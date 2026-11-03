#!/bin/bash
# Apply the website filter to the system hosts file (macOS / Linux).
# Needs admin rights, so run with sudo:
#
#     sudo ./install_filter.sh [path/to/blocklist.txt] [BLOCKLIST_URL]
#
# With a URL, the list is downloaded, appended to the local blocklist, and
# all of it is applied. Re-run any time to refresh.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
BLOCKLIST="${1:-$SRC_DIR/blocklist.txt}"
URL="${2:-}"
PY="$(command -v python3)"

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run with sudo (it edits /etc/hosts)." >&2
    exit 1
fi

TMP="$(mktemp)"
cat "$BLOCKLIST" > "$TMP"
if [ -n "$URL" ]; then
    echo "==> Downloading blocklist from $URL"
    curl -fsSL "$URL" >> "$TMP" || { echo "download failed" >&2; exit 1; }
fi

echo "==> Applying filter"
PYTHONPATH="$SRC_DIR" "$PY" -m accountability_monitor.blocker apply "$TMP"
rm -f "$TMP"

# Flush DNS cache so the change takes effect immediately.
if [ "$(uname)" = "Darwin" ]; then
    dscacheutil -flushcache 2>/dev/null || true
    killall -HUP mDNSResponder 2>/dev/null || true
fi

echo "Done. Check status with:"
echo "  python3 -m accountability_monitor.blocker status"
echo "Remove with:"
echo "  sudo python3 -m accountability_monitor.blocker remove"
