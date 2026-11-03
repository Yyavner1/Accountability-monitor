"""Screen capture and activity detection for macOS, Windows, and Linux.

The agent only captures while the device is in use, so each platform needs a
way to grab every display and a way to read how long it has been since the
last keyboard or mouse input.

  macOS    capture: built-in `screencapture`   idle: ioreg HIDIdleTime
  Windows  capture: mss                         idle: GetLastInputInfo
  Linux    capture: mss (X11) / grim (Wayland)  idle: xprintidle, else active
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("monitor.capture")

if sys.platform == "darwin":
    PLATFORM = "macos"
elif sys.platform.startswith("win"):
    PLATFORM = "windows"
else:
    PLATFORM = "linux"


# --- idle time -------------------------------------------------------------

_HID_IDLE_RE = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def _idle_macos() -> float:
    out = subprocess.check_output(
        ["ioreg", "-c", "IOHIDSystem"], text=True, timeout=10
    )
    values = [int(m) for m in _HID_IDLE_RE.findall(out)]
    if not values:
        return 0.0
    # HIDIdleTime is in nanoseconds; the smallest is the most recent input.
    return min(values) / 1_000_000_000


def _idle_windows() -> float:
    import ctypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    millis_now = ctypes.windll.kernel32.GetTickCount()
    return max(0.0, (millis_now - info.dwTime) / 1000.0)


def _idle_linux() -> float:
    # xprintidle reports milliseconds of idle time under X11.
    if shutil.which("xprintidle"):
        try:
            out = subprocess.check_output(["xprintidle"], text=True, timeout=10)
            return int(out.strip()) / 1000.0
        except Exception as exc:  # pragma: no cover - runtime safety
            log.warning("xprintidle failed: %s", exc)
    # No reliable idle source (e.g. Wayland): treat the device as in use.
    return 0.0


def seconds_since_input() -> float:
    """Seconds since the last keyboard/mouse input. 0.0 means 'assume active'."""
    try:
        if PLATFORM == "macos":
            return _idle_macos()
        if PLATFORM == "windows":
            return _idle_windows()
        return _idle_linux()
    except Exception as exc:  # pragma: no cover - runtime safety
        log.warning("could not read idle time (%s); assuming active", exc)
        return 0.0


def device_in_use(idle_threshold_seconds: float) -> bool:
    return seconds_since_input() < idle_threshold_seconds


# --- capture ---------------------------------------------------------------

def _capture_macos(out: Path) -> bool:
    # -x: no sound. -t jpg: JPEG. Captures all displays.
    subprocess.check_call(["screencapture", "-x", "-t", "jpg", str(out)], timeout=30)
    return out.exists() and out.stat().st_size > 0


def _capture_mss(out: Path) -> bool:
    # Cross-platform grab of all monitors into one image (Windows and X11).
    import mss
    import mss.tools
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[0])  # monitors[0] is the full virtual screen
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        img.save(out, "JPEG", quality=70)
    return out.exists() and out.stat().st_size > 0


def _capture_linux(out: Path) -> bool:
    # Wayland blocks mss, so prefer native tools when present; fall back to mss.
    if shutil.which("grim"):  # Wayland
        subprocess.check_call(["grim", "-t", "jpeg", str(out)], timeout=30)
        return out.exists() and out.stat().st_size > 0
    if shutil.which("gnome-screenshot"):
        subprocess.check_call(["gnome-screenshot", "-f", str(out)], timeout=30)
        return out.exists() and out.stat().st_size > 0
    return _capture_mss(out)


def capture_looks_valid(path: Path) -> bool:
    """True if the capture looks like a real screen, not a blank/black frame.

    When screen-recording permission is revoked (e.g. on macOS), capture can
    still produce a file, but it is near-uniform (all one color). We treat a
    near-uniform image as an invalid capture so the caller can react to it as
    a tamper signal rather than silently logging black frames as "clean".
    """
    try:
        from PIL import Image, ImageStat

        with Image.open(path) as im:
            stat = ImageStat.Stat(im.convert("L"))
        # stddev of luminance; a real screen has structure, a blank frame ~0.
        return stat.stddev[0] >= 3.0
    except Exception as exc:  # pragma: no cover - runtime safety
        log.warning("could not validate capture (%s); assuming valid", exc)
        return True


def take_screenshot(dest_dir: Path) -> Path | None:
    """Capture all displays into a single JPEG. Returns the path or None."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = dest_dir / f"capture-{stamp}.jpg"
    try:
        if PLATFORM == "macos":
            ok = _capture_macos(out)
        elif PLATFORM == "windows":
            ok = _capture_mss(out)
        else:
            ok = _capture_linux(out)
    except Exception as exc:  # pragma: no cover - runtime safety
        log.error("screen capture failed: %s", exc)
        return None
    return out if ok else None
