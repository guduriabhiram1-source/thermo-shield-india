"""E-mail service facade: verification e-mails + live alert e-mails.

Provider selection: SMTP when configured, otherwise the log-only provider when
EMAIL_DEV_LOG_ONLY=true, otherwise `not_configured` (nothing is faked)."""
from __future__ import annotations

import html
import logging

from ..config import settings
from .email.base import EmailMessage, EmailProvider, EmailResult
from .email.smtp_provider import LogOnlyProvider, SMTPProvider

log = logging.getLogger("thermoshield.email")
_providers: list[EmailProvider] = [SMTPProvider(), LogOnlyProvider()]
_override: EmailProvider | None = None  # tests inject a capturing provider


def set_provider_override(provider: EmailProvider | None) -> None:
    global _override
    _override = provider


def active_provider() -> EmailProvider | None:
    if _override is not None:
        return _override
    for p in _providers:
        if p.configured():
            return p
    return None


def email_status() -> dict:
    p = active_provider()
    return {"configured": p is not None and p.name != "log-only", "provider": p.name if p else "none",
            "smtp_host": settings.smtp_host if settings.smtp_configured else None,
            "sender": settings.email_sender if settings.smtp_configured else None,
            "dev_log_only": settings.email_dev_log_only and not settings.smtp_configured}


def send_email(to: list[str], subject: str, text: str, html_body: str | None = None) -> EmailResult:
    p = active_provider()
    if p is None:
        return EmailResult(status="not_configured", detail="No e-mail provider configured (set SMTP_* in .env)", provider="none")
    return p.send(EmailMessage(to=to, subject=subject, text=text, html=html_body))


def verification_email(to: str, code: str, purpose: str = "signup") -> EmailResult:
    minutes = settings.verification_code_expire_minutes
    title = "Verify your e-mail address" if purpose == "signup" else "Your verification code"
    text = (
        f"THERMO-SHIELD INDIA\n{title}\n\n"
        f"Your verification code is: {code}\n\n"
        f"Enter this code in the Thermo-Shield India verification screen to activate your account.\n"
        f"The code expires in {minutes} minutes.\n\n"
        f"If you did not request this, ignore this e-mail.\n\n"
        f"Verification page: {settings.frontend_url.rstrip('/')}/verify-email?email={to}\n"
    )
    html_body = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;border:1px solid #e2e8f0;border-radius:12px;padding:24px">
      <div style="font-size:12px;letter-spacing:.2em;color:#b91c1c;font-weight:700">THERMO-SHIELD INDIA</div>
      <h2 style="margin:8px 0 16px;color:#0f172a">{html.escape(title)}</h2>
      <p style="color:#334155">Enter this code in the verification screen to activate your account:</p>
      <div style="font-size:32px;letter-spacing:.35em;font-weight:800;color:#0f172a;background:#f1f5f9;padding:14px 18px;border-radius:10px;text-align:center">{code}</div>
      <p style="color:#64748b;font-size:13px;margin-top:16px">The code expires in {minutes} minutes. If you did not request this, ignore this e-mail.</p>
      <p style="font-size:13px"><a href="{html.escape(settings.frontend_url.rstrip('/'))}/verify-email?email={html.escape(to)}">Open the verification page</a></p>
    </div>"""
    return send_email([to], f"[THERMO-SHIELD INDIA] Your verification code: {code}", text, html_body)
