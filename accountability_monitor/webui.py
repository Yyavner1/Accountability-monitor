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


# Fields grouped into sections for the page (keys reference FIELDS above).
GROUPS = [
    ("Email reports", "Who gets the reports, and the account they send from.",
     ["partner_email", "sender_email", "smtp_password", "summary_frequency"]),
    ("Detection", "How often it checks and what counts as flagged.",
     ["capture_interval_seconds", "nsfw_score_threshold", "blur_flagged_captures"]),
    ("Extra safeguards", "Optional checks. Leave as-is if you're not sure.",
     ["watch_site_filter", "healthcheck_url"]),
]
_FIELD_BY_KEY = {k: (k, l, kind, d) for (k, l, kind, d) in FIELDS}

# Mirrors the landing page: pine-and-paper palette, Fraunces + IBM Plex, theme-aware.
PAGE_CSS = """
:root{--bg:#f3f1ea;--surface:#fbfaf6;--surface-2:#eceae1;--ink:#1a211c;--muted:#5b675e;
 --line:#ddd9cd;--pine:#12503c;--pine-bright:#1c7a56;--accent-soft:#e2eee6;
 --amber:#9a5a12;--amber-soft:#f3e7d2;--ok:#176a45;--ok-soft:#dcefe3;
 --display:"Fraunces",Georgia,serif;--body:"IBM Plex Sans",system-ui,-apple-system,sans-serif;}
@media(prefers-color-scheme:dark){:root{--bg:#0e120f;--surface:#161b16;--surface-2:#1d231d;
 --ink:#e9ece4;--muted:#9aa89d;--line:#2a312a;--pine:#4fbd90;--pine-bright:#6bd2a6;
 --accent-soft:#15241d;--amber:#e0a856;--amber-soft:#2a2114;--ok:#6bd2a6;--ok-soft:#15241d;
 color-scheme:dark;}}
*{box-sizing:border-box;}
body{background:var(--bg);color:var(--ink);font-family:var(--body);line-height:1.55;
 margin:0;padding:32px max(16px,env(safe-area-inset-left,0)) 56px;-webkit-font-smoothing:antialiased;}
.wrap{max-width:600px;margin:0 auto;}
.head{display:flex;align-items:center;gap:12px;margin-bottom:6px;}
.head svg{width:30px;height:30px;flex:none;}
.head h1{font-family:var(--display);font-weight:600;font-size:24px;margin:0;letter-spacing:-.01em;}
.status{display:inline-flex;align-items:center;gap:8px;background:var(--surface);
 border:1px solid var(--line);border-radius:999px;padding:7px 14px;font-size:13px;
 color:var(--muted);margin:8px 0 22px;}
.status .dot{width:8px;height:8px;border-radius:50%;background:var(--pine-bright);flex:none;}
.banner{display:flex;gap:10px;align-items:flex-start;background:var(--ok-soft);color:var(--ok);
 border-radius:12px;padding:13px 16px;margin-bottom:20px;font-size:14px;font-weight:500;}
.banner svg{width:18px;height:18px;flex:none;margin-top:1px;}
.sect{background:var(--surface);border:1px solid var(--line);border-radius:16px;
 padding:22px 22px 8px;margin-bottom:18px;}
.sect>h2{font-family:var(--display);font-weight:600;font-size:18px;margin:0;letter-spacing:-.01em;}
.sect>.sub{color:var(--muted);font-size:13.5px;margin:4px 0 16px;}
.field{margin-bottom:16px;}
.field label{display:block;font-weight:600;font-size:14px;margin-bottom:6px;}
.field input,.field select{width:100%;padding:11px 12px;border:1px solid var(--line);
 border-radius:10px;font:inherit;font-size:15px;background:var(--bg);color:var(--ink);}
.field input:focus,.field select:focus{outline:2px solid var(--pine-bright);outline-offset:1px;
 border-color:var(--pine-bright);}
.toggle{display:flex;align-items:center;gap:11px;margin-bottom:16px;cursor:pointer;font-size:14px;font-weight:500;}
.toggle input{width:18px;height:18px;accent-color:var(--pine);flex:none;margin:0;}
.actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:4px 0 10px;}
.btn{background:var(--pine);color:#fbfaf6;border:0;border-radius:10px;padding:12px 22px;
 font:inherit;font-weight:600;font-size:15px;cursor:pointer;}
.btn:hover{background:var(--pine-bright);}
@media(prefers-color-scheme:dark){.btn{color:#0e120f;}}
.btn.ghost{background:transparent;color:var(--pine-bright);border:1px solid var(--line);}
.btn.ghost:hover{background:var(--surface);border-color:var(--pine-bright);}
.foot{color:var(--muted);font-size:12.5px;margin-top:20px;max-width:54ch;}
a{color:var(--pine-bright);}
"""

