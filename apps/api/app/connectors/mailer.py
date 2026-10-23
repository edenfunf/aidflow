"""E-mail connector (SMTP) — progress notifications to reporters who asked
for them. Unset SMTP_HOST ⇒ ``is_configured()`` is False and callers record
the message as simulated."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app.connectors.base import ConnectorError
from app.core.config import settings


def is_configured() -> bool:
    return bool(settings.SMTP_HOST)


def send(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="aidflow")
    msg.set_content(body)
    try:
        if settings.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS,
                                  context=ssl.create_default_context()) as s:
                _login_and_send(s, msg)
        else:
            if not settings.SMTP_STARTTLS and not settings.is_development:
                raise ConnectorError("SMTP_STARTTLS 已關閉：拒絕以未加密連線寄送通知信")
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT_SECONDS) as s:
                if settings.SMTP_STARTTLS:
                    s.starttls(context=ssl.create_default_context())
                _login_and_send(s, msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise ConnectorError(f"Email 寄送失敗：{exc}") from exc


def _login_and_send(s: smtplib.SMTP, msg: EmailMessage) -> None:
    if settings.SMTP_USERNAME:
        s.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
    s.send_message(msg)
