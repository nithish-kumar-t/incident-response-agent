"""
Monitor Service
---------------
Runs as a persistent daemon that:
  1. Polls service log files every POLL_INTERVAL seconds for new errors / HTTP 4xx-5xx
  2. Health-checks each service's HTTP endpoint to detect API-down events
  3. Triggers the 3-agent incident-analysis pipeline *directly* (no HTTP hop)
     by importing run_pipeline from apps/agent/pipeline.py
  4. Generates a Word report via report_generator.py for every scan cycle that
     finds new issues (or on first clean scan after previous failures)

Usage:
    python monitor_service.py [--interval N] [--tail N] [--output-dir DIR] [--no-report]

Requires:
    pip install httpx python-docx
    (python-docx only needed when --no-report is NOT set)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import re
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ── Inject the agent package onto the path ─────────────────────────────────────
_AGENT_DIR = Path(__file__).parent / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from pipeline import run_pipeline  # noqa: E402  (must be after sys.path edit)

# ── Configuration ──────────────────────────────────────────────────────────────

POLL_INTERVAL   = 60          # seconds between scans
DEFAULT_TAIL    = 500         # log lines to read per scan
CONTEXT_WINDOW  = 8           # lines before/after a flagged line
HEALTH_TIMEOUT  = 5.0         # seconds for service health-check requests
PIPELINE_CONCURRENCY = 2      # max simultaneous pipeline calls
DEFAULT_MAX_EVENTS_PER_SCAN = 3

REPORTS_DIR = Path(__file__).parent / "reports"

LOG_SOURCES: list[dict[str, str]] = [
    {
        "service_name": "mongo-api-service",
        "log_path": str(Path(__file__).parent / "mongo-api-service" / "logs" / "service.log"),
        "repo_path": str(Path(__file__).parent / "mongo-api-service"),
        "health_url": "http://localhost:9000/health/ready",
    },
    {
        "service_name": "weather-app1",
        "log_path": str(Path(__file__).parent / "weather-app1" / "logs" / "app.log"),
        "repo_path": str(Path(__file__).parent / "weather-app1"),
        "health_url": "http://localhost:8000/",
    },
]

# ── Regex patterns ─────────────────────────────────────────────────────────────

_ERROR_KW = re.compile(
    r"\b(ERROR|CRITICAL|EXCEPTION|Traceback|FATAL|WARN(?:ING)?)\b",
    re.IGNORECASE,
)
_STATUS_CODE = re.compile(r"(?:->[ ]?|status(?:_code)?[=: ])([45]\d{2})")

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("monitor")


# ── Log utilities ──────────────────────────────────────────────────────────────

def read_log(log_path: str, tail: int) -> list[str]:
    p = Path(log_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return lines[-tail:]


def parse_timestamp(line: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line)
    return m.group(1) if m else datetime.now(timezone.utc).isoformat()


def extract_errors(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    absorbed: set[int] = set()
    for i, line in enumerate(lines):
        if i in absorbed:
            continue
        if _ERROR_KW.search(line) or _STATUS_CODE.search(line):
            start = max(0, i - CONTEXT_WINDOW)
            end   = min(len(lines), i + CONTEXT_WINDOW + 1)
            for idx in range(start, end):
                absorbed.add(idx)
            events.append({
                "line_number": i + 1,
                "line":        line.rstrip(),
                "timestamp":   parse_timestamp(line),
                "context":     "".join(lines[start:end]).rstrip(),
            })
    return events


def error_fingerprint(service_name: str, err: dict[str, Any]) -> str:
    """Stable hash so we don't re-trigger the pipeline for lines we already processed."""
    raw = f"{service_name}|{err['line_number']}|{err['line']}"
    return hashlib.sha1(raw.encode()).hexdigest()


# ── Health check ───────────────────────────────────────────────────────────────

