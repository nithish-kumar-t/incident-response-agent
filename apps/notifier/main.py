import logging
from fastapi import FastAPI
from pydantic import BaseModel
from emailer import send_incident_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(__name__)

app = FastAPI(title="Notifier Service")


class NotifyPayload(BaseModel):
    service: str
    alertname: str
    summary: str
    analysis: str


@app.get("/")
def health():
    return {"status": "ok", "service": "notifier"}


@app.post("/notify")
def notify(payload: NotifyPayload):
    try:
        send_incident_email(
            service=payload.service,
            alertname=payload.alertname,
            summary=payload.summary,
            analysis=payload.analysis,
        )
        log.info("Email sent for alert=%s service=%s", payload.alertname, payload.service)
        return {"status": "sent"}
    except Exception as e:
        log.error("Failed to send email: %s", str(e))
        return {"status": "failed", "error": str(e)}
