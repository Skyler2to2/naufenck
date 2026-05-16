#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "⚠️  未找到 .env，从 .env.example 复制并填入 YOUTUBE_API_KEY" >&2
  echo "   cp .env.example .env && \$EDITOR .env" >&2
fi

PORT="${PORT:-8501}"
HOST="${HOST:-0.0.0.0}"

exec streamlit run YTMetrics.py \
  --server.port "$PORT" \
  --server.address "$HOST" \
  --server.headless true \
  --browser.gatherUsageStats false \
  "$@"