async def check_health(client: httpx.AsyncClient, source: dict[str, str]) -> dict[str, Any]:
    url = source.get("health_url", "")
    if not url:
        return {"service_name": source["service_name"], "reachable": None, "status_code": None}
    try:
        r = await client.get(url, timeout=HEALTH_TIMEOUT)
        ok = r.status_code == 200
        log.info("[health] %s → %s %s", source["service_name"], r.status_code, "OK" if ok else "DEGRADED")
        return {"service_name": source["service_name"], "reachable": ok, "status_code": r.status_code}
    except Exception as exc:
        log.warning("[health] %s → UNREACHABLE (%s)", source["service_name"], exc)
        return {"service_name": source["service_name"], "reachable": False, "status_code": None}


# ── Direct pipeline trigger ────────────────────────────────────────────────────

async def trigger_pipeline(
    source: dict[str, str],
    err: dict[str, Any],
    health_status: dict[str, Any],
) -> dict[str, Any]:
    """Call run_pipeline() directly — no HTTP server needed."""
    payload: dict[str, Any] = {
        "service_name":    source["service_name"],
        "error_message":   err["line"],
        "timestamp":       err["timestamp"],
        "log_paths":       {"service": source["log_path"]},
        "repo_path":       source["repo_path"],
        "additional_context": {
            "line_number":    err["line_number"],
            "context_window": err["context"],
            "api_reachable":  health_status.get("reachable"),
            "api_status_code": health_status.get("status_code"),
        },
    }
    log.info(
        "[pipeline] %s — triggering for line %d: %.80s",
        source["service_name"], err["line_number"], err["line"],
    )
    try:
        result = await run_pipeline(payload)
        log.info(
            "[pipeline] %s — pipeline %s done (severity=%s)",
            source["service_name"],
            result.get("pipeline_id"),
            result.get("agent1_triage", {}).get("severity", "?"),
        )
        return result
    except Exception as exc:
        log.exception("[pipeline] %s — pipeline failed: %s", source["service_name"], exc)
        return {"pipeline_error": str(exc)}


# ── One scan cycle ─────────────────────────────────────────────────────────────

async def run_scan(
    seen_fingerprints: set[str],
    tail: int,
    max_events: int,
) -> dict[str, Any]:
    scan: dict[str, Any] = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "services": [],
        "new_events": 0,
    }

    sem = asyncio.Semaphore(PIPELINE_CONCURRENCY)
    remaining_events = max_events

    async with httpx.AsyncClient() as client:
        health_results = await asyncio.gather(
            *[check_health(client, src) for src in LOG_SOURCES]
        )
        health_map = {h["service_name"]: h for h in health_results}

    for source in LOG_SOURCES:
        svc_name = source["service_name"]
        health   = health_map[svc_name]
        lines    = read_log(source["log_path"], tail)

        svc: dict[str, Any] = {
            "service_name":       svc_name,
            "log_path":           source["log_path"],
            "log_exists":         Path(source["log_path"]).exists(),
            "total_lines_scanned": len(lines),
            "health":             health,
            "errors":             [],
            "pipeline_results":   [],
        }

        # Synthesise a fake "API down" error entry when health check fails
        api_down_fp = f"{svc_name}|api_down"
        if health["reachable"] is False and api_down_fp not in seen_fingerprints and remaining_events > 0:
            seen_fingerprints.add(api_down_fp)
            api_err: dict[str, Any] = {
                "line_number": 0,
                "line":        f"[MONITOR] Service {svc_name} health endpoint UNREACHABLE",
                "timestamp":   datetime.now(timezone.utc).isoformat(),
                "context":     f"Health URL: {source.get('health_url')}\nStatus code: {health.get('status_code')}",
            }
            svc["errors"].append(api_err)
            log.warning("[scan] %s — API DOWN, triggering pipeline", svc_name)
            async with sem:
                result = await trigger_pipeline(source, api_err, health)
            svc["pipeline_results"].append({"error": api_err, "pipeline_response": result})
            scan["new_events"] += 1
            remaining_events -= 1
        elif health["reachable"] is True:
            # Clear the api_down fingerprint so we re-alert if it goes down again
            seen_fingerprints.discard(api_down_fp)

        if not lines:
            log.info("[scan] %s — log empty or missing", svc_name)
            scan["services"].append(svc)
            continue

        errors = extract_errors(lines)
        svc["errors"].extend(errors)
        log.info("[scan] %s — %d error(s) in %d lines", svc_name, len(errors), len(lines))

        async def process_error(err: dict[str, Any], src=source, h=health, s=svc) -> bool:
            fp = error_fingerprint(src["service_name"], err)
            if fp in seen_fingerprints:
                return False
            seen_fingerprints.add(fp)
            async with sem:
                result = await trigger_pipeline(src, err, h)
            s["pipeline_results"].append({"error": err, "pipeline_response": result})
            scan["new_events"] += 1
            return True

        for err in errors:
            if remaining_events <= 0:
                log.warning(
                    "[scan] Reached max events per scan (%d); remaining errors will be handled next cycle",
                    max_events,
                )
                break
            processed = await process_error(err)
            if processed:
                remaining_events -= 1
        scan["services"].append(svc)

    return scan


