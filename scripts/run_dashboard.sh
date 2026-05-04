#!/usr/bin/env bash
# Launch the DeepPool Streamlit dashboard.
# Resolves uv path even if ~/.zshrc hasn't been sourced.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found in PATH. Install with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_ROOT/.streamlit/secrets.toml" ]]; then
  echo "WARN: .streamlit/secrets.toml not found." >&2
  echo "      The app will refuse to start without app_password set." >&2
  echo "      Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml" >&2
  echo "      and edit the password. Falling through anyway." >&2
fi

cd "$PROJECT_ROOT"
exec uv run streamlit run src/etf_dash/ui/app.py "$@"
