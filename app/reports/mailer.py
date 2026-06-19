from __future__ import annotations

import logging

from app.config import settings

log = logging.getLogger(__name__)


def send_report(subject: str, html: str) -> bool:
    if not settings.send_email:
        log.info("SEND_EMAIL=false; skipping email send")
        return False
    if not settings.sendgrid_api_key:
        raise RuntimeError("SENDGRID_API_KEY is required when SEND_EMAIL=true")
    if not settings.email_from or not settings.email_to:
        raise RuntimeError("EMAIL_FROM and EMAIL_TO are required when SEND_EMAIL=true")

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=settings.email_from,
        to_emails=settings.email_to,
        subject=subject,
        html_content=html,
    )
    sg = SendGridAPIClient(settings.sendgrid_api_key)
    response = sg.send(message)
    log.info("SendGrid response status: %s", response.status_code)
    return 200 <= response.status_code < 300
