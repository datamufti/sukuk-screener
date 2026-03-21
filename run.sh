#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Sukuk Screener — local launcher (no Docker required)
# Usage:
#   ./run.sh                  # defaults: host=0.0.0.0, port=8000, data=./data
#   ./run.sh --port 9000      # custom port
#   ./run.sh --host 127.0.0.1 # localhost only
#   ./run.sh --data /tmp/sdb  # custom DuckDB directory
# ---------------------------------------------------------------------------
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
DATA_DIR="${DATA_DIR:-./data}"
WORKERS="${WORKERS:-1}"           # DuckDB is single-writer, keep at 1

# Parse CLI args (override env vars)
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)    HOST="$2";     shift 2 ;;
        --port)    PORT="$2";     shift 2 ;;
        --data)    DATA_DIR="$2"; shift 2 ;;
        --workers) WORKERS="$2";  shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--host HOST] [--port PORT] [--data DATA_DIR] [--workers N]"
            echo ""
            echo "Environment variables (fallback if no flag given):"
            echo "  HOST      Bind address          (default: 0.0.0.0)"
            echo "  PORT      Bind port             (default: 8000)"
            echo "  DATA_DIR  DuckDB data directory  (default: ./data)"
            echo "  WORKERS   Uvicorn workers        (default: 1, keep 1 for DuckDB)"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Ensure data directory exists
mkdir -p "$DATA_DIR"
export DATA_DIR

# Check uv is available
if ! command -v uv &>/dev/null; then
    echo "Error: 'uv' is not installed. Install it with: curl -Ls https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "Syncing dependencies with uv..."
uv sync --frozen


echo ""
echo "Starting Sukuk Screener"
echo "  Host:     $HOST"
echo "  Port:     $PORT"
echo "  Data dir: $DATA_DIR"
echo "  URL:      http://${HOST}:${PORT}"
echo ""

exec uv run uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --reload
