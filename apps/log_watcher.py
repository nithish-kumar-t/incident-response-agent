"""
Log Watcher Middleware
Scans service log files for errors/warnings, calls the 3-agent incident analysis
pipeline for each finding, then generates a Word document report.

Usage:
    python log_watcher.py [--tail N] [--agent-url URL] [--no-pipeline]

Requires:
    pip install httpx python-docx
"""

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ── Configuration ──────────────────────────────────────────────────────────────

AGENT_API_URL = "http://localhost:8000"

LOG_SOURCES: list[dict[str, str]] = [
    {
        "service_name": "mongo-api-service",
        "log_path": r"C:\UIC_COURSES\uncommon_hack\final_ones\apps\mongo-api-service\logs\service.log",
        "repo_path": r"C:\UIC_COURSES\uncommon_hack\final_ones\apps\mongo-api-service",
        "health_url": "http://localhost:8001/health",
    },
    {
        "service_name": "weather-app1",
        "log_path": r"C:\UIC_COURSES\uncommon_hack\final_ones\apps\weather-app1\logs\app.log",
        "repo_path": r"C:\UIC_COURSES\uncommon_hack\final_ones\apps\weather-app1",
        "health_url": "http://localhost:8002/health",
    },
]

REPORTS_DIR = Path(r"C:\UIC_COURSES\uncommon_hack\final_ones\apps\reports")
DEFAULT_TAIL_LINES = 500
CONTEXT_WINDOW = 8       # lines before/after each flagged line
API_TIMEOUT = 180.0      # seconds per pipeline call

# Lines are flagged if they match any of these patterns
_ERROR_KW = re.compile(
    r"\b(ERROR|CRITICAL|EXCEPTION|Traceback|FATAL|WARN(?:ING)?)\b",
    re.IGNORECASE,
)
# HTTP 4xx/5xx embedded as "-> 502" or "status=502" or "status_code=502"
_STATUS_CODE = re.compile(r"(?:->[ ]?|status(?:_code)?[=: ])([45]\d{2})")


# ── Log Parsing ────────────────────────────────────────────────────────────────

