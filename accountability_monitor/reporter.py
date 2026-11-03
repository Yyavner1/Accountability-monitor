"""Optional reporting of events to a hosted backend (the SaaS direction).

If `server_url` and `device_api_key` are set in the config, the agent also
reports flagged events, capture failures, and heartbeats to the backend, so
a partner can view them in the dashboard. Email still works independently; a
backend is additive, not required.

Uses only the standard library (urllib) to avoid adding a dependency.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import urllib.request
import uuid
from pathlib import Path

log = logging.getLogger("monitor.reporter")


def _encode_multipart(fields: dict[str, str], image: Path | None):
    boundary = uuid.uuid4().hex
    buf = io.BytesIO()

    def w(s: str) -> None:
        buf.write(s.encode())

    for name, value in fields.items():
        w(f"--{boundary}\r\n")
        w(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
        w(f"{value}\r\n")

    if image is not None and image.exists():
        ctype = mimetypes.guess_type(str(image))[0] or "image/jpeg"
        w(f"--{boundary}\r\n")
        w(
            'Content-Disposition: form-data; name="image"; '
            f'filename="{image.name}"\r\n'
        )
        w(f"Content-Type: {ctype}\r\n\r\n")
        buf.write(image.read_bytes())
        w("\r\n")

    w(f"--{boundary}--\r\n")
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


class Reporter:
    def __init__(self, server_url: str, api_key: str):
        self.base = server_url.rstrip("/")
        self.api_key = api_key

    @property
    def enabled(self) -> bool:
        return bool(self.base and self.api_key)

    def _post(self, path: str, body: bytes, content_type: str) -> bool:
        req = urllib.request.Request(
            f"{self.base}{path}", data=body, method="POST"
        )
        req.add_header("X-API-Key", self.api_key)
        req.add_header("Content-Type", content_type)
        try:
            urllib.request.urlopen(req, timeout=20).read()
            return True
        except Exception as exc:  # pragma: no cover - network dependent
            log.warning("report to backend failed: %s", exc)
            return False

    def report_event(
        self, kind: str, reasons: list[str], score: float, image: Path | None
    ) -> bool:
        if not self.enabled:
            return False
        fields = {"kind": kind, "reasons": "; ".join(reasons), "score": str(score)}
        body, ctype = _encode_multipart(fields, image)
        return self._post("/api/events", body, ctype)

    def heartbeat(self) -> bool:
        if not self.enabled:
            return False
        body, ctype = _encode_multipart({}, None)
        return self._post("/api/heartbeat", body, ctype)
