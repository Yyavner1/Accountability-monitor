"""Outbound email for the server (verification, password reset).

If SMTP is configured it sends mail; otherwise it logs the message and link
to the server console, which is enough for local development. This keeps the
app fully runnable without an email provider.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("notify")


def send(to: str, subject: str, body: str) -> bool:
    if not settings.smtp_host:
        log.warning("[email not configured] To:%s | %s\n%s", to, subject, body)
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=ctx,
                              timeout=30) as s:
            s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(msg)
        return True
    except Exception as exc:  # pragma: no cover - network dependent
        log.error("failed to send mail to %s: %s", to, exc)
        return False
