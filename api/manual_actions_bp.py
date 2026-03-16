#!/usr/bin/env python3
"""
Manual Actions API — 白名單式手動觸發

僅允許以下 action：
  - sync_news      : 手動同步新聞 (呼叫 fetch_news_batch.py)
  - refresh_kline   : 手動刷新 K 線 (呼叫 yfinance_update.py)
  - refresh_status  : 手動刷新系統狀態 (重新讀取各子系統)

安全限制：
  - 白名單硬編碼，無法執行任意命令
  - 同一 action 執行中禁止重複觸發
  - 不碰交易 / 資金 / 配置修改
"""

import os
import sys
import subprocess
import sqlite3
import threading
import time
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request

manual_actions_bp = Blueprint('manual_actions', __name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, 'scripts')
DB_PATH = os.path.join(PROJECT_ROOT, 'trademaster.db')
_TZ = timezone(timedelta(hours=8))

# ── 執行狀態追蹤 (process-level in-memory) ──
# {action_name: {status, started_at, finished_at, summary, error, last_5_runs: []}}
_action_state = {}
_action_locks = {}  # per-action threading lock


def _get_lock(action: str) -> threading.Lock:
    if action not in _action_locks:
        _action_locks[action] = threading.Lock()
    return _action_locks[action]


def _set_state(action: str, **kwargs):
    if action not in _action_state:
        _action_state[action] = {'last_5_runs': []}
    if 'last_5_runs' not in _action_state[action]:
        _action_state[action]['last_5_runs'] = []
    _action_state[action].update(kwargs)


def _add_to_history(action: str, status: str, started_at: str, finished_at: str, summary: str = None, error: str = None):
    """將執行結果加入 last_5_runs"""
    if action not in _action_state:
        _action_state[action] = {'last_5_runs': []}
    
    if 'last_5_runs' not in _action_state[action]:
        _action_state[action]['last_5_runs'] = []
    
    record = {
        'status': status,
        'started_at': started_at,
        'finished_at': finished_at,
        'summary': summary,
        'error': error[:100] if error else None  # max 100 chars
    }
    _action_state[action]['last_5_runs'].append(record)
    
    # Keep only last 5
    if len(_action_state[action]['last_5_runs']) > 5:
        _action_state[action]['last_5_runs'] = _action_state[action]['last_5_runs'][-5:]


def _now_iso():
    return datetime.now(_TZ).isoformat()


# ── SQLite 持久化 ──

