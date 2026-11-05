"""Email delivery over SMTP (Gmail app password by default).

Sends two kinds of mail to the accountability partner:
  * an immediate alert when a capture is flagged (with the blurred image
    attached), rate-limited by a cooldown so one bad session is not a flood;
  * a daily summary counting flagged captures over the last 24h.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

log = logging.getLogger("monitor.emailer")


class Emailer:
    def __init__(
        self,
        sender_email: str,
        smtp_password: str,
        partner_email: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 465,
    ):
        self.sender = sender_email
        self.password = smtp_password
        self.partner = partner_email
        self.host = smtp_host
        self.port = int(smtp_port)

    def _send(self, msg: EmailMessage) -> bool:
        msg["From"] = self.sender
        msg["To"] = self.partner
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=30) as s:
                s.login(self.sender, self.password)
                s.send_message(msg)
            log.info("sent mail: %s", msg["Subject"])
            return True
        except Exception as exc:  # pragma: no cover - network dependent
            log.error("failed to send mail: %s", exc)
            return False

    def send_test(self) -> tuple[bool, str]:
        """Send a test email, returning (ok, error). Unlike the other senders,
        this surfaces the real SMTP error so the settings page can show it."""
        msg = EmailMessage()
        msg["From"] = self.sender
        msg["To"] = self.partner
        msg["Subject"] = "Accountability Monitor: test email"
        msg.set_content(
            "This is a test from your Accountability Monitor settings page.\n"
            "If you received this, your email is set up correctly."
        )
        try:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=30) as s:
                s.login(self.sender, self.password)
                s.send_message(msg)
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def send_alert(self, reasons: list[str], image_path: str | None) -> bool:
        msg = EmailMessage()
        msg["Subject"] = "Accountability alert: flagged activity"
        body = (
            "The accountability monitor flagged on-screen activity.\n\n"
            "Reasons:\n" + "\n".join(f"  - {r}" for r in reasons) + "\n\n"
            "A blurred screenshot is attached for context."
        )
        msg.set_content(body)
        if image_path and Path(image_path).exists():
            data = Path(image_path).read_bytes()
            msg.add_attachment(
                data, maintype="image", subtype="jpeg",
                filename=Path(image_path).name,
            )
        return self._send(msg)

    def send_summary(self, flagged_count: int, total_captures: int) -> bool:
        msg = EmailMessage()
        if flagged_count == 0:
            msg["Subject"] = "Accountability summary: all clear"
            body = (
                f"No flagged activity in the last 24 hours.\n"
                f"{total_captures} captures were checked."
            )
        else:
            msg["Subject"] = f"Accountability summary: {flagged_count} flagged"
            body = (
                f"{flagged_count} of {total_captures} captures were flagged "
                f"in the last 24 hours.\n"
                "Immediate alerts were sent as they happened."
            )
        msg.set_content(body)
        return self._send(msg)

    def send_capture_failure(self, consecutive: int) -> bool:
        msg = EmailMessage()
        msg["Subject"] = "Accountability monitor: screen capture stopped working"
        msg.set_content(
            "The accountability monitor is running but has not produced a "
            f"valid screen capture in {consecutive} consecutive checks.\n\n"
            "This usually means Screen Recording permission was turned off, "
            "or the screen is being captured as blank. The monitor cannot "
            "see the screen until this is restored."
        )
        return self._send(msg)

    def send_filter_tampered(self) -> bool:
        msg = EmailMessage()
        msg["Subject"] = "Accountability monitor: website filter was removed"
        msg.set_content(
            "The system-wide website filter is no longer present in the hosts "
            "file. It may have been edited or removed. Blocked sites can load "
            "again until it is restored."
        )
        return self._send(msg)

    def send_heartbeat_warning(self) -> bool:
        """Sent by an external watchdog, not the agent itself."""
        msg = EmailMessage()
        msg["Subject"] = "Accountability monitor: monitoring went quiet"
        msg.set_content(
            "The accountability monitor stopped checking in. It may have "
            "been stopped, uninstalled, or the machine may be off."
        )
        return self._send(msg)
