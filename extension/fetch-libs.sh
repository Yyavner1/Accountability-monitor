#!/bin/bash
# Download the on-device model libraries the extension needs.
# Chrome (Manifest V3) does not allow extensions to load code from the
# internet at runtime, so TensorFlow.js and NSFWJS are bundled locally.
# Run this once before loading the extension:
#
#     cd extension && ./fetch-libs.sh
#
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p lib

TF="https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js"
NSFW="https://cdn.jsdelivr.net/npm/nsfwjs@4.2.1/dist/nsfwjs.min.js"

echo "==> Downloading TensorFlow.js"
curl -fsSL "$TF" -o lib/tf.min.js
echo "==> Downloading NSFWJS"
curl -fsSL "$NSFW" -o lib/nsfwjs.min.js

echo "Done. Files in extension/lib/:"
ls -la lib/
echo
echo "Now load the extension: Chrome > Extensions > Developer mode >"
echo "Load unpacked > select this 'extension' folder."
