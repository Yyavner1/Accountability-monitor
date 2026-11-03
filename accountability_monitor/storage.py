"""Local storage of captures and a small SQLite event log.

Flagged captures are blurred (so the partner sees context, not explicit
detail) and kept; clean captures are deleted immediately. Old flagged
captures are pruned after the retention window.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

log = logging.getLogger("monitor.storage")


def blur_image(src: Path, dst: Path, radius: int = 25) -> bool:
    try:
        from PIL import Image, ImageFilter

        img = Image.open(src).convert("RGB")
        img = img.filter(ImageFilter.GaussianBlur(radius=radius))
        img.save(dst, "JPEG", quality=70)
        return True
    except Exception as exc:  # pragma: no cover - runtime safety
        log.warning("blur failed (%s); keeping original", exc)
        return False


class Store:
    def __init__(self, base_dir: Path, retention_days: int):
        self.base = base_dir
        self.base.mkdir(parents=True, exist_ok=True)
        self.retention_days = int(retention_days)
        self.db_path = self.base / "events.db"
        self._db = sqlite3.connect(self.db_path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " ts REAL, flagged INTEGER, reasons TEXT, image TEXT)"
        )
        self._db.commit()

    def record(self, flagged: bool, reasons: list[str], image: str | None) -> None:
        self._db.execute(
            "INSERT INTO events (ts, flagged, reasons, image) VALUES (?,?,?,?)",
            (time.time(), 1 if flagged else 0, "; ".join(reasons), image or ""),
        )
        self._db.commit()

    def counts_last_24h(self) -> tuple[int, int]:
        cutoff = time.time() - 24 * 3600
        cur = self._db.execute(
            "SELECT COUNT(*), COALESCE(SUM(flagged),0) FROM events WHERE ts >= ?",
            (cutoff,),
        )
        total, flagged = cur.fetchone()
        return int(flagged or 0), int(total or 0)

    def prune(self) -> None:
        cutoff = time.time() - self.retention_days * 24 * 3600
        # Remove old image files still on disk.
        for p in self.base.glob("flagged-*.jpg"):
            if p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
        self._db.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
        self._db.commit()
