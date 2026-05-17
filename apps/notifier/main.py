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
    pdf_base64: str | None = None
    pdf_filename: str | None = None


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
            pdf_base64=payload.pdf_base64,
            pdf_filename=payload.pdf_filename,
        )
        has_pdf = payload.pdf_base64 is not None
        log.info("Email sent for alert=%s service=%s pdf=%s", payload.alertname, payload.service, has_pdf)
        return {"status": "sent", "pdf_attached": has_pdf}
    except Exception as e:
        log.error("Failed to send email: %s", str(e))
        return {"status": "failed", "error": str(e)}
