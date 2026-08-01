from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.config import settings

log = logging.getLogger(__name__)


def _send_with_sendgrid(subject: str, html: str) -> bool:
    if not settings.sendgrid_api_key:
        raise RuntimeError("SENDGRID_API_KEY is required when EMAIL_PROVIDER=sendgrid and SEND_EMAIL=true")
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


def _smtp_host() -> str:
    """Return a usable SMTP host even when an empty GitHub secret is injected."""

    host = str(settings.smtp_host or "").strip()
    if host:
        return host
    if (settings.email_provider or "").strip().lower() in {"smtp", "icloud", "apple", "mail"}:
        return "smtp.mail.me.com"
    raise RuntimeError("SMTP_HOST is required when EMAIL_PROVIDER=smtp and SEND_EMAIL=true")


def _send_with_smtp(subject: str, html: str) -> bool:
    if not settings.email_from or not settings.email_to:
        raise RuntimeError("EMAIL_FROM and EMAIL_TO are required when SEND_EMAIL=true")
    if not settings.smtp_username or not settings.smtp_password:
        raise RuntimeError("SMTP_USERNAME and SMTP_PASSWORD are required when EMAIL_PROVIDER=smtp and SEND_EMAIL=true")

    host = _smtp_host()
    port = int(settings.smtp_port or 587)
    recipients = [addr.strip() for addr in settings.email_to.replace(";", ",").split(",") if addr.strip()]
    if not recipients:
        raise RuntimeError("EMAIL_TO does not contain a valid recipient address")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((settings.smtp_from_name, settings.email_from)) if settings.smtp_from_name else settings.email_from
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText("请使用支持 HTML 的邮件客户端查看本日报。", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    timeout = max(5, settings.smtp_timeout_seconds)
    log.info(
        "Sending report via SMTP provider=%s host=%s port=%s tls=%s recipients=%s",
        settings.email_provider,
        host,
        port,
        settings.smtp_starttls,
        len(recipients),
    )

    # Create the client first and connect explicitly. This makes an empty or
    # unreachable host fail at connect() with a useful error instead of the
    # misleading "please run connect() first" error at ehlo().
    with smtplib.SMTP(timeout=timeout) as server:
        server.connect(host, port)
        server.ehlo()
        if settings.smtp_starttls:
            server.starttls()
            server.ehlo()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.email_from, recipients, msg.as_string())

    log.info("SMTP email sent via %s", host)
    return True


def send_report(subject: str, html: str) -> bool:
    if not settings.send_email:
        log.info("SEND_EMAIL=false; skipping email send")
        return False

    provider = (settings.email_provider or "sendgrid").strip().lower()
    if provider in {"smtp", "icloud", "apple", "mail"}:
        return _send_with_smtp(subject, html)
    if provider == "sendgrid":
        return _send_with_sendgrid(subject, html)

    raise RuntimeError(f"Unsupported EMAIL_PROVIDER={settings.email_provider!r}; use sendgrid or smtp")
