# Accountability Monitor

A self-hosted accountability tool you install on your own computers
(macOS, Windows, and Linux). While the device is in use, it captures the
screen on an interval, checks each capture **on-device** for explicit
material, and emails an accountability partner: an immediate (rate-limited)
alert when something is flagged, and a daily summary. An autostart service
keeps it running and restarts it if it stops; a free external heartbeat
warns your partner if monitoring ever goes quiet.

This is consent-based self-monitoring. You install it on machines you own
and control, and you choose who receives the reports.

## How it works

```
                while the device is in use
  screen capture ──► classify on-device ──► clean  ─► delete + log
   (all displays)      • NudeNet (image)      flagged ─► blur + keep
                       • OCR keywords (text)            + email partner
                                                        + log
        every loop ─► heartbeat ping (healthchecks.io)
        once a day ─► summary email + prune old captures
```

- **Capture** (all displays), per platform:
  - macOS: built-in `screencapture` (silent).
  - Windows: `mss`.
  - Linux: `grim` or `gnome-screenshot` on Wayland, else `mss` on X11.
- **In-use detection** so an idle machine is not captured:
  - macOS: `ioreg` HIDIdleTime. Windows: `GetLastInputInfo`.
  - Linux: `xprintidle` on X11; on Wayland it assumes active.
- **Classification:** [NudeNet](https://pypi.org/project/nudenet/) for
  explicit imagery, plus optional OCR keyword matching for known sites.
  Everything runs locally; captures never leave the machine during analysis.
- **Storage:** clean captures are deleted at once; flagged ones are blurred
  (context without explicit detail) and kept for `retention_days`.
- **Delivery:** SMTP (Gmail App Password by default).
- **Resilience:** an autostart service (launchd / Task Scheduler / systemd)
  restarts the monitor if it exits. Because you are an admin on your own
  machine, no local process can be made truly unremovable — the external
  heartbeat is what makes tampering visible: if the agent stops pinging,
  healthchecks.io emails your partner.
- **Tamper detection:** the heartbeat is only sent after a capture that
  actually worked. If the agent is stopped or removed, pings stop. If screen
  capture is disabled or comes back blank (e.g. Screen Recording permission
  revoked), the agent detects the blank frames, stops pinging (so the
  heartbeat still fires), and also emails the partner directly after
  `capture_failure_threshold` consecutive bad captures. An idle machine keeps
  pinging normally, so an unattended computer does not raise a false alarm.

## Blocking (proactive)

Detection above is after-the-fact. Two optional layers block content before
or as it appears. No layer is perfect; together they block most of it and the
screenshot monitor remains the backstop for the rest.

- **Website filter** ([`blocklist.txt`](blocklist.txt), `blocker.py`): writes
  known adult domains into the system hosts file so they never load in any
  browser or app. Apply it with admin rights:

  ```bash
  sudo ./install_filter.sh                 # macOS / Linux
  # Windows (elevated): .\install_filter.ps1
  ```

  Pass a URL to pull a large maintained list (e.g. StevenBlack's hosts). With
  `watch_site_filter` enabled, the agent alerts the partner if the filter is
  later removed. The filter can be bypassed by an admin or by browser
  DNS-over-HTTPS, which is why tampering is reported.

- **Browser extension** ([`extension/`](extension/)): blurs explicit images
  and video frames on-device as pages render, catching content on sites that
  aren't blocked outright. See [`extension/README.md`](extension/README.md).

## Install

```bash
git clone https://github.com/yyavner1/accountability-monitor
cd accountability-monitor
```

Then, on each machine:

| OS | command |
|---|---|
| macOS | `./install.sh` |
| Linux | `./install_linux.sh` |
| Windows | `powershell -ExecutionPolicy Bypass -File .\install_windows.ps1` |

Each installer creates a virtual environment, installs dependencies, writes
`config.json`, and registers an autostart service. Then edit `config.json`
(partner email, your Gmail + App Password) and restart the service. The
installer prints the exact paths and restart command for your platform.

On macOS you must also grant **Screen Recording** permission to the venv's
Python (System Settings → Privacy & Security → Screen Recording), or
captures come out black.

## Configuration

See [`config.example.json`](config.example.json). Key fields:

| key | meaning |
|---|---|
| `partner_email` | who receives alerts and summaries |
| `sender_email` / `smtp_password` | your Gmail + App Password |
| `capture_interval_seconds` | seconds between captures (default 120) |
| `idle_threshold_seconds` | skip capture after this much idle time |
| `nsfw_score_threshold` | 0–1 confidence to flag an image |
| `keywords` | lowercase substrings matched against on-screen text |
| `blur_flagged_captures` | blur kept captures (recommended) |
| `alert_cooldown_seconds` | minimum gap between alert emails |
| `capture_failure_threshold` | blank/failed captures in a row before a tamper email |
| `healthcheck_url` | healthchecks.io ping URL (tamper alert) |
| `watch_site_filter` | alert the partner if the website filter is removed |

## Run manually (for testing)

From the install directory's venv:

```bash
python3 -m accountability_monitor.monitor --config /path/to/config.json --once --verbose
```

## Limitations

- An administrator of the machine can stop or remove any local agent. The
  heartbeat makes that visible to the partner rather than preventing it.
- OCR keyword matching requires the `tesseract` binary; without it, image
  classification still works.
- On Linux under Wayland, reliable idle detection isn't available, so the
  agent captures on every interval regardless of activity.
- iPhone/iPad are not supported: iOS does not let an app capture other apps
  in the background.
- On-device detection favors privacy over catching every borderline case.

## Roadmap

- Deploy the backend (HTTPS, Postgres), invite emails, billing.
- Self-healing website filter (privileged helper re-applies if removed).
- Optional cloud second-opinion classifier for borderline captures.
- Android companion app.
