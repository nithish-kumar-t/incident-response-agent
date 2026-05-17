import base64
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from config import settings


def send_incident_email(
    service: str,
    alertname: str,
    summary: str,
    analysis: str,
    pdf_base64: str | None = None,
    pdf_filename: str | None = None,
):
    msg = MIMEMultipart("mixed")
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
  <div style="background:#1a1a2e; padding:24px 28px; border-radius:6px 6px 0 0;">
    <h2 style="color:white; margin:0; font-size:18px;">&#x1F6A8; INCIDENT: {alertname}</h2>
    <p style="color:#a0aec0; margin:6px 0 0; font-size:13px;">{service}</p>
  </div>
  <div style="border:1px solid #e2e8f0; padding:20px 28px; border-radius:0 0 6px 6px;">
    <table style="width:100%; border-collapse:collapse; margin-bottom:20px;">
      <tr>
        <td style="padding:8px; color:#718096; width:90px; font-size:12px;">Alert</td>
        <td style="padding:8px;"><strong>{alertname}</strong></td>
      </tr>
      <tr style="background:#f8f9fa;">
        <td style="padding:8px; color:#718096; font-size:12px;">Service</td>
        <td style="padding:8px;"><strong>{service}</strong></td>
      </tr>
      <tr>
        <td style="padding:8px; color:#718096; font-size:12px;">Summary</td>
        <td style="padding:8px;">{summary}</td>
      </tr>
    </table>
    <h3 style="border-bottom:2px solid #e2e8f0; padding-bottom:8px; font-size:14px;">Analysis</h3>
    <pre style="background:#f4f4f4; padding:16px; border-radius:4px; white-space:pre-wrap; font-size:12px; line-height:1.6;">{analysis}</pre>
    {"<p style='margin-top:16px; padding:12px; background:#edfaf3; border-radius:4px; font-size:13px; border-left:3px solid #27ae60;'>&#x1F4CE; <strong>Full incident report attached</strong> — see PDF for detailed code analysis and fix suggestion.</p>" if pdf_base64 else ""}
    <p style="color:#a0aec0; font-size:11px; margin-top:20px; border-top:1px solid #e2e8f0; padding-top:12px;">
      Sent automatically by the Incident Response Agent.
    </p>
  </div>
</body>
</html>
"""

    # Build the email body as an alternative part
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(plain, "plain"))
    body.attach(MIMEText(html, "html"))
    msg.attach(body)

    # Attach PDF if provided
    if pdf_base64 and pdf_filename:
        pdf_bytes = base64.b64decode(pdf_base64)
        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=pdf_filename)
        msg.attach(attachment)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        server.login(settings.EMAIL_SENDER, settings.EMAIL_APP_PASSWORD)
        server.sendmail(settings.EMAIL_SENDER, settings.EMAIL_RECEIVER, msg.as_string())
