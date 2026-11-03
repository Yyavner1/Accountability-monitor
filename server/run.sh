#!/bin/bash
# Run the backend locally for development.
#
#   ./run.sh            # http://127.0.0.1:8000
#
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d venv ]; then
    python3 -m venv venv
    venv/bin/pip install --quiet --upgrade pip
    venv/bin/pip install --quiet -r requirements.txt
fi

# Generate a secret key on first run if none is set.
if [ ! -f .env ]; then
    echo "AM_SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')" > .env
    echo "Wrote .env with a fresh AM_SECRET_KEY"
fi

exec venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
