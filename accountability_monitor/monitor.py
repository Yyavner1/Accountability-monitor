"""Main loop for the accountability monitor.

While the device is in use, capture the screen on an interval, classify it
on-device, and act on the result:
  * clean  -> delete the capture, log the event, heartbeat;
  * flagged -> blur and keep the capture, send an immediate (rate-limited)
    alert to the partner, log the event.
Once a day, send a summary. An external heartbeat (healthchecks.io) lets the
partner be warned if the agent ever stops checking in.

Run:  python3 -m accountability_monitor.monitor --config /path/to/config.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

from . import capture, storage
from .classifier import Classifier
from .emailer import Emailer
from .reporter import Reporter

log = logging.getLogger("monitor")


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def load_config(path: Path) -> dict:
    with open(path) as f:
        cfg = json.load(f)
    required = ["partner_email", "sender_email", "smtp_password"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise SystemExit(f"config missing required keys: {', '.join(missing)}")
    return cfg


def heartbeat(url: str) -> None:
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=10).read()
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("heartbeat failed: %s", exc)


class Monitor:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.interval = int(cfg.get("capture_interval_seconds", 120))
        self.idle_threshold = float(cfg.get("idle_threshold_seconds", 60))
        self.alert_cooldown = int(cfg.get("alert_cooldown_seconds", 900))
        self.blur = bool(cfg.get("blur_flagged_captures", True))
        self.summary_hour = int(cfg.get("daily_summary_hour", 21))
        self.healthcheck_url = cfg.get("healthcheck_url", "")

        self.capture_dir = _expand(cfg["screenshot_dir"])
        self.store = storage.Store(self.capture_dir, cfg.get("retention_days", 14))
        self.classifier = Classifier(
            cfg.get("nsfw_score_threshold", 0.80), cfg.get("keywords", [])
        )
        self.emailer = Emailer(
            sender_email=cfg["sender_email"],
            smtp_password=cfg["smtp_password"],
            partner_email=cfg["partner_email"],
            smtp_host=cfg.get("smtp_host", "smtp.gmail.com"),
            smtp_port=cfg.get("smtp_port", 465),
        )
        self.reporter = Reporter(
            cfg.get("server_url", ""), cfg.get("device_api_key", "")
        )
        self.capture_failure_threshold = int(
            cfg.get("capture_failure_threshold", 3)
        )
        self._last_alert = 0.0
        self._last_summary_day = None
        self._capture_failures = 0
        self._last_capture_fail_alert = 0.0

    def _handle_flagged(self, shot: Path, reasons: list[str]) -> Path:
        kept: Path = shot
        if self.blur:
            blurred = self.capture_dir / f"flagged-{shot.name}"
            if storage.blur_image(shot, blurred):
                shot.unlink(missing_ok=True)
                kept = blurred
        else:
            kept = self.capture_dir / f"flagged-{shot.name}"
            shot.rename(kept)
        self.store.record(True, reasons, str(kept))
        log.info("FLAGGED: %s", "; ".join(reasons))

        now = time.time()
        if now - self._last_alert >= self.alert_cooldown:
            if self.emailer.send_alert(reasons, str(kept)):
                self._last_alert = now
        return kept

    def _handle_clean(self, shot: Path) -> None:
        self.store.record(False, [], None)
        shot.unlink(missing_ok=True)

    def _maybe_summary(self) -> None:
        now = time.localtime()
        day = time.strftime("%Y-%m-%d", now)
        if now.tm_hour == self.summary_hour and self._last_summary_day != day:
            flagged, total = self.store.counts_last_24h()
            if self.emailer.send_summary(flagged, total):
                self._last_summary_day = day
            self.store.prune()

    def _handle_capture_failure(self) -> None:
        """A capture failed or came back blank (e.g. permission revoked).

        We do NOT heartbeat, so the external watchdog also fires, and after a
        few consecutive failures we email the partner directly.
        """
        self._capture_failures += 1
        log.warning(
            "capture invalid (%d consecutive); not sending heartbeat",
            self._capture_failures,
        )
        if self._capture_failures < self.capture_failure_threshold:
            return
        now = time.time()
        if now - self._last_capture_fail_alert >= self.alert_cooldown:
            if self.emailer.send_capture_failure(self._capture_failures):
                self._last_capture_fail_alert = now
            self.reporter.report_event(
                "capture_failure",
                [f"{self._capture_failures} consecutive blank/failed captures"],
                0.0,
                None,
            )

    def tick(self) -> None:
        self._maybe_summary()

        # An idle machine is healthy and correctly not capturing, so keep the
        # heartbeat alive to avoid false tamper alerts (e.g. overnight).
        if not capture.device_in_use(self.idle_threshold):
            log.debug("device idle; skipping capture")
            heartbeat(self.healthcheck_url)
            return

        shot = capture.take_screenshot(self.capture_dir)
        if not shot or not capture.capture_looks_valid(shot):
            if shot:
                shot.unlink(missing_ok=True)
            self._handle_capture_failure()
            return

        # Valid capture: the monitor can see the screen. Reset the failure
        # counter, classify, act, and only now confirm the heartbeat.
        self._capture_failures = 0
        verdict = self.classifier.classify(str(shot))
        if verdict.flagged:
            kept = self._handle_flagged(shot, verdict.reasons)
            self.reporter.report_event(
                "flagged", verdict.reasons, verdict.top_score, kept
            )
        else:
            self._handle_clean(shot)
        heartbeat(self.healthcheck_url)
        self.reporter.heartbeat()

    def run(self) -> None:
        log.info("accountability monitor started (interval=%ss)", self.interval)
        while True:
            try:
                self.tick()
            except Exception as exc:  # keep the loop alive no matter what
                log.exception("tick failed: %s", exc)
            time.sleep(self.interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accountability screen monitor")
    parser.add_argument("--config", required=True, help="path to config.json")
    parser.add_argument("--once", action="store_true", help="run one tick and exit")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    cfg = load_config(_expand(args.config))
    mon = Monitor(cfg)
    if args.once:
        mon.tick()
        return 0
    mon.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
