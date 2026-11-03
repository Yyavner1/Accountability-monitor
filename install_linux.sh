#!/bin/bash
# Installer for the accountability monitor (Linux, systemd user service).
#
# Sets up a Python virtual environment, installs dependencies, and registers
# a systemd *user* service that starts the monitor at login and restarts it
# if it stops. Run from the repo root:
#
#     ./install_linux.sh
#
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/accountability-monitor"
VENV="$INSTALL_DIR/venv"
CONFIG="$INSTALL_DIR/config.json"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/accountability-monitor.service"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing to: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$UNIT_DIR"

echo "==> Copying source"
rm -rf "$INSTALL_DIR/accountability_monitor"
cp -R "$SRC_DIR/accountability_monitor" "$INSTALL_DIR/accountability_monitor"

echo "==> Setting up config"
if [ ! -f "$CONFIG" ]; then
    cp "$SRC_DIR/config.example.json" "$CONFIG"
    echo "    Created $CONFIG -- EDIT IT before email will send."
else
    echo "    Keeping existing $CONFIG"
fi

echo "==> Creating virtual environment"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$SRC_DIR/requirements.txt"

echo "==> Writing systemd user unit"
cat > "$UNIT" <<EOF
[Unit]
Description=Accountability screen monitor
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
ExecStart=$VENV/bin/python3 -m accountability_monitor.monitor --config $CONFIG
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

echo "==> Enabling service"
systemctl --user daemon-reload
systemctl --user enable --now accountability-monitor.service

cat <<EOF

Done.

Notes:
  * Edit config:            \$EDITOR "$CONFIG"
    (partner_email, sender_email, smtp_password)
  * Restart after editing:  systemctl --user restart accountability-monitor
  * Logs:                   journalctl --user -u accountability-monitor -f
  * On X11, install xprintidle for idle detection:
        sudo apt install xprintidle
  * On Wayland, install grim for capture:
        sudo apt install grim
  * To keep running after logout: sudo loginctl enable-linger "$USER"
  * (Recommended) Set healthcheck_url in the config to a healthchecks.io
    ping URL so your partner is warned if monitoring goes quiet.
EOF