def _get_db():
    """取得 SQLite 連線（per-call，thread-safe）"""
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _save_history(action: str, status: str, started_at: str,
                  finished_at: str, summary: str = None, error: str = None):
    """將執行結果寫入 action_history"""
    try:
        conn = _get_db()
        conn.execute(
            """INSERT INTO action_history (action, status, started_at, finished_at, summary, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (action, status, started_at, finished_at, summary, error)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        # 持久化失敗不應阻斷主邏輯
        print(f"[action_history] save failed: {e}")


def _load_last_states():
    """啟動時從 DB 還原每個 action 的最近狀態和最近5筆記錄"""
    try:
        conn = _get_db()
        for action_name in ACTION_REGISTRY:
            # Load last state
            row = conn.execute(
                """SELECT status, started_at, finished_at, summary, error
                   FROM action_history
                   WHERE action = ?
                   ORDER BY id DESC LIMIT 1""",
                (action_name,)
            ).fetchone()
            if row:
                _set_state(action_name,
                           status=row['status'],
                           started_at=row['started_at'],
                           finished_at=row['finished_at'],
                           summary=row['summary'],
                           error=row['error'])
            
            # Load last 5 runs
            rows = conn.execute(
                """SELECT status, started_at, finished_at, summary, error
                   FROM action_history
                   WHERE action = ?
                   ORDER BY id DESC LIMIT 5""",
                (action_name,)
            ).fetchall()
            if rows:
                # Reverse to get oldest first (chronological order)
                records = [dict(r) for r in reversed(rows)]
                if action_name not in _action_state:
                    _action_state[action_name] = {}
                _action_state[action_name]['last_5_runs'] = records
        conn.close()
    except Exception as e:
        print(f"[action_history] load_last_states failed: {e}")


def _get_history(action: str, limit: int = 5):
    """取得指定 action 的最近 N 筆執行記錄"""
    try:
        conn = _get_db()
        rows = conn.execute(
            """SELECT id, action, status, started_at, finished_at, summary, error
               FROM action_history
               WHERE action = ?
               ORDER BY id DESC LIMIT ?""",
            (action, limit)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"[action_history] get_history failed: {e}")
        return []


# ── 白名單 action 定義 ──

def _run_sync_news():
    """執行新聞同步，回傳摘要"""
    script = os.path.join(SCRIPTS_DIR, 'fetch_news_batch.py')
    if not os.path.isfile(script):
        return False, "Script not found: fetch_news_batch.py"
    try:
        result = subprocess.run(
            [sys.executable, script, '--limit', '5'],
            capture_output=True, text=True, timeout=120,
            cwd=PROJECT_ROOT,
            env={**os.environ, 'PYTHONPATH': PROJECT_ROOT},
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            lines = stdout.split('\n')
            summary_lines = [l for l in lines[-10:] if l.strip()]
            summary = '\n'.join(summary_lines) if summary_lines else "完成（無輸出）"
            return True, summary
        else:
            detail = stderr[-500:] if stderr else stdout[-500:]
            return False, f"exit code {result.returncode}: {detail}"
    except subprocess.TimeoutExpired:
        return False, "執行超時 (>120s)"
    except Exception as e:
        return False, str(e)[:300]


def _run_refresh_kline():
    """刷新 K 線資料 (呼叫 futu_update_once.py)"""
    import socket
    opend_host = os.environ.get('OPEND_HOST', '127.0.0.1')
    opend_port = int(os.environ.get('OPEND_PORT', '11111'))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        if sock.connect_ex((opend_host, opend_port)) != 0:
            sock.close()
            return False, f"OpenD ({opend_host}:{opend_port}) 無法連線，請先啟動 OpenD"
        sock.close()
    except Exception:
        return False, f"OpenD ({opend_host}:{opend_port}) 連線檢查失敗"

    script = os.path.join(SCRIPTS_DIR, 'futu_update_once.py')
    if not os.path.isfile(script):
        return False, "Script not found: futu_update_once.py"
    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=180,
            cwd=SCRIPTS_DIR,
            env={**os.environ, 'PYTHONPATH': PROJECT_ROOT},
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            lines = stdout.split('\n')
            summary_lines = [l for l in lines[-10:] if l.strip()]
            summary = '\n'.join(summary_lines) if summary_lines else "完成（無輸出）"
            return True, summary
        else:
            detail = stderr[-500:] if stderr else stdout[-500:]
            return False, f"exit code {result.returncode}: {detail}"
    except subprocess.TimeoutExpired:
        return False, "執行超時 (>180s)"
    except Exception as e:
        return False, str(e)[:300]


def _run_refresh_status():
    """重新讀取系統狀態 (直接呼叫 system_status 的各檢查函數)"""
    try:
        from api.system_status_bp import (
            _check_api_health, _check_news_sync,
            _check_kline_freshness, _check_opend,
            _check_futu, _check_cron,
        )
        result = {
            "api": _check_api_health(),
            "news_sync": _check_news_sync(),
            "kline": _check_kline_freshness(),
            "opend": _check_opend(),
            "futu": _check_futu(),
            "cron": _check_cron(),
        }
        parts = []
        for k, v in result.items():
            s = v.get('status', 'unknown')
            parts.append(f"{k}: {s}")
        summary = ' | '.join(parts)
        return True, summary
    except Exception as e:
        return False, str(e)[:300]


# 白名單 registry — 只有這裡列出的 action 可以被觸發
ACTION_REGISTRY = {
    'sync_news': {
        'label': '手動同步新聞',
        'fn': _run_sync_news,
        'cooldown_sec': 30,
    },
    'refresh_kline': {
        'label': '手動刷新 K 線',
        'fn': _run_refresh_kline,
        'cooldown_sec': 30,
    },
    'refresh_status': {
        'label': '手動刷新系統狀態',
        'fn': _run_refresh_status,
        'cooldown_sec': 5,
    },
}


def _run_action_async(action: str):
    """在背景 thread 執行 action，更新狀態並持久化"""
    entry = ACTION_REGISTRY[action]
    fn = entry['fn']
    started = _now_iso()
    _set_state(action, status='running', started_at=started,
               finished_at=None, summary=None, error=None)
    try:
        ok, summary = fn()
        finished = _now_iso()
        if ok:
            _set_state(action, status='success', finished_at=finished,
                       summary=summary, error=None)
            _save_history(action, 'success', started, finished, summary=summary)
            _add_to_history(action, 'success', started, finished, summary=summary)
        else:
            _set_state(action, status='failed', finished_at=finished,
                       summary=None, error=summary)
            _save_history(action, 'failed', started, finished, error=summary)
            _add_to_history(action, 'failed', started, finished, error=summary)
    except Exception as e:
        finished = _now_iso()
        err_msg = str(e)[:300]
        _set_state(action, status='failed', finished_at=finished,
                   summary=None, error=err_msg)
        _save_history(action, 'failed', started, finished, error=err_msg)
        _add_to_history(action, 'failed', started, finished, error=err_msg)


# ── 啟動時從 DB 還原最近狀態 ──
_load_last_states()


# ── Routes ──

@manual_actions_bp.route('/api/v1/manual-actions', methods=['GET'])
def list_actions():
    """列出所有可用的手動 action 及其當前狀態"""
    actions = []
    for key, entry in ACTION_REGISTRY.items():
        state = _action_state.get(key, {})
        actions.append({
            'action': key,
            'label': entry['label'],
            'cooldown_sec': entry['cooldown_sec'],
            'status': state.get('status', 'idle'),
            'started_at': state.get('started_at'),
            'finished_at': state.get('finished_at'),
            'summary': state.get('summary'),
            'error': state.get('error'),
            'last_5_runs': state.get('last_5_runs', []),
        })
    return jsonify({'actions': actions})


@manual_actions_bp.route('/api/v1/manual-actions/<action>/trigger', methods=['POST'])
def trigger_action(action: str):
    """觸發指定的手動 action"""
    if action not in ACTION_REGISTRY:
        return jsonify({'status': 'error',
                        'message': f'Unknown action: {action}. '
                                   f'Allowed: {list(ACTION_REGISTRY.keys())}'}), 400

    entry = ACTION_REGISTRY[action]
    lock = _get_lock(action)

    # 防重複
    state = _action_state.get(action, {})
    if state.get('status') == 'running':
        return jsonify({'status': 'rejected',
                        'message': '該動作正在執行中，請稍候',
                        'started_at': state.get('started_at')}), 429

    # Cooldown 檢查
    finished = state.get('finished_at')
    if finished:
        try:
            finished_dt = datetime.fromisoformat(finished)
            elapsed = (datetime.now(_TZ) - finished_dt).total_seconds()
            if elapsed < entry['cooldown_sec']:
                remaining = int(entry['cooldown_sec'] - elapsed)
                return jsonify({'status': 'cooldown',
                                'message': f'冷卻中，請等 {remaining} 秒',
                                'retry_after_sec': remaining}), 429
        except Exception:
            pass

    # 啟動背景執行
    t = threading.Thread(target=_run_action_async, args=(action,), daemon=True)
    t.start()

    return jsonify({'status': 'accepted',
                    'action': action,
                    'label': entry['label'],
                    'message': '已開始執行'})


@manual_actions_bp.route('/api/v1/manual-actions/<action>/status', methods=['GET'])
def action_status(action: str):
    """查詢指定 action 的執行狀態"""
    if action not in ACTION_REGISTRY:
        return jsonify({'status': 'error',
                        'message': f'Unknown action: {action}'}), 400

    state = _action_state.get(action, {})
    entry = ACTION_REGISTRY[action]
    return jsonify({
        'action': action,
        'label': entry['label'],
        'status': state.get('status', 'idle'),
        'started_at': state.get('started_at'),
        'finished_at': state.get('finished_at'),
        'summary': state.get('summary'),
        'error': state.get('error'),
    })


@manual_actions_bp.route('/api/v1/manual-actions/<action>/history', methods=['GET'])
def action_history(action: str):
    """查詢指定 action 最近 N 筆執行記錄（預設 5 筆）"""
    if action not in ACTION_REGISTRY:
        return jsonify({'status': 'error',
                        'message': f'Unknown action: {action}'}), 400

    limit = request.args.get('limit', 5, type=int)
    limit = max(1, min(limit, 20))  # clamp 1~20
    records = _get_history(action, limit)
    return jsonify({
        'action': action,
        'label': ACTION_REGISTRY[action]['label'],
        'history': records,
    })
