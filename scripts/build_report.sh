#!/usr/bin/env bash
# Build the DeepPool public static report into ./site.
# Reads from the local SQLite cache — run ingest first for fresh data.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv not found in PATH. Install with:" >&2
  echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

cd "$PROJECT_ROOT"
exec uv run python -m etf_dash.reporting --out "$PROJECT_ROOT/site" "$@"
