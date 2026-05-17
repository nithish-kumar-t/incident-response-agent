import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from prometheus_fastapi_instrumentator import Instrumentator

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

app = FastAPI(title="Incident Agent Workflow")
Instrumentator().instrument(app).expose(app)

PROMETHEUS_URL = "http://prometheus:9090"
LOKI_URL = "http://loki:3100"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "incident-agent-workflow"}


@app.post("/alerts")
async def receive_alerts(request: Request):
    payload = await request.json()
    alerts = payload.get("alerts", [])

    async with httpx.AsyncClient(timeout=5.0) as client:
        for alert in alerts:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            service = labels.get("service", "unknown")
            alert_name = labels.get("alertname", "unknown")
            status = alert.get("status", "unknown")

            prometheus_snapshot = await query_prometheus(client, service)
            recent_logs = await query_loki(client, service)


#LLM CALL
            analysis = await analyze_with_ollama(service, alert_name, annotations.get("summary", ""), prometheus_snapshot, recent_logs)
            log.warning("ollama_analysis service=%s alert=%s analysis=%s", service, alert_name, analysis)




            log.warning(
                "agent_workflow_triggered status=%s alert=%s service=%s summary=%s prometheus=%s recent_logs=%s",
                status,
                alert_name,
                service,
                annotations.get("summary", ""),
                prometheus_snapshot,
                recent_logs,
            )

    return {"status": "accepted", "alerts_received": len(alerts)}


async def query_prometheus(client: httpx.AsyncClient, service: str):
    if service == "unknown":
        return {}

    queries = {
        "up": f'up{{service="{service}"}}',
        "five_xx_rate": (
            f'sum(rate(http_requests_total{{service="{service}",status="5xx"}}[2m]))'
        ),
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


async def query_loki(client: httpx.AsyncClient, service: str):
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




#### LLM METHOD

async def analyze_with_ollama(service: str, alert_name: str, summary: str, prometheus_snapshot: dict, recent_logs: list) -> str:
    prompt = f"""You are an incident response agent analyzing a production alert.

Alert: {alert_name}
Service: {service}
Summary: {summary}

Prometheus metrics:
{prometheus_snapshot}

Recent logs:
{chr(10).join(recent_logs)}

Analyze and answer:
1. What went wrong?
2. What is the likely root cause?
3. What should the on-call engineer check first?

Be concise and specific."""

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "http://host.docker.internal:11434/api/generate",
                json={"model": "mistral-nemo", "prompt": prompt, "stream": False}
            )
            response.raise_for_status()
            return response.json()["response"]
    except Exception as exc:
        return f"Ollama analysis failed: {exc}"
