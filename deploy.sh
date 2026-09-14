#!/usr/bin/env bash
#
# Deploy the Syndicate frontend to Helix.
#
# The tracked frontend/index.html contains PLACEHOLDERS, not real keys, so the
# public repo carries no credentials. This script substitutes the real values
# from .env into a temp copy and deploys that.
#
# Usage: ./deploy.sh ["version message"]
set -euo pipefail

PROJECT_DIR="/opt/data/syndicate"
FRONTEND_DIR="$PROJECT_DIR/frontend"
ENV_FILE="$PROJECT_DIR/.env"
HELIX_CLIENT="/opt/allr/skills/helix/scripts/helix_client.py"
APP_ID="cf126906-b884-47b3-a1d8-aec3b9d44dd3"
HELIX_PY="/opt/hermes/.venv/bin/python3"

MSG="${1:-frontend deploy}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.example and fill it in." >&2
  exit 1
fi

# Load only the frontend keys from .env (do not export the whole file).
maps_key=$(grep -E '^SYNDICATE_FRONTEND_MAPS_KEY=' "$ENV_FILE" | cut -d= -f2- || true)
firebase_key=$(grep -E '^SYNDICATE_FRONTEND_FIREBASE_KEY=' "$ENV_FILE" | cut -d= -f2- || true)

if [ -z "$maps_key" ]; then
  echo "ERROR: SYNDICATE_FRONTEND_MAPS_KEY missing from .env" >&2
  exit 1
fi
if [ -z "$firebase_key" ]; then
  echo "WARN: SYNDICATE_FRONTEND_FIREBASE_KEY missing; auth may not initialise." >&2
fi

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp -r "$FRONTEND_DIR"/. "$BUILD_DIR"/

# Substitute placeholders. Use python to avoid sed escaping issues with URLs.
MAPS_KEY="$maps_key" FIREBASE_KEY="$firebase_key" BUILD_DIR="$BUILD_DIR" "$HELIX_PY" - <<'PY'
import os, pathlib
d = pathlib.Path(os.environ["BUILD_DIR"])
for f in d.rglob("*.html"):
    s = f.read_text(encoding="utf-8")
    s = s.replace("__GOOGLE_MAPS_API_KEY__", os.environ.get("MAPS_KEY", ""))
    s = s.replace("__FIREBASE_API_KEY__", os.environ.get("FIREBASE_KEY", ""))
    f.write_text(s, encoding="utf-8")
print("placeholders substituted")
PY

# Fail loudly if a placeholder survived.
if grep -rq "__GOOGLE_MAPS_API_KEY__\|__FIREBASE_API_KEY__" "$BUILD_DIR"; then
  echo "ERROR: unresolved placeholder remains in the build." >&2
  exit 1
fi

ZIP="$BUILD_DIR/../syndicate_deploy.zip"
"$HELIX_PY" "$HELIX_CLIENT" zip "$BUILD_DIR" "$ZIP" >/dev/null
"$HELIX_PY" "$HELIX_CLIENT" update "$APP_ID" "$ZIP" "$MSG"
rm -f "$ZIP"
