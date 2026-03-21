#!/usr/bin/env python3
"""
Signals API Blueprint (DB-based, single source of truth)
交易信號的 CRUD 接口 - MySQL
Stage 1: 收斂為唯一 signals 路由，消除 file-based 歧義
"""

from flask import Blueprint, jsonify, request
from api.db import get_db_connection
import json
from datetime import datetime

signals_bp = Blueprint('signals_db', __name__, url_prefix='/api/v1/signals')


def _serialize_row(row):
    """Ensure datetime fields are ISO-8601 strings with +08:00 timezone"""
    if not row:
        return row
    out = dict(row)
    for k, v in out.items():
        if isinstance(v, datetime):
            # MySQL stores local time (Asia/Taipei), tag it explicitly
            out[k] = v.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    return out


def _serialize_rows(rows):
    return [_serialize_row(r) for r in rows]


@signals_bp.route('', methods=['GET'])
def get_signals():
    """獲取信號列表 (支持 offset 分頁)"""
    status = request.args.get('status')
    symbol = request.args.get('symbol')
    account_type = request.args.get('account_type', 'paper')  # 默認只返回 paper
    limit = int(request.args.get('limit', 100))
    offset = int(request.args.get('offset', 0))

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Count query
        count_query = "SELECT COUNT(*) as cnt FROM signals WHERE 1=1"
        query = "SELECT * FROM signals WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            count_query += " AND status = %s"
            params.append(status)

        if symbol:
            query += " AND symbol = %s"
            count_query += " AND symbol = %s"
            params.append(symbol)

        if account_type:
            query += " AND account_type = %s"
            count_query += " AND account_type = %s"
            params.append(account_type)

        # Get total count
        cursor.execute(count_query, params)
        total = cursor.fetchone()['cnt']

        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        cursor.execute(query, params + [limit, offset])
        rows = cursor.fetchall()

        # data_timestamp: use latest row's created_at
        data_timestamp = None
        if rows:
            latest_ts = rows[0].get('created_at')
            if isinstance(latest_ts, datetime):
                data_timestamp = latest_ts.strftime('%Y-%m-%dT%H:%M:%S+08:00')
            elif latest_ts:
                data_timestamp = str(latest_ts)

    return jsonify({
        "status": "ok",
        "count": total,
        "data_timestamp": data_timestamp,
        "signals": _serialize_rows(rows)
    })


@signals_bp.route('/latest', methods=['GET'])
def get_latest_signals():
    """獲取最新信號 (供 store/Dashboard 使用)"""
    limit = int(request.args.get('limit', 10))
    account_type = request.args.get('account_type', 'paper')

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM signals WHERE account_type = %s ORDER BY created_at DESC LIMIT %s",
            (account_type, limit)
        )
        rows = cursor.fetchall()

        data_timestamp = None
        if rows:
            latest_ts = rows[0].get('created_at')
            if isinstance(latest_ts, datetime):
                data_timestamp = latest_ts.strftime('%Y-%m-%dT%H:%M:%S+08:00')
            elif latest_ts:
                data_timestamp = str(latest_ts)

    return jsonify({
        "status": "ok",
        "count": len(rows),
        "data_timestamp": data_timestamp,
        "signals": _serialize_rows(rows)
    })


@signals_bp.route('/by-symbol/<symbol>', methods=['GET'])
def get_signals_by_symbol(symbol):
    """根據股票代號獲取信號"""
    limit = int(request.args.get('limit', 50))

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM signals WHERE symbol = %s ORDER BY created_at DESC LIMIT %s",
            (symbol.upper(), limit)
        )
        rows = cursor.fetchall()

        data_timestamp = None
        if rows:
            latest_ts = rows[0].get('created_at')
            if isinstance(latest_ts, datetime):
                data_timestamp = latest_ts.strftime('%Y-%m-%dT%H:%M:%S+08:00')
            elif latest_ts:
                data_timestamp = str(latest_ts)

    return jsonify({
        "status": "ok",
        "symbol": symbol.upper(),
        "count": len(rows),
        "data_timestamp": data_timestamp,
        "signals": _serialize_rows(rows)
    })


