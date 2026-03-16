#!/bin/zsh
# ============================================================
# tm-ctl.sh — TradeMaster 統一服務管理腳本
# Usage: tm-ctl.sh {status|start|stop|restart|health|logs}
# ============================================================
set -uo pipefail

API_LABEL="com.trademaster.api"
VIEW_LABEL="com.trademaster.view"
API_URL="http://127.0.0.1:8080"
VIEW_URL="http://127.0.0.1:3000"
API_LOG_DIR="$HOME/.openclaw/workspace/codes/TradeMaster_v2/logs"
VIEW_LOG_DIR="$HOME/.openclaw/workspace/codes/TradeMasterView/logs"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'; NC='\033[0m'

# ── helpers ─────────────────────────────────────────────────
_ok()   { echo "${GREEN}✅ $1${NC}"; }
_warn() { echo "${YELLOW}⚠️  $1${NC}"; }
_fail() { echo "${RED}❌ $1${NC}"; }

_svc_running() {
  launchctl list "$1" &>/dev/null
}

_http_ok() {
  curl -sf --max-time 3 "$1" &>/dev/null
}

# ── status ──────────────────────────────────────────────────
cmd_status() {
  echo "═══════════════════════════════════════"
  echo "  TradeMaster Service Status"
  echo "═══════════════════════════════════════"

  # API
  echo ""
  echo "▸ TradeMaster API (port 8080)"
  if _svc_running "$API_LABEL"; then
    _ok "launchd: loaded"
  else
    _fail "launchd: NOT loaded"
  fi
  if _http_ok "$API_URL/health"; then
    local health=$(curl -sf --max-time 3 "$API_URL/health")
    _ok "health: $health"
  else
    _fail "health: unreachable"
  fi

  # View
  echo ""
  echo "▸ TradeMasterView (port 3000)"
  if _svc_running "$VIEW_LABEL"; then
    _ok "launchd: loaded"
  else
    _fail "launchd: NOT loaded"
  fi
  if _http_ok "$VIEW_URL"; then
    _ok "http: responding"
  else
    _fail "http: unreachable"
  fi

  # MySQL
  echo ""
  echo "▸ MySQL (port 3306)"
  if mysqladmin ping -h 127.0.0.1 -u alita -palitamysql --silent 2>/dev/null; then
    _ok "mysql: alive"
  else
    _warn "mysql: not responding (optional for some features)"
  fi

  # OpenClaw Cron summary
  echo ""
  echo "▸ OpenClaw Cron Jobs"
  local total=$(openclaw cron list 2>/dev/null | tail -n +3 | wc -l | tr -d ' ')
  local errors=$(openclaw cron list 2>/dev/null | grep -c "error" || echo 0)
  echo "  total: $total jobs, errors: $errors"

  echo ""
  echo "═══════════════════════════════════════"
}

# ── start ───────────────────────────────────────────────────
cmd_start() {
  local target="${1:-all}"
  mkdir -p "$API_LOG_DIR" "$VIEW_LOG_DIR"

  if [[ "$target" == "all" || "$target" == "api" ]]; then
    echo "Starting TradeMaster API..."
    # Kill any orphan nohup instances first
    pkill -f "python.*api_server.py" 2>/dev/null || true
    sleep 1
    if ! _svc_running "$API_LABEL"; then
      launchctl load "$HOME/Library/LaunchAgents/${API_LABEL}.plist"
    fi
    # Wait and verify
    sleep 3
    if _http_ok "$API_URL/health"; then
      _ok "API started"
    else
      _warn "API loaded but health check failed — check logs: $API_LOG_DIR/api_launchd_err.log"
    fi
  fi

  if [[ "$target" == "all" || "$target" == "view" ]]; then
    echo "Starting TradeMasterView..."
    if ! _svc_running "$VIEW_LABEL"; then
      launchctl load "$HOME/Library/LaunchAgents/${VIEW_LABEL}.plist"
    fi
    sleep 2
    if _http_ok "$VIEW_URL"; then
      _ok "View started"
    else
      _warn "View loaded but http check failed — check logs: $VIEW_LOG_DIR/view_launchd_err.log"
    fi
  fi
}

# ── stop ────────────────────────────────────────────────────
cmd_stop() {
  local target="${1:-all}"

  if [[ "$target" == "all" || "$target" == "api" ]]; then
    echo "Stopping TradeMaster API..."
    if _svc_running "$API_LABEL"; then
      launchctl unload "$HOME/Library/LaunchAgents/${API_LABEL}.plist" 2>/dev/null
    fi
    pkill -f "python.*api_server.py" 2>/dev/null || true
    _ok "API stopped"
  fi

  if [[ "$target" == "all" || "$target" == "view" ]]; then
    echo "Stopping TradeMasterView..."
    if _svc_running "$VIEW_LABEL"; then
      launchctl unload "$HOME/Library/LaunchAgents/${VIEW_LABEL}.plist" 2>/dev/null
    fi
    _ok "View stopped"
  fi
}

# ── restart ─────────────────────────────────────────────────
cmd_restart() {
  local target="${1:-all}"
  cmd_stop "$target"
  sleep 2
  cmd_start "$target"
}

# ── health (quick one-liner) ────────────────────────────────
cmd_health() {
  local ok=0 fail=0
  if _http_ok "$API_URL/health"; then ((ok++)); else ((fail++)); fi
  if _http_ok "$VIEW_URL"; then ((ok++)); else ((fail++)); fi

  if [[ $fail -eq 0 ]]; then
    _ok "All services healthy (API + View)"
  else
    _fail "$fail service(s) down, $ok healthy"
    return 1
  fi
}

# ── logs ────────────────────────────────────────────────────
cmd_logs() {
  local target="${1:-api}"
  case "$target" in
    api)  tail -50 "$API_LOG_DIR/api_launchd.log" "$API_LOG_DIR/api_launchd_err.log" ;;
    view) tail -50 "$VIEW_LOG_DIR/view_launchd.log" "$VIEW_LOG_DIR/view_launchd_err.log" ;;
    cron) tail -50 "$API_LOG_DIR/../logs/cron/"*.log ;;
    *)    echo "Usage: tm-ctl.sh logs {api|view|cron}" ;;
  esac
}

# ── main ────────────────────────────────────────────────────
case "${1:-status}" in
  status)  cmd_status ;;
  start)   cmd_start "${2:-all}" ;;
  stop)    cmd_stop "${2:-all}" ;;
  restart) cmd_restart "${2:-all}" ;;
  health)  cmd_health ;;
  logs)    cmd_logs "${2:-api}" ;;
  *)
    echo "Usage: tm-ctl.sh {status|start|stop|restart|health|logs} [api|view|all]"
    exit 1
    ;;
esac
