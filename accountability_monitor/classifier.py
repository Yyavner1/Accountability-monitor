"""On-device classification of screenshots.

Two independent signals:
  1. Image NSFW detection via NudeNet (ONNX, runs on CPU, no network).
  2. On-screen text OCR (best-effort) matched against a keyword list.

A capture is flagged if either signal fires. Everything runs locally; no
image or text ever leaves the machine during classification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

log = logging.getLogger("monitor.classifier")

# Parts that indicate explicit nudity. NudeNet returns many labels; we only
# treat the explicitly sexual ones as positive signal.
_EXPLICIT_LABELS = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
}


@dataclass
class Verdict:
    flagged: bool = False
    reasons: list[str] = field(default_factory=list)
    top_score: float = 0.0

    def add(self, reason: str, score: float = 0.0) -> None:
        self.flagged = True
        self.reasons.append(reason)
        self.top_score = max(self.top_score, score)


class Classifier:
    def __init__(self, nsfw_threshold: float, keywords: list[str]):
        self.nsfw_threshold = float(nsfw_threshold)
        self.keywords = [k.lower() for k in keywords if k.strip()]
        self._detector = None
        self._ocr_ready = None  # tri-state: None = untried, True/False after

    # --- image ----------------------------------------------------------
    def _get_detector(self):
        if self._detector is None:
            from nudenet import NudeDetector  # lazy import; heavy

            self._detector = NudeDetector()
            log.info("NudeNet detector loaded")
        return self._detector

    def _check_image(self, image_path: str, verdict: Verdict) -> None:
        try:
            detections = self._get_detector().detect(image_path)
        except Exception as exc:  # pragma: no cover - runtime safety
            log.warning("image classification failed: %s", exc)
            return
        for det in detections:
            label = det.get("class", "")
            score = float(det.get("score", 0.0))
            if label in _EXPLICIT_LABELS and score >= self.nsfw_threshold:
                verdict.add(f"image:{label.lower()} ({score:.2f})", score)

    # --- text ------------------------------------------------------------
    def _check_text(self, image_path: str, verdict: Verdict) -> None:
        if not self.keywords:
            return
        text = self._ocr(image_path)
        if not text:
            return
        low = text.lower()
        for kw in self.keywords:
            if kw in low:
                verdict.add(f"keyword:{kw}")

    def _ocr(self, image_path: str) -> str:
        if self._ocr_ready is False:
            return ""
        try:
            import pytesseract  # optional dependency
            from PIL import Image

            self._ocr_ready = True
            return pytesseract.image_to_string(Image.open(image_path))
        except Exception as exc:
            if self._ocr_ready is None:
                log.info("OCR unavailable (%s); keyword matching disabled", exc)
            self._ocr_ready = False
            return ""

    # --- public ----------------------------------------------------------
    def classify(self, image_path: str) -> Verdict:
        verdict = Verdict()
        self._check_image(image_path, verdict)
        self._check_text(image_path, verdict)
        return verdict
