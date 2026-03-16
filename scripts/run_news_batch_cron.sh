#!/bin/zsh
set -euo pipefail

# ── Guard: reject OS-crontab invocation ──
# OpenClaw sets OPENCLAW_SHELL in its exec environment.
# If absent, this was launched by OS crontab (which should be removed).
if [[ -z "${OPENCLAW_SHELL:-}" ]]; then
  mkdir -p "$HOME/.openclaw/workspace/codes/TradeMaster_v2/logs/cron"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] BLOCKED: OS crontab trigger rejected. Remove OS crontab entry: crontab -e" \
    >> "$HOME/.openclaw/workspace/codes/TradeMaster_v2/logs/cron/news_batch_cron.log"
  exit 0
fi

PROJECT_DIR="$HOME/.openclaw/workspace/codes/TradeMaster_v2"
LOG_DIR="$PROJECT_DIR/logs/cron"
LOCK_DIR="$PROJECT_DIR/.locks/news-batch-cron.lock"
# Pin to the system Python 3.14 that has requests installed
PYTHON_BIN="/usr/local/bin/python3"

mkdir -p "$LOG_DIR" "$PROJECT_DIR/.locks"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] news batch skipped: lock active" >> "$LOG_DIR/news_batch_cron.log"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$PROJECT_DIR"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] news batch start" >> "$LOG_DIR/news_batch_cron.log"
API_BASE="http://127.0.0.1:8080" "$PYTHON_BIN" scripts/fetch_news_batch.py --limit 3 >> "$LOG_DIR/news_batch_cron.log" 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] news batch done" >> "$LOG_DIR/news_batch_cron.log"
