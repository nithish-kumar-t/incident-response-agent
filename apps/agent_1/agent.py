from fastapi import FastAPI, Request
from agents.log_analyzer_agent import LogAnalyzerAgent
from config import settings
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title=settings.APP_NAME)

log_analyzer = LogAnalyzerAgent()


@app.get("/")
def health():
    return {"status": "ok", "service": settings.APP_NAME}


@app.post("/alert")
async def receive_alert(request: Request):
    payload = await request.json()
    alerts = payload.get("alerts", [])

    for alert in alerts:
        if alert.get("status") != "firing":
            continue

        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})

        context = {
            "alertname": labels.get("alertname", "unknown"),
            "service": labels.get("service", "unknown"),
            "summary": annotations.get("summary", ""),
        }

        log.info(f"Alert received: {context['alertname']} for service '{context['service']}'")

        analysis = log_analyzer.run(context)

        log.info(f"\n{'='*60}\nINCIDENT ANALYSIS — {context['alertname']}\nService: {context['service']}\n{'='*60}\n{analysis}\n{'='*60}\n")

    return {"status": "received"}
