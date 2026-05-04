#!/usr/bin/env bash
# Expose the local Streamlit (port 8501) to the internet via ngrok.
#
# Two layers of protection are applied:
#  1. The Streamlit app already requires the app_password from secrets.toml.
#  2. ngrok itself requires HTTP basic auth from $NGROK_BASIC_AUTH (user:pass).
#
# Prereqs:
#   brew install ngrok                          # one-time
#   ngrok config add-authtoken <YOUR_TOKEN>     # one-time, sign up at ngrok.com
#   export NGROK_BASIC_AUTH="alice:strongpassword"   # per-shell or in ~/.zshrc
#
# Usage:
#   ./scripts/run_tunnel.sh
set -euo pipefail

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ERROR: ngrok not installed. Install with: brew install ngrok" >&2
  exit 1
fi

if [[ -z "${NGROK_BASIC_AUTH:-}" ]]; then
  echo "ERROR: NGROK_BASIC_AUTH is not set." >&2
  echo "  export NGROK_BASIC_AUTH=\"username:strong-password\"" >&2
  exit 1
fi

# `--host-header=rewrite` keeps Streamlit's CORS/XSRF happy through the proxy.
exec ngrok http 8501 \
  --host-header=rewrite \
  --basic-auth="$NGROK_BASIC_AUTH"
