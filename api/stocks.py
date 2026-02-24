#!/usr/bin/env python3
"""
Stocks API - 股票清單管理端點
管理回測股票和實盤股票的清單
使用 SQLite 數據庫持久化存儲
"""

import os
import uuid
import sqlite3
from flask import Blueprint, jsonify, request
from datetime import datetime
from api.db import get_connection

stocks_bp = Blueprint('stocks', __name__, url_prefix='/api/v1/stocks')

# 數據庫路徑
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'trademaster.db')


def init_db():
    """初始化數據庫"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 創建股票表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            name TEXT,
            type TEXT NOT NULL DEFAULT 'live',
            enabled INTEGER NOT NULL DEFAULT 1,
            needsBacktest INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT
        )
    ''')
    
    # 創建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_symbol ON stocks(symbol)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_type ON stocks(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stocks_enabled ON stocks(enabled)')
    
    conn.commit()
    conn.close()


def get_db_connection():
    """獲取數據庫連接"""
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    return conn


# 初始化數據庫
# init_db()


def row_to_dict(row):
    """將 Row 轉換為字典"""
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
    
    # 構建查詢
    if stock_type == 'backtest':
        # 回測股票 = 實盤股票中 needsBacktest=1
        query = 'SELECT * FROM stocks WHERE type="live" AND needsBacktest=1'
        params = ()
    elif stock_type == 'live':
        query = 'SELECT * FROM stocks WHERE type="live"'
        params = ()
    else:
        query = 'SELECT * FROM stocks WHERE type="live"'
        params = ()
    
    if not show_disabled:
        query += ' AND enabled=1'
    
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
        return jsonify({
            "status": "error",
            "message": "Request body is required"
        }), 400
    
    # 驗證必填欄位
    if 'symbol' not in data:
        return jsonify({
            "status": "error",
            "message": "Symbol is required"
        }), 400
    
    symbol = data['symbol'].upper()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 檢查是否已存在
    cursor.execute('SELECT id FROM stocks WHERE symbol=?', (symbol,))
    if cursor.fetchone():
        conn.close()
        return jsonify({
            "status": "error",
            "message": f"Stock {symbol} already exists in the list"
        }), 400
    
    # 生成唯一 ID
    stock_id = f"lv_{uuid.uuid4().hex[:6]}"
    now = datetime.utcnow().isoformat() + "Z"
    
    stock = {
        "id": stock_id,
        "symbol": symbol,
        "name": data.get('name', symbol),
        "type": "live",  # 只能是實盤
        "enabled": data.get('enabled', True),
        "needsBacktest": data.get('needsBacktest', False),
        "created_at": now
    }
    
    # 插入數據庫
    cursor.execute('''
        INSERT INTO stocks (id, symbol, name, type, enabled, needsBacktest, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (stock['id'], stock['symbol'], stock['name'], stock['type'], 
          1 if stock['enabled'] else 0, 1 if stock['needsBacktest'] else 0, stock['created_at']))
    
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
    cursor.execute('SELECT * FROM stocks WHERE id=?', (stock_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({
            "status": "error",
            "message": "Stock not found"
        }), 404
    
    return jsonify({
        "status": "ok",
        "stock": row_to_dict(row)
    })


@stocks_bp.route('/<stock_id>', methods=['PUT'])
def update_stock(stock_id):
    """更新股票"""
    data = request.json
    
    if not data:
        return jsonify({
            "status": "error",
            "message": "Request body is required"
        }), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 查找股票
    cursor.execute('SELECT * FROM stocks WHERE id=?', (stock_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({
            "status": "error",
            "message": "Stock not found"
        }), 404
    
    # 構建更新語句
    updates = []
    params = []
    
    if 'name' in data:
        updates.append('name=?')
        params.append(data['name'])
    if 'symbol' in data:
        updates.append('symbol=?')
        params.append(data['symbol'].upper())
    if 'enabled' in data:
        updates.append('enabled=?')
        params.append(1 if data['enabled'] else 0)
    if 'needsBacktest' in data:
        updates.append('needsBacktest=?')
        params.append(1 if data['needsBacktest'] else 0)
    # type 不可修改
    
    if updates:
        updates.append('updated_at=?')
        params.append(datetime.utcnow().isoformat() + "Z")
        params.append(stock_id)
        
        query = f"UPDATE stocks SET {', '.join(updates)} WHERE id=?"
        cursor.execute(query, params)
        conn.commit()
    
    # 獲取更新後的數據
    cursor.execute('SELECT * FROM stocks WHERE id=?', (stock_id,))
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
    
    cursor.execute('DELETE FROM stocks WHERE id=?', (stock_id,))
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    if not deleted:
        return jsonify({
            "status": "error",
            "message": "Stock not found"
        }), 404
    
    return jsonify({
        "status": "ok",
        "message": "Stock deleted successfully"
    })


@stocks_bp.route('/backtest', methods=['GET'])
def get_backtest_stocks():
    """獲取回測股票（= 實盤股票中 needsBacktest=True 的）"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stocks WHERE type="live" AND needsBacktest=1 AND enabled=1')
    rows = cursor.fetchall()
    conn.close()
    
    stocks = [row_to_dict(row) for row in rows]
    
    return jsonify({
        "status": "ok",
        "count": len(stocks),
        "type": "backtest",
        "stocks": stocks
    })


@stocks_bp.route('/live', methods=['GET'])
def get_live_stocks():
    """獲取實盤股票"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM stocks WHERE type="live" AND enabled=1')
    rows = cursor.fetchall()
    conn.close()
    
    stocks = [row_to_dict(row) for row in rows]
    
    return jsonify({
        "status": "ok",
        "count": len(stocks),
        "type": "live",
        "stocks": stocks
    })


@stocks_bp.route('/toggle/<stock_id>', methods=['PUT', 'POST'])
def toggle_stock(stock_id):
    """切換股票狀態"""
    data = request.json or {}
    enabled = data.get('enabled')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM stocks WHERE id=?', (stock_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({
            "status": "error",
            "message": "Stock not found"
        }), 404
    
    cursor.execute('UPDATE stocks SET enabled=?, updated_at=? WHERE id=?', 
                  (1 if enabled else 0, datetime.utcnow().isoformat() + "Z", stock_id))
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "stock_id": stock_id,
        "enabled": enabled
    })


@stocks_bp.route('/summary', methods=['GET'])
def get_summary():
    """獲取股票清單摘要"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 總實盤股票數
    cursor.execute('SELECT COUNT(*) FROM stocks WHERE type="live" AND enabled=1')
    live_count = cursor.fetchone()[0]
    
    # 回測股票數（needsBacktest=1）
    cursor.execute('SELECT COUNT(*) FROM stocks WHERE type="live" AND needsBacktest=1 AND enabled=1')
    backtest_count = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        "status": "ok",
        "summary": {
            "backtest": {
                "count": backtest_count,
                "enabled": backtest_count
            },
            "live": {
                "count": live_count,
                "enabled": live_count
            },
            "total": live_count
        }
    })
