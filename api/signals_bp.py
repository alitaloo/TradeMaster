#!/usr/bin/env python3
"""
Signals API Blueprint
交易信號的 CRUD 接口 - MySQL
"""

from flask import Blueprint, jsonify, request
import json
from datetime import datetime
from pathlib import Path

signals_bp = Blueprint('signals', __name__, url_prefix='/api/v1/signals')


@signals_bp.route('', methods=['GET'])
def get_signals():
    """獲取信號列表"""
    from api.db import get_connection
    
    status = request.args.get('status')
    symbol = request.args.get('symbol')
    limit = int(request.args.get('limit', 100))
    
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM signals WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = %s"
        params.append(status)
    
    if symbol:
        query += " AND symbol = %s"
        params.append(symbol)
    
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "signals": rows
    })


@signals_bp.route('/<int:signal_id>', methods=['GET'])
def get_signal(signal_id):
    """獲取單個信號"""
    from api.db import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM signals WHERE id = %s", (signal_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({"status": "error", "message": "Signal not found"}), 404
    
    return jsonify({
        "status": "ok",
        "signal": row
    })


@signals_bp.route('', methods=['POST'])
def create_signal():
    """創建新信號"""
    from api.db import get_connection
    
    data = request.json
    
    if not data or 'symbol' not in data or 'signal_type' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
    # HOLD 信號自動標記為 IGNORED
    signal_type = data.get('signal_type')
    status = data.get('status', 'PENDING')
    if signal_type == 'HOLD':
        status = 'IGNORED'
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO signals (symbol, strategy_type, signal_type, price, quantity, 
                          confidence, status, risk_score, news_weight, stop_loss, 
                          take_profit, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        json.dumps(data.get('metadata', {}))
    ))
    
    signal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": "Signal created",
        "signal_id": signal_id
    }), 201


@signals_bp.route('/<int:signal_id>', methods=['PUT'])
def update_signal(signal_id):
    """更新信號"""
    from api.db import get_connection
    
    data = request.json
    
    conn = get_connection()
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
    conn.close()
    
    if affected == 0:
        return jsonify({"status": "error", "message": "Signal not found"}), 404
    
    return jsonify({
        "status": "ok",
        "message": "Signal updated"
    })


@signals_bp.route('/<int:signal_id>', methods=['DELETE'])
def delete_signal(signal_id):
    """刪除信號"""
    from api.db import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM signals WHERE id = %s", (signal_id,))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    if affected == 0:
        return jsonify({"status": "error", "message": "Signal not found"}), 404
    
    return jsonify({
        "status": "ok",
        "message": "Signal deleted"
    })


@signals_bp.route('/active', methods=['GET'])
def get_active_signals():
    """獲取活躍信號"""
    from api.db import get_connection
    
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM signals 
        WHERE status IN ('PENDING', 'SENT')
        ORDER BY created_at DESC
        LIMIT 50
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "count": len(rows),
        "signals": rows
    })


@signals_bp.route('/summary', methods=['GET'])
def get_signals_summary():
    """獲取信號摘要"""
    from api.db import get_connection
    
    conn = get_connection()
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
    
    conn.close()
    
    return jsonify({
        "status": "ok",
        "summary": {
            "total": sum(status_counts.values()),
            "by_status": status_counts,
            "today": today_count
        }
    })
