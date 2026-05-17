import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import settings


def send_incident_email(service: str, alertname: str, summary: str, analysis: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[INCIDENT] {alertname} — {service}"
    msg["From"] = settings.EMAIL_SENDER
    msg["To"] = settings.EMAIL_RECEIVER

    plain = f"""INCIDENT ALERT
{'='*60}
Alert:   {alertname}
Service: {service}
Summary: {summary}
{'='*60}

ANALYSIS
{analysis}

{'='*60}
This notification was sent automatically by the Incident Response Agent.
"""

    html = f"""
<html>
<body style="font-family: Arial, sans-serif; max-width: 700px; margin: auto;">
  <div style="background:#c0392b; padding:16px; border-radius:6px 6px 0 0;">
    <h2 style="color:white; margin:0;">&#x1F6A8; INCIDENT: {alertname}</h2>
  </div>
  <div style="border:1px solid #ddd; padding:20px; border-radius:0 0 6px 6px;">
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px;">
      <tr><td style="padding:6px; color:#888; width:100px;">Alert</td><td style="padding:6px;"><strong>{alertname}</strong></td></tr>
      <tr style="background:#f9f9f9;"><td style="padding:6px; color:#888;">Service</td><td style="padding:6px;"><strong>{service}</strong></td></tr>
      <tr><td style="padding:6px; color:#888;">Summary</td><td style="padding:6px;">{summary}</td></tr>
    </table>
    <h3 style="border-bottom:2px solid #eee; padding-bottom:8px;">Analysis</h3>
    <pre style="background:#f4f4f4; padding:16px; border-radius:4px; white-space:pre-wrap; font-size:13px;">{analysis}</pre>
    <p style="color:#aaa; font-size:12px; margin-top:20px;">
      Sent automatically by the Incident Response Agent.
    </p>
  </div>
</body>
</html>
"""

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.EMAIL_SENDER, settings.EMAIL_APP_PASSWORD)
        server.sendmail(settings.EMAIL_SENDER, settings.EMAIL_RECEIVER, msg.as_string())
