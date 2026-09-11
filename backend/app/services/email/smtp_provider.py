"""SMTP provider (Gmail App Password via STARTTLS by default).

Credentials come exclusively from the environment (SMTP_HOST / SMTP_PORT /
SMTP_USERNAME / SMTP_PASSWORD / EMAIL_FROM) and never leave the backend."""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr, formatdate, make_msgid

from ...config import settings
from .base import EmailMessage, EmailProvider, EmailResult

log = logging.getLogger("thermoshield.email.smtp")


class SMTPProvider(EmailProvider):
    name = "smtp"

    def configured(self) -> bool:
        return settings.smtp_configured

    def send(self, message: EmailMessage) -> EmailResult:
        if not self.configured():
            return EmailResult(status="not_configured", detail="SMTP credentials not configured (SMTP_USERNAME / SMTP_PASSWORD)", provider=self.name)
        msg = MimeMessage()
        msg["From"] = formataddr(("Thermo-Shield India", settings.email_sender))
        msg["To"] = ", ".join(message.to)
        msg["Subject"] = message.subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain="thermoshield.local")
        for k, v in message.headers.items():
            msg[k] = v
        msg.set_content(message.text)
        if message.html:
            msg.add_alternative(message.html, subtype="html")
        try:
            if settings.smtp_port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=ssl.create_default_context()) as s:
                    s.login(settings.smtp_username, settings.smtp_password)
                    s.send_message(msg)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as s:
                    s.ehlo()
                    if settings.smtp_use_tls:
                        s.starttls(context=ssl.create_default_context())
                        s.ehlo()
                    s.login(settings.smtp_username, settings.smtp_password)
                    s.send_message(msg)
            return EmailResult(status="sent", detail=f"delivered to {len(message.to)} recipient(s) via {settings.smtp_host}", provider=self.name)
        except Exception as exc:
            log.error("SMTP send failed: %s", exc)
            return EmailResult(status="failed", detail=str(exc), provider=self.name)


class LogOnlyProvider(EmailProvider):
    """Development helper: writes the message to the log instead of sending.
    Enabled only with EMAIL_DEV_LOG_ONLY=true; never used when SMTP is configured."""

    name = "log-only"
    last_messages: list[EmailMessage] = []

    def configured(self) -> bool:
        return settings.email_dev_log_only

    def send(self, message: EmailMessage) -> EmailResult:
        LogOnlyProvider.last_messages.append(message)
        LogOnlyProvider.last_messages = LogOnlyProvider.last_messages[-50:]
        log.warning("[EMAIL_DEV_LOG_ONLY] To: %s | Subject: %s\n%s", message.to, message.subject, message.text)
        return EmailResult(status="logged", detail="EMAIL_DEV_LOG_ONLY=true - message written to server log, nothing sent", provider=self.name)