_SHIELD = ('<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">'
           '<path d="M12 2 4 5v6c0 4.5 3.2 8.3 8 9.9 4.8-1.6 8-5.4 8-9.9V5l-8-3Z" '
           'fill="var(--pine)"/><path d="m8.5 12 2.4 2.4L15.8 9.5" stroke="#fbfaf6" '
           'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')


def _shell(inner: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<title>Goonmaster 7000 — Settings</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
        'family=Fraunces:opsz,wght@9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">'
        f'<style>{PAGE_CSS}</style></head><body><div class="wrap">{inner}</div></body></html>'
    )


def _field_row(key: str, label: str, kind: str, val) -> str:
    lbl = html.escape(label)
    if kind == "bool":
        checked = " checked" if val else ""
        return (f'<label class="toggle"><input type="checkbox" name="{key}" '
                f'value="1"{checked}> {lbl}</label>')
    if kind == "freq":
        opts = "".join(
            f'<option value="{o}"{" selected" if val == o else ""}>{o}</option>'
            for o in ("daily", "weekly", "off")
        )
        return (f'<div class="field"><label>{lbl}</label>'
                f'<select name="{key}">{opts}</select></div>')
    t = {"password": "password", "number": "text", "email": "email",
         "url": "url"}.get(kind, "text")
    v = html.escape(str(val))
    return (f'<div class="field"><label>{lbl}</label>'
            f'<input type="{t}" name="{key}" value="{v}"></div>')


def render(cfg: dict, saved: bool) -> str:
    sections = []
    for title, sub, keys in GROUPS:
        rows = []
        for key in keys:
            k, label, kind, default = _FIELD_BY_KEY[key]
            rows.append(_field_row(k, label, kind, cfg.get(k, default)))
        sections.append(
            f'<div class="sect"><h2>{html.escape(title)}</h2>'
            f'<p class="sub">{html.escape(sub)}</p>{"".join(rows)}</div>'
        )
    banner = (
        '<div class="banner"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/>'
        '</svg>Saved. Restart the app for changes to take full effect.</div>'
    ) if saved else ""
    inner = (
        f'<div class="head">{_SHIELD}<h1>Goonmaster 7000</h1></div>'
        f'<span class="status"><span class="dot"></span>{html.escape(_status(cfg))}</span>'
        f'{banner}'
        f'<form method="post" action="/save">{"".join(sections)}'
        f'<div class="actions"><button class="btn" type="submit">Save settings</button>'
        f'<a class="btn ghost" href="/test">Send test email</a></div></form>'
        f'<p class="foot">This page runs only on your computer. Nothing here is sent '
        f'anywhere except the emails you set up.</p>'
    )
    return _shell(inner)


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
        sent_ok = msg.startswith("Test email sent")
        icon = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
                'stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
                if sent_ok else
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/>'
                '<path d="M12 8v5M12 16h.01"/></svg>')
        tone = "ok-soft" if sent_ok else "amber-soft"
        fg = "ok" if sent_ok else "amber"
        inner = (
            f'<div class="head">{_SHIELD}<h1>Goonmaster 7000</h1></div>'
            f'<div class="banner" style="background:var(--{tone});color:var(--{fg})">'
            f'{icon}<span>{html.escape(msg)}</span></div>'
            f'<div class="actions"><a class="btn" href="/">Back to settings</a></div>'
        )
        self._send(_shell(inner))

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
