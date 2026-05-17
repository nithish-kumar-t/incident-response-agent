import asyncio
import base64
import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

from config import settings
from agents.log_analyzer_agent import LogAnalyzerAgent
from pipeline import run_pipeline
from reports.generator import generate_pdf

LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "workflow.log"),
    ],
)
log = logging.getLogger("incident-agent-workflow")
logging.getLogger("fontTools").setLevel(logging.ERROR)
logging.getLogger("weasyprint").setLevel(logging.WARNING)

app = FastAPI(title="Incident Agent Workflow")
Instrumentator().instrument(app).expose(app)

PROMETHEUS_URL = "http://prometheus:9090"
LOKI_URL = "http://loki:3100"

_quick_analyzer = LogAnalyzerAgent()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "incident-agent-workflow"}


@app.post("/alerts")
async def receive_alerts(request: Request):
    payload = await request.json()
    alerts = payload.get("alerts", [])

    for alert in alerts:
        asyncio.create_task(_handle_alert(alert))

    return {"status": "accepted", "alerts_received": len(alerts)}


async def _handle_alert(alert: dict):
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    service = labels.get("service", "unknown")
    alert_name = labels.get("alertname", "unknown")
    status = alert.get("status", "firing")

    log.info("alert_received alertname=%s service=%s status=%s", alert_name, service, status)

    async with httpx.AsyncClient(timeout=5.0) as client:
        prometheus_snapshot = await _query_prometheus(client, service)
        recent_logs = await _query_loki(client, service)

    context = {
        "alertname": alert_name,
        "service": service,
        "summary": annotations.get("summary", ""),
        "prometheus_snapshot": prometheus_snapshot,
        "recent_logs": recent_logs,
    }

    # Quick analysis — always runs, gives a reliable baseline even if pipeline fails
    quick_analysis = await asyncio.to_thread(_quick_analyzer.run, context)
    log.info("quick_analysis_done service=%s alert=%s", service, alert_name)

    error_payload = {**context, "description": annotations.get("description", ""), "status": status}

    pipeline_result = None
    pdf_b64 = None
    try:
        pipeline_result = await run_pipeline(error_payload)
        log.info("pipeline_complete pipeline_id=%s service=%s", pipeline_result["pipeline_id"], service)

        try:
            pdf_bytes = await asyncio.to_thread(generate_pdf, pipeline_result)
            pdf_b64 = base64.b64encode(pdf_bytes).decode()
            log.info("pdf_generated pipeline_id=%s bytes=%d", pipeline_result["pipeline_id"], len(pdf_bytes))
        except Exception as pdf_exc:
            log.warning("pdf_generation_failed pipeline_id=%s error=%s", pipeline_result["pipeline_id"], str(pdf_exc))

    except Exception as exc:
        log.error("pipeline_failed service=%s alert=%s error=%s", service, alert_name, str(exc))

    await _send_notification(
        service, alert_name,
        annotations.get("summary", ""),
        quick_analysis, pipeline_result, pdf_b64,
    )


def _extract_agent_text(agent_result: dict, *field_names: str) -> str:
    """Pull structured fields or fall back to raw LLM output if JSON parsing failed."""
    values = [str(agent_result.get(f, "")) for f in field_names if agent_result.get(f)]
    if values:
        return " | ".join(values)
    # LLM returned non-parseable output — use the raw text
    raw = agent_result.get("raw_output", "")
    return raw[:800] if raw else "—"


