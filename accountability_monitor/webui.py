"""Local settings page for the agent.

Serves a small web page on 127.0.0.1 so the user can configure the agent in
their browser instead of editing config.json by hand. It binds to localhost
only, reads and writes the same config.json the agent uses, and shows simple
status (last check, flagged counts). Nothing is sent anywhere; this is purely
a local control panel.

Run:  python3 -m accountability_monitor.webui --config /path/to/config.json
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sqlite3
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Fields shown on the page: (key, label, kind, default).
FIELDS = [
    ("partner_email", "Partner's email (gets the reports)", "email", ""),
    ("sender_email", "Your email (sends the reports)", "email", ""),
    ("smtp_password", "Email app password", "password", ""),
    ("summary_frequency", "Summary email", "freq", "daily"),
    ("capture_interval_seconds", "Seconds between checks", "number", 120),
    ("nsfw_score_threshold", "Sensitivity (0–1, lower = stricter)", "number", 0.80),
    ("blur_flagged_captures", "Blur flagged screenshots", "bool", True),
    ("watch_site_filter", "Alert if the website filter is removed", "bool", True),
    ("healthcheck_url", "Heartbeat URL (optional)", "url", ""),
]


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def load_config(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def save_config(path: Path, cfg: dict) -> None:
    path.write_text(json.dumps(cfg, indent=2) + "\n")


def _status(cfg: dict) -> str:
    """A short status line from the agent's local event database."""
    try:
        base = _expand(cfg.get("screenshot_dir", "."))
        db = base / "events.db"
        if not db.exists():
            return "No activity recorded yet."
        con = sqlite3.connect(db)
        last = con.execute("SELECT MAX(ts) FROM events").fetchone()[0]
        flagged, total = con.execute(
            "SELECT COALESCE(SUM(flagged),0), COUNT(*) FROM events "
            "WHERE ts >= ?", (time.time() - 24 * 3600,)
        ).fetchone()
        con.close()
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(last)) if last else "never"
        return f"Last check: {when}. Last 24h: {flagged} flagged of {total} checks."
    except Exception:
        return "Status unavailable."


def render(cfg: dict, saved: bool) -> str:
    rows = []
    for key, label, kind, default in FIELDS:
        val = cfg.get(key, default)
        lbl = html.escape(label)
        if kind == "bool":
            checked = "checked" if val else ""
            field = (f'<input type="checkbox" name="{key}" value="1" {checked}>')
            rows.append(f'<p><label>{field} {lbl}</label></p>')
        elif kind == "freq":
            opts = "".join(
                f'<option value="{o}"{" selected" if val==o else ""}>{o}</option>'
                for o in ("daily", "weekly", "off")
            )
            rows.append(f'<p><label>{lbl}<br><select name="{key}">{opts}</select></label></p>')
        else:
            t = {"password": "password", "number": "text", "email": "email",
                 "url": "url"}.get(kind, "text")
            v = html.escape(str(val))
            rows.append(
                f'<p><label>{lbl}<br>'
                f'<input type="{t}" name="{key}" value="{v}" style="width:100%"></label></p>'
            )
    banner = ('<div class="ok">Saved. Restart the agent for changes to take '
              'full effect.</div>' if saved else "")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Accountability Monitor — Settings</title>
<style>
 body{{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:560px;
   margin:0 auto;padding:24px 16px;color:#1a1a1a;background:#fff}}
 @media(prefers-color-scheme:dark){{body{{background:#131316;color:#e7e7e9}}
   input,select{{background:#1d1d22;color:#e7e7e9;border-color:#333}}}}
 h1{{font-size:19px}} .mut{{color:#777}}
 input,select{{padding:9px 10px;border:1px solid #ccc;border-radius:8px;font:inherit}}
 button{{background:#2563eb;color:#fff;border:0;border-radius:8px;padding:11px 18px;
   font:inherit;cursor:pointer}}
 .ok{{background:#dcfce7;color:#166534;padding:10px 12px;border-radius:8px;margin:10px 0}}
 .card{{border:1px solid #e4e4e7;border-radius:10px;padding:14px;margin:12px 0}}
</style></head><body>
<h1>Accountability Monitor</h1>
<p class="mut">{html.escape(_status(cfg))}</p>
{banner}
<form method="post" action="/save" class="card">
{''.join(rows)}
<p><button type="submit">Save settings</button>
   <a href="/test" style="margin-left:10px">Send test email</a></p>
</form>
<p class="mut">This page runs only on your computer. Nothing here is sent
anywhere except the emails you configure.</p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    config_path: Path = Path("config.json")

    def _send(self, body: str, code: int = 200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/test"):
            self._handle_test()
            return
        cfg = load_config(self.config_path)
        saved = self.path.startswith("/?saved=1")
        self._send(render(cfg, saved))

    def do_POST(self):
        if not self.path.startswith("/save"):
            self._send("not found", 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode()
        form = urllib.parse.parse_qs(raw)
        cfg = load_config(self.config_path)
        for key, _label, kind, _default in FIELDS:
            if kind == "bool":
                cfg[key] = key in form  # checkbox present = on
            elif key in form:
                v = form[key][0].strip()
                if kind == "number":
                    try:
                        cfg[key] = float(v) if "." in v else int(v)
                    except ValueError:
                        pass
                else:
                    cfg[key] = v
        save_config(self.config_path, cfg)
        self.send_response(303)
        self.send_header("Location", "/?saved=1")
        self.end_headers()

    def _handle_test(self):
        cfg = load_config(self.config_path)
        msg = "Test email not sent."
        try:
            from .emailer import Emailer

            e = Emailer(
                sender_email=cfg.get("sender_email", ""),
                smtp_password=cfg.get("smtp_password", ""),
                partner_email=cfg.get("partner_email", ""),
                smtp_host=cfg.get("smtp_host", "smtp.gmail.com"),
                smtp_port=cfg.get("smtp_port", 465),
            )
            ok, err = e.send_test()
            if ok:
                msg = "Test email sent — check the partner inbox."
            else:
                low = err.lower()
                if ("username and password not accepted" in low
                        or "5.7.8" in low or "authentication" in low
                        or "badcredentials" in low):
                    msg = ("Gmail rejected the sign-in. Make sure you used a 16-character "
                           "Gmail App Password (not your normal password), that 2-Step "
                           "Verification is turned on for that Google account, and that "
                           "the sender email matches it. Details: " + err)
                else:
                    msg = "Could not send: " + err
        except Exception as exc:
            msg = f"Could not send: {exc}"
        self._send(
            f'<!doctype html><meta charset="utf-8"><body style="font-family:'
            f'system-ui;max-width:560px;margin:40px auto;padding:0 16px">'
            f'<p>{html.escape(msg)}</p><p><a href="/">Back to settings</a></p>'
        )

    def log_message(self, *args):  # silence console noise
        pass


def make_server(config_path: Path, port: int) -> ThreadingHTTPServer:
    Handler.config_path = config_path
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local settings page")
    parser.add_argument("--config", required=True)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args(argv)

    config_path = _expand(args.config)
    server = make_server(config_path, args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Settings page: {url}  (editing {config_path})")
    if not args.no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