def read_log(log_path: str, tail: int) -> list[str]:
    p = Path(log_path)
    if not p.exists():
        return []
    with open(p, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return lines[-tail:]


def parse_timestamp(line: str) -> str:
    """Pull an ISO-like timestamp from the beginning of a log line."""
    m = re.match(r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", line)
    return m.group(1) if m else datetime.now(timezone.utc).isoformat()


def extract_errors(lines: list[str]) -> list[dict[str, Any]]:
    """
    Return deduplicated error events with surrounding context.
    Consecutive lines near the same error are merged into one event.
    """
    events: list[dict[str, Any]] = []
    absorbed: set[int] = set()

    for i, line in enumerate(lines):
        if i in absorbed:
            continue
        if _ERROR_KW.search(line) or _STATUS_CODE.search(line):
            start = max(0, i - CONTEXT_WINDOW)
            end = min(len(lines), i + CONTEXT_WINDOW + 1)
            for idx in range(start, end):
                absorbed.add(idx)
            events.append({
                "line_number": i + 1,
                "line": line.rstrip(),
                "timestamp": parse_timestamp(line),
                "context": "".join(lines[start:end]).rstrip(),
            })

    return events


# ── Agent Pipeline ─────────────────────────────────────────────────────────────

async def agent_healthy(client: httpx.AsyncClient, url: str) -> bool:
    try:
        r = await client.get(f"{url}/health", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False


async def call_pipeline(
    client: httpx.AsyncClient,
    agent_url: str,
    source: dict[str, str],
    error: dict[str, Any],
) -> dict[str, Any]:
    """
    POST /analyze with the error info and log-path overrides.
    Returns the full pipeline response dict or an error dict.
    """
    payload: dict[str, Any] = {
        "service_name": source["service_name"],
        "error_message": error["line"],
        "timestamp": error["timestamp"],
        # log_paths override — these services aren't in service_registry.json
        "log_paths": {"service": source["log_path"]},
        "repo_path": source["repo_path"],
        "additional_context": {
            "line_number": error["line_number"],
            "context_window": error["context"],
        },
    }
    try:
        r = await client.post(
            f"{agent_url}/analyze",
            json=payload,
            timeout=API_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        return {
            "pipeline_error": f"HTTP {exc.response.status_code}",
            "detail": exc.response.text[:800],
        }
    except Exception as exc:
        return {"pipeline_error": str(exc)}


# ── Orchestrator ───────────────────────────────────────────────────────────────

async def run(
    tail: int = DEFAULT_TAIL_LINES,
    agent_url: str = AGENT_API_URL,
    skip_pipeline: bool = False,
) -> dict[str, Any]:
    scan: dict[str, Any] = {
        "scan_time": datetime.now(timezone.utc).isoformat(),
        "agent_api_url": agent_url,
        "agent_healthy": False,
        "log_sources": LOG_SOURCES,
        "services": [],
    }

    async with httpx.AsyncClient() as client:
        if skip_pipeline:
            print("[INFO] Pipeline calls skipped (--no-pipeline flag).")
        else:
            scan["agent_healthy"] = await agent_healthy(client, agent_url)
            if scan["agent_healthy"]:
                print(f"[OK]   Agent pipeline reachable at {agent_url}")
            else:
                print(
                    f"[WARN] Agent pipeline at {agent_url} is unreachable. "
                    "Log scan will continue but pipeline analysis will be skipped.",
                    file=sys.stderr,
                )

        for source in LOG_SOURCES:
            svc: dict[str, Any] = {
                "service_name": source["service_name"],
                "log_path": source["log_path"],
                "log_exists": Path(source["log_path"]).exists(),
                "total_lines_scanned": 0,
                "errors": [],
                "pipeline_results": [],
            }

            lines = read_log(source["log_path"], tail)
            svc["total_lines_scanned"] = len(lines)

            if not lines:
                print(f"[INFO] {source['service_name']}: log file empty or missing — {source['log_path']}")
                scan["services"].append(svc)
                continue

            errors = extract_errors(lines)
            svc["errors"] = errors
            label = f"{len(errors)} error(s)" if errors else "no errors"
            print(f"[INFO] {source['service_name']}: {label} in {len(lines)} lines")

            if errors and (scan["agent_healthy"] and not skip_pipeline):
                for err in errors:
                    preview = err["line"][:80] + ("…" if len(err["line"]) > 80 else "")
                    print(f"  ↳ Pipeline call for line {err['line_number']}: {preview}")
                    result = await call_pipeline(client, agent_url, source, err)
                    svc["pipeline_results"].append(
                        {"error": err, "pipeline_response": result}
                    )
                    await asyncio.sleep(0.3)

            scan["services"].append(svc)

    return scan


# ── Entry Point ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Log watcher middleware")
    parser.add_argument("--tail", type=int, default=DEFAULT_TAIL_LINES,
                        help="Number of tail lines to read per log file")
    parser.add_argument("--agent-url", default=AGENT_API_URL,
                        help="Base URL of the agent pipeline service")
    parser.add_argument("--no-pipeline", action="store_true",
                        help="Skip agent pipeline calls (generate scan-only report)")
    parser.add_argument("--output-dir", default=str(REPORTS_DIR),
                        help="Directory to write the .docx report")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(" Log Watcher Middleware")
    print("=" * 60)

    results = asyncio.run(
        run(
            tail=args.tail,
            agent_url=args.agent_url,
            skip_pipeline=args.no_pipeline,
        )
    )

    try:
        from report_generator import generate_report
        report_path = generate_report(results, output_dir)
        print(f"\n[DONE] Report saved to: {report_path}")
    except ImportError:
        print("\n[ERROR] report_generator.py not found. Install python-docx and ensure both files are together.")
        raise