async def _send_notification(
    service: str,
    alertname: str,
    summary: str,
    quick_analysis: str,
    pipeline_result: dict | None,
    pdf_b64: str | None,
):
    lines = []

    # ── Quick analysis (always present) ──────────────────────────────────────
    lines.append("QUICK ANALYSIS")
    lines.append("─" * 60)
    lines.append(quick_analysis)

    # ── Deep pipeline analysis ────────────────────────────────────────────────
    if pipeline_result:
        pid = pipeline_result.get("pipeline_id", "?")
        triage = pipeline_result.get("triage", {})
        invest = pipeline_result.get("investigation", {})
        code = pipeline_result.get("code_analysis", {})

        severity   = triage.get("severity") or "unknown"
        err_type   = triage.get("error_type") or "unknown"
        err_sum    = triage.get("error_summary") or _extract_agent_text(triage, "raw_output")
        hypothesis = invest.get("root_cause_hypothesis") or _extract_agent_text(invest, "raw_output")
        confidence = invest.get("confidence") or "unknown"
        inference  = invest.get("inference") or ""
        root_cause = code.get("root_cause") or _extract_agent_text(code, "raw_output")
        fix        = code.get("fix_suggestion") or ""
        next_steps = code.get("recommended_next_steps") or []
        stack      = invest.get("stack_trace") or ""
        actions    = triage.get("actions_taken") or []

        lines.append(f"\n\nDEEP ANALYSIS  [Pipeline {pid}]")
        lines.append("─" * 60)

        lines.append(f"\n▶ TRIAGE")
        lines.append(f"  Severity : {severity.upper()}")
        lines.append(f"  Type     : {err_type}")
        lines.append(f"  Summary  : {err_sum}")
        if actions:
            lines.append(f"  Actions  : {', '.join(str(a) for a in actions)}")

        lines.append(f"\n▶ INVESTIGATION  (confidence: {confidence})")
        lines.append(f"  Hypothesis : {hypothesis}")
        if inference:
            lines.append(f"  Inference  : {inference}")
        if stack:
            lines.append(f"\n  Stack trace:\n{stack[:1200]}")

        lines.append(f"\n▶ CODE ANALYSIS")
        lines.append(f"  Root cause : {root_cause}")
        if fix:
            lines.append(f"  Fix        : {fix}")
        if next_steps:
            for i, step in enumerate(next_steps, 1):
                lines.append(f"  Step {i}: {step}")

        if pdf_b64:
            lines.append("\n📎 Full incident report attached as PDF.")
    else:
        lines.append("\n\nDEEP ANALYSIS")
        lines.append("─" * 60)
        lines.append("Pipeline did not complete — see workflow logs for details.")
        lines.append("Quick analysis above is your primary reference.")

    analysis = "\n".join(lines)

    try:
        payload: dict = {
            "service": service,
            "alertname": alertname,
            "summary": summary,
            "analysis": analysis,
        }
        if pdf_b64:
            payload["pdf_base64"] = pdf_b64
            payload["pdf_filename"] = f"incident-{(pipeline_result or {}).get('pipeline_id', 'report')}.pdf"

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(settings.NOTIFIER_URL, json=payload)
        log.info("notification_sent alertname=%s service=%s pdf=%s", alertname, service, pdf_b64 is not None)
    except Exception as exc:
        log.warning("notification_failed alertname=%s service=%s error=%s", alertname, service, str(exc))


async def _query_prometheus(client: httpx.AsyncClient, service: str) -> dict:
    if service == "unknown":
        return {}

    queries = {
        "up": f'up{{service="{service}"}}',
        "five_xx_rate": f'sum(rate(http_requests_total{{service="{service}",status="5xx"}}[2m]))',
    }

    results = {}
    for name, query in queries.items():
        try:
            response = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            response.raise_for_status()
            results[name] = response.json().get("data", {}).get("result", [])
        except Exception as exc:
            results[name] = f"query_failed: {exc}"
    return results


async def _query_loki(client: httpx.AsyncClient, service: str) -> list:
    if service == "unknown":
        return []

    try:
        response = await client.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": f'{{service="{service}"}}',
                "limit": 5,
                "direction": "backward",
            },
        )
        response.raise_for_status()
        streams = response.json().get("data", {}).get("result", [])
        return [
            line
            for stream in streams
            for _, line in stream.get("values", [])
        ][:5]
    except Exception as exc:
        return [f"query_failed: {exc}"]
