#!/bin/bash
# Installer for the accountability monitor (macOS).
#
# Sets up a Python virtual environment, installs dependencies, writes a
# launchd agent that starts the monitor at login and restarts it if it
# stops, and loads it. Run from the repo root:
#
#     ./install.sh
#
set -euo pipefail

INSTALL_DIR="$HOME/Library/Application Support/AccountabilityMonitor"
LOG_DIR="$INSTALL_DIR/logs"
VENV="$INSTALL_DIR/venv"
CONFIG="$INSTALL_DIR/config.json"
PLIST_DST="$HOME/Library/LaunchAgents/com.accountability.monitor.plist"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing to: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$LOG_DIR" "$HOME/Library/LaunchAgents"

echo "==> Copying source"
rm -rf "$INSTALL_DIR/accountability_monitor"
cp -R "$SRC_DIR/accountability_monitor" "$INSTALL_DIR/accountability_monitor"

echo "==> Setting up config"
if [ ! -f "$CONFIG" ]; then
    cp "$SRC_DIR/config.example.json" "$CONFIG"
    echo "    Created $CONFIG"
    echo "    EDIT THIS FILE before the monitor will send email."
else
    echo "    Keeping existing $CONFIG"
fi

echo "==> Creating Python virtual environment"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

echo "==> Writing launchd agent"
sed -e "s|__PYTHON__|$VENV/bin/python3|g" \
    -e "s|__CONFIG__|$CONFIG|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__LOG_DIR__|$LOG_DIR|g" \
    "$SRC_DIR/com.accountability.monitor.plist.template" > "$PLIST_DST"

echo "==> Loading agent"
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

cat <<EOF

Done.

Next steps:
  1. Edit your config:
       open -e "$CONFIG"
     Set partner_email, sender_email, and smtp_password (a Gmail App
     Password, created at https://myaccount.google.com/apppasswords).

  2. Grant Screen Recording permission:
     System Settings > Privacy & Security > Screen Recording.
     Add the Python at:
       $VENV/bin/python3
     (A capture will look black until this is granted.)

  3. Restart the agent after editing config:
       launchctl unload "$PLIST_DST"
       launchctl load   "$PLIST_DST"

  4. (Recommended) Create a free check at https://healthchecks.io, paste
     its ping URL into "healthcheck_url" in the config, and set it to
     email your partner if a ping is missed. That is the tamper alert.

Logs: $LOG_DIR
EOF
