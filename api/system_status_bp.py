#!/usr/bin/env python3
"""
System Status Aggregation API
GET /api/v1/system/status - 聚合所有子系統狀態，供前端 Dashboard 顯示
"""

import os
import socket
import subprocess
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify

system_status_bp = Blueprint('system_status', __name__)

_TZ = timezone(timedelta(hours=8))


def _now():
    return datetime.now(_TZ)


def _check_api_health():
    """TradeMaster API health (self-check)"""
    return {
        "status": "ok",
        "service": "TradeMaster v2.0 API",
        "checked_at": _now().isoformat(),
    }


def _check_news_sync():
    """News sync status from MySQL"""
    try:
        from config.database import get_db_connection
        with get_db_connection() as conn:
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT MAX(created_at) AS last_synced FROM news")
            row = cur.fetchone()
            last_synced = row['last_synced'] if row else None
            if last_synced and last_synced.tzinfo is None:
                last_synced = last_synced.replace(tzinfo=_TZ)

            cur.execute(
                "SELECT COUNT(*) AS cnt FROM news "
                "WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)"
            )
            count_24h = cur.fetchone()['cnt']

            cur.execute("SELECT COUNT(*) AS cnt FROM news")
            total = cur.fetchone()['cnt']

        if last_synced is None:
            sync_status = "never_synced"
        elif count_24h > 0:
            sync_status = "ok"
        else:
            sync_status = "stale"

        return {
            "status": sync_status,
            "last_synced": last_synced.isoformat() if last_synced else None,
            "count_24h": count_24h,
            "count_total": total,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}


def _check_kline_freshness():
    """K-line cache freshness from MySQL"""
    try:
        from api.db import get_db_connection
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT MAX(updated_at) AS latest, COUNT(DISTINCT symbol) AS symbols "
                "FROM kline_cache"
            )
            row = cur.fetchone()
            if row and row['latest']:
                latest = row['latest']
                if isinstance(latest, str):
                    # parse ISO string
                    try:
                        latest = datetime.fromisoformat(latest)
                    except Exception:
                        pass
                if hasattr(latest, 'tzinfo') and latest.tzinfo is None:
                    latest = latest.replace(tzinfo=_TZ)
                return {
                    "status": "ok",
                    "last_updated": latest.isoformat() if hasattr(latest, 'isoformat') else str(latest),
                    "symbol_count": row['symbols'],
                }
            return {"status": "empty", "last_updated": None, "symbol_count": 0}
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}


def _check_opend():
    """OpenD process reachability (TCP probe on 11111)"""
    host = os.getenv("OPEND_HOST", "127.0.0.1")
    port = int(os.getenv("OPEND_PORT", "11111"))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        if result == 0:
            return {"status": "reachable", "host": host, "port": port}
        else:
            return {"status": "unreachable", "host": host, "port": port}
    except Exception as e:
        return {"status": "unknown", "detail": str(e)[:200]}


def _check_futu():
    """Futu API connectivity (SDK-level check via OpenD).

    Performs a fast TCP pre-check first; only attempts the heavier SDK call
    when the OpenD port is actually open.  This avoids the SDK's built-in
    retry loop (≈60 s) blocking the status endpoint when OpenD is down.
    """
    host = os.getenv("OPEND_HOST", "127.0.0.1")
    port = int(os.getenv("OPEND_PORT", "11111"))

    # Fast TCP gate — if OpenD port is closed, skip SDK entirely
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        tcp_ok = sock.connect_ex((host, port)) == 0
        sock.close()
    except Exception:
        tcp_ok = False

    if not tcp_ok:
        return {"status": "unreachable", "host": host, "port": port,
                "detail": "OpenD port not open — skipped SDK check"}

    # OpenD port is open, try SDK-level verification
    try:
        from futu.quote.open_quote_context import OpenQuoteContext
    except ImportError:
        return {"status": "sdk_missing", "detail": "futu-api SDK not installed"}

    try:
        ctx = OpenQuoteContext(host=host, port=port)
        ret, data = ctx.get_global_state()
        ctx.close()
        if ret == 0:
            market_info = {}
            if hasattr(data, 'to_dict'):
                records = data.to_dict('records')
                market_info = records[0] if records else {}
            elif isinstance(data, dict):
                market_info = data
            return {
                "status": "connected",
                "host": host,
                "port": port,
                "market_state": market_info.get("market_hk",
                                                market_info.get("market", None)),
            }
        else:
            return {"status": "error", "host": host, "port": port,
                    "detail": str(data)[:200]}
    except Exception as e:
        return {"status": "error", "host": host, "port": port,
                "detail": str(e)[:200]}


def _check_cron():
    """OpenClaw / system cron summary"""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip() and not l.startswith('#')]
        job_count = len(lines)

        # Check recent cron log for errors
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "cron")
        error_count = 0
        latest_log = None
        if os.path.isdir(log_dir):
            log_files = sorted(os.listdir(log_dir), reverse=True)
            if log_files:
                latest_log = log_files[0]
                log_path = os.path.join(log_dir, latest_log)
                try:
                    with open(log_path, 'r') as f:
                        content = f.read()
                    error_count = content.lower().count('error') + content.lower().count('traceback')
                except Exception:
                    pass

        return {
            "status": "ok" if job_count > 0 else "no_jobs",
            "job_count": job_count,
            "recent_errors": error_count,
            "latest_log": latest_log,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)[:200]}


@system_status_bp.route('/api/v1/system/status')
def system_status():
    """Aggregated system status for Dashboard panel"""
    return jsonify({
        "checked_at": _now().isoformat(),
        "api": _check_api_health(),
        "news_sync": _check_news_sync(),
        "kline": _check_kline_freshness(),
        "opend": _check_opend(),
        "futu": _check_futu(),
        "cron": _check_cron(),
    })
