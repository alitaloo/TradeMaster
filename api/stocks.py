#!/usr/bin/env python3
"""
Stocks API - 股票清單管理端點
管理回測股票和實盤股票的清單
已從 SQLite 遷移至 MySQL (2026-03-06)，透過 api/db.py (pymysql) 連線
"""

import uuid
from flask import Blueprint, jsonify, request
from datetime import datetime
from api.db import get_connection

stocks_bp = Blueprint('stocks', __name__, url_prefix='/api/v1/stocks')


def get_db_connection():
    """獲取 MySQL 數據庫連接"""
    return get_connection()


def row_to_dict(row):
    """將 DictCursor row 正規化成字典"""
    if row is None:
        return None
    return dict(row)


@stocks_bp.route('', methods=['GET'])
def get_stocks():
    """獲取所有股票或按類型篩選"""
    stock_type = request.args.get('type')
    show_disabled = request.args.get('show_all', 'false').lower() == 'true'

    conn = get_db_connection()
    cursor = conn.cursor()

    if stock_type == 'backtest':
        query = 'SELECT * FROM stocks WHERE type=%s AND needsBacktest=1'
        params = ['live']
    elif stock_type == 'live':
        query = 'SELECT * FROM stocks WHERE type=%s'
        params = ['live']
    else:
        query = 'SELECT * FROM stocks WHERE type=%s'
        params = ['live']

    if not show_disabled:
        query += ' AND enabled=1'

    query += ' ORDER BY symbol ASC'
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    stocks = [row_to_dict(row) for row in rows]

    return jsonify({
        "status": "ok",
        "count": len(stocks),
        "type": stock_type or "all",
        "stocks": stocks
    })


@stocks_bp.route('', methods=['POST'])
def create_stock():
    """創建新股票（只能是實盤股票）"""
    data = request.json

    if not data:
        return jsonify({"status": "error", "message": "Request body is required"}), 400

    if 'symbol' not in data:
        return jsonify({"status": "error", "message": "Symbol is required"}), 400

    symbol = data['symbol'].upper()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM stocks WHERE symbol=%s', (symbol,))
    if cursor.fetchone():
        conn.close()
        return jsonify({
            "status": "error",
            "message": f"Stock {symbol} already exists in the list"
        }), 400

    stock_id = f"lv_{uuid.uuid4().hex[:6]}"
    now = datetime.utcnow().isoformat() + "Z"

    stock = {
        "id": stock_id,
        "symbol": symbol,
        "name": data.get('name', symbol),
        "type": "live",
        "enabled": bool(data.get('enabled', True)),
        "needsBacktest": bool(data.get('needsBacktest', False)),
        "created_at": now,
    }

    cursor.execute(
        '''
        INSERT INTO stocks (id, symbol, name, type, enabled, needsBacktest, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''',
        (
            stock['id'], stock['symbol'], stock['name'], stock['type'],
            1 if stock['enabled'] else 0,
            1 if stock['needsBacktest'] else 0,
            stock['created_at'],
        ),
    )

    conn.commit()
    conn.close()

    return jsonify({
        "status": "ok",
        "message": "Stock created successfully",
        "stock": stock
    }), 201


@stocks_bp.route('/<stock_id>', methods=['GET'])
def get_stock(stock_id):
    """獲取特定股票"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stocks WHERE id=%s', (stock_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"status": "error", "message": "Stock not found"}), 404

    return jsonify({"status": "ok", "stock": row_to_dict(row)})


@stocks_bp.route('/<stock_id>', methods=['PUT'])
def update_stock(stock_id):
    """更新股票"""
    data = request.json

    if not data:
        return jsonify({"status": "error", "message": "Request body is required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM stocks WHERE id=%s', (stock_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "Stock not found"}), 404

    updates = []
    params = []

    if 'name' in data:
        updates.append('name=%s')
        params.append(data['name'])
    if 'symbol' in data:
        updates.append('symbol=%s')
        params.append(data['symbol'].upper())
    if 'enabled' in data:
        updates.append('enabled=%s')
        params.append(1 if data['enabled'] else 0)
    if 'needsBacktest' in data:
        updates.append('needsBacktest=%s')
        params.append(1 if data['needsBacktest'] else 0)

    if updates:
        updates.append('updated_at=%s')
        params.append(datetime.utcnow().isoformat() + 'Z')
        params.append(stock_id)
        query = f"UPDATE stocks SET {', '.join(updates)} WHERE id=%s"
        cursor.execute(query, params)
        conn.commit()

    cursor.execute('SELECT * FROM stocks WHERE id=%s', (stock_id,))
    row = cursor.fetchone()
    conn.close()

    return jsonify({
        "status": "ok",
        "message": "Stock updated successfully",
        "stock": row_to_dict(row)
    })


@stocks_bp.route('/<stock_id>', methods=['DELETE'])
def delete_stock(stock_id):
    """刪除股票"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM stocks WHERE id=%s', (stock_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    if not deleted:
        return jsonify({"status": "error", "message": "Stock not found"}), 404

    return jsonify({"status": "ok", "message": "Stock deleted successfully"})


@stocks_bp.route('/backtest', methods=['GET'])
def get_backtest_stocks():
    """獲取回測股票（= 實盤股票中 needsBacktest=True 的）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stocks WHERE type=%s AND needsBacktest=1 AND enabled=1 ORDER BY symbol ASC', ('live',))
    rows = cursor.fetchall()
    conn.close()

    stocks = [row_to_dict(row) for row in rows]
    return jsonify({"status": "ok", "count": len(stocks), "type": "backtest", "stocks": stocks})


@stocks_bp.route('/live', methods=['GET'])
def get_live_stocks():
    """獲取實盤股票"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stocks WHERE type=%s AND enabled=1 ORDER BY symbol ASC', ('live',))
    rows = cursor.fetchall()
    conn.close()

    stocks = [row_to_dict(row) for row in rows]
    return jsonify({"status": "ok", "count": len(stocks), "type": "live", "stocks": stocks})


@stocks_bp.route('/toggle/<stock_id>', methods=['PUT', 'POST'])
def toggle_stock(stock_id):
    """切換股票狀態"""
    data = request.json or {}
    enabled = bool(data.get('enabled'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stocks WHERE id=%s', (stock_id,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return jsonify({"status": "error", "message": "Stock not found"}), 404

    cursor.execute(
        'UPDATE stocks SET enabled=%s, updated_at=%s WHERE id=%s',
        (1 if enabled else 0, datetime.utcnow().isoformat() + 'Z', stock_id)
    )
    conn.commit()
    conn.close()

    return jsonify({"status": "ok", "stock_id": stock_id, "enabled": enabled})


@stocks_bp.route('/summary', methods=['GET'])
def get_summary():
    """獲取股票清單摘要"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) AS count FROM stocks WHERE type=%s AND enabled=1', ('live',))
    live_count = cursor.fetchone()['count']

    cursor.execute('SELECT COUNT(*) AS count FROM stocks WHERE type=%s AND needsBacktest=1 AND enabled=1', ('live',))
    backtest_count = cursor.fetchone()['count']

    conn.close()

    return jsonify({
        "status": "ok",
        "summary": {
            "backtest": {"count": backtest_count, "enabled": backtest_count},
            "live": {"count": live_count, "enabled": live_count},
            "total": live_count,
        }
    })