@signals_bp.route('/<int:signal_id>', methods=['GET'])
def get_signal(signal_id):
    """獲取單個信號"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE id = %s", (signal_id,))
        row = cursor.fetchone()

    if not row:
        return jsonify({"status": "error", "message": "Signal not found"}), 404

    return jsonify({
        "status": "ok",
        "signal": _serialize_row(row)
    })


@signals_bp.route('', methods=['POST'])
def create_signal():
    """創建新信號"""
    data = request.json

    if not data or 'symbol' not in data or 'signal_type' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400

    # HOLD 信號自動標記為 IGNORED
    signal_type = data.get('signal_type')
    status = data.get('status', 'PENDING')
    if signal_type == 'HOLD':
        status = 'IGNORED'

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 從數據中獲取 account_type，預設為 paper
        account_type = data.get('account_type', 'paper')

        cursor.execute('''
            INSERT INTO signals (symbol, strategy_type, signal_type, price, quantity,
                              confidence, status, risk_score, news_weight, stop_loss,
                              take_profit, metadata, account_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            data['symbol'],
            data.get('strategy_type'),
            data['signal_type'],
            data.get('price'),
            data.get('quantity'),
            data.get('confidence', 0.5),
            status,
            data.get('risk_score'),
            data.get('news_weight'),
            data.get('stop_loss'),
            data.get('take_profit'),
            json.dumps(data.get('metadata', {})),
            account_type
        ))

        signal_id = cursor.lastrowid
        conn.commit()

    return jsonify({
        "status": "ok",
        "message": "Signal created",
        "signal_id": signal_id
    }), 201


@signals_bp.route('/<int:signal_id>', methods=['PUT'])
def update_signal(signal_id):
    """更新信號"""
    data = request.json

    with get_db_connection() as conn:
        cursor = conn.cursor()

        updates = []
        params = []

        for field in ['symbol', 'strategy_type', 'signal_type', 'price', 'quantity',
                      'confidence', 'status', 'risk_score', 'news_weight',
                      'stop_loss', 'take_profit']:
            if field in data:
                updates.append(f"{field} = %s")
                params.append(data[field])

        if not updates:
            return jsonify({"status": "error", "message": "No fields to update"}), 400

        params.append(signal_id)

        cursor.execute(
            f"UPDATE signals SET {', '.join(updates)} WHERE id = %s",
            params
        )

        conn.commit()
        affected = cursor.rowcount

    if affected == 0:
        return jsonify({"status": "error", "message": "Signal not found"}), 404

    return jsonify({
        "status": "ok",
        "message": "Signal updated"
    })


@signals_bp.route('/<int:signal_id>', methods=['DELETE'])
def delete_signal(signal_id):
    """刪除信號"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM signals WHERE id = %s", (signal_id,))
        conn.commit()
        affected = cursor.rowcount

    if affected == 0:
        return jsonify({"status": "error", "message": "Signal not found"}), 404

    return jsonify({
        "status": "ok",
        "message": "Signal deleted"
    })


@signals_bp.route('/active', methods=['GET'])
def get_active_signals():
    """獲取活躍信號"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM signals
            WHERE status IN ('PENDING', 'SENT')
            ORDER BY created_at DESC
            LIMIT 50
        ''')

        rows = cursor.fetchall()

    return jsonify({
        "status": "ok",
        "count": len(rows),
        "signals": _serialize_rows(rows)
    })


@signals_bp.route('/summary', methods=['GET'])
def get_signals_summary():
    """獲取信號摘要"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            SELECT status, COUNT(*) as count
            FROM signals
            GROUP BY status
        ''')

        status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

        cursor.execute('''
            SELECT COUNT(*) as cnt FROM signals
            WHERE DATE(created_at) = DATE(NOW())
        ''')
        today_count = cursor.fetchone()['cnt']

        # Also provide long/short counts for Dashboard compatibility
        cursor.execute('''
            SELECT signal_type, COUNT(*) as count
            FROM signals
            WHERE DATE(created_at) = DATE(NOW())
            GROUP BY signal_type
        ''')
        type_counts = {row['signal_type']: row['count'] for row in cursor.fetchall()}

    return jsonify({
        "status": "ok",
        "summary": {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
            "by_type": type_counts,
            "today": today_count
        }
    })