# ── Service loop ───────────────────────────────────────────────────────────────

async def service_loop(
    interval: int,
    tail: int,
    reports_dir: Path,
    no_report: bool,
    max_events: int,
    stop_event: asyncio.Event,
) -> None:
    seen_fingerprints: set[str] = set()
    reports_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info(" Monitor Service started")
    log.info(" Poll interval : %ds", interval)
    log.info(" Tail lines    : %d", tail)
    log.info(" Reports dir   : %s", reports_dir)
    log.info(" Pipeline      : direct (no HTTP)")
    log.info(" Max events    : %d per scan", max_events)
    log.info("=" * 60)

    cycle = 0
    while not stop_event.is_set():
        cycle += 1
        log.info("── Scan cycle #%d ──────────────────────────────────────", cycle)

        scan = await run_scan(seen_fingerprints, tail, max_events)

        if not no_report and scan["new_events"] > 0:
            try:
                # report_generator lives alongside this file
                sys.path.insert(0, str(Path(__file__).parent))
                from report_generator import generate_report
                scan["agent_api_url"] = "direct"
                scan["agent_healthy"] = True
                scan["log_sources"]   = LOG_SOURCES
                report_path = generate_report(scan, reports_dir)
                log.info("[report] Written → %s", report_path)
            except Exception as exc:
                log.exception("[report] Failed to generate report: %s", exc)
        elif scan["new_events"] == 0:
            log.info("[scan] No new events — next scan in %ds", interval)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    log.info("Monitor Service stopped")


# ── Signal handling ────────────────────────────────────────────────────────────

def _install_signals(loop: asyncio.AbstractEventLoop, stop_event: asyncio.Event) -> None:
    def _stop() -> None:
        log.info("Shutdown signal received — finishing current scan before stopping.")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler for SIGTERM
            signal.signal(sig, lambda *_: stop_event.set())


# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Log-watcher + agent monitor service")
    p.add_argument("--interval",   type=int, default=POLL_INTERVAL,
                   help="Seconds between scan cycles (default: %(default)s)")
    p.add_argument("--tail",       type=int, default=DEFAULT_TAIL,
                   help="Log tail lines per scan (default: %(default)s)")
    p.add_argument("--output-dir", default=str(REPORTS_DIR),
                   help="Directory for .docx reports (default: %(default)s)")
    p.add_argument("--no-report",  action="store_true",
                   help="Skip Word document generation")
    p.add_argument("--max-events", type=int, default=DEFAULT_MAX_EVENTS_PER_SCAN,
                   help="Maximum new events to send to the agent per scan (default: %(default)s)")
    return p.parse_args()


if __name__ == "__main__":
    args   = parse_args()
    loop   = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    stop_event = asyncio.Event()
    _install_signals(loop, stop_event)

    try:
        loop.run_until_complete(
            service_loop(
                interval    = args.interval,
                tail        = args.tail,
                reports_dir = Path(args.output_dir),
                no_report   = args.no_report,
                max_events  = args.max_events,
                stop_event  = stop_event,
            )
        )
    finally:
        loop.close()
