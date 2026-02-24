#!/usr/bin/env python3
"""
Market API Blueprint
市場數據接口 (VIX, 市場漲跌幅等)
"""

from flask import Blueprint, jsonify, request
import pymysql
from api.db import get_connection
from datetime import datetime

market_bp = Blueprint('market', __name__, url_prefix='/api/v1/market')

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/trademaster.db'


def get_db_connection():
    conn = get_connection()
    # conn.row_factory = dict
    return conn


# def init_market_db():
    """初始化 market 表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type VARCHAR NOT NULL,
            value REAL DEFAULT 0,
            source VARCHAR,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(type)
        )
    ''')
    
    conn.commit()
    conn.close()


# 初始化
# init_market_db()


@market_bp.route('', methods=['GET'])
def get_market_data():
    """獲取市場數據"""
    market_type = request.args.get('type')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if market_type:
        cursor.execute("SELECT * FROM market WHERE type = %s", (market_type.upper(),))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({
                "status": "ok",
                "type": market_type.upper(),
                "value": None
            })
        
        return jsonify({
            "status": "ok",
            "market": dict(row)
        })
    else:
        cursor.execute("SELECT * FROM market ORDER BY type")
        rows = cursor.fetchall()
        conn.close()
        
        markets = [dict(row) for row in rows]
        
        return jsonify({
            "status": "ok",
            "count": len(markets),
            "markets": markets
        })


@market_bp.route('/<market_type>', methods=['GET'])
def get_market_by_type(market_type):
    """根據類型獲取市場數據"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM market WHERE type = %s", (market_type.upper(),))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return jsonify({
            "status": "ok",
            "type": market_type.upper(),
            "value": None,
            "message": "No data available"
        })
    
    return jsonify({
        "status": "ok",
        "market": dict(row)
    })


@market_bp.route('', methods=['POST'])
def update_market_data():
    """更新市場數據"""
    data = request.json
    
    if not data or 'type' not in data:
        return jsonify({"status": "error", "message": "Missing type"}), 400
    
    market_type = data['type'].upper()
    value = data.get('value', 0)
    source = data.get('source', 'manual')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 使用 INSERT OR REPLACE 來實現 upsert
    cursor.execute('''
        INSERT INTO market (type, value, source, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT(type) DO UPDATE SET
            value = excluded.value,
            source = excluded.source,
            updated_at = excluded.updated_at
    ''', (market_type, value, source, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": f"Market data updated: {market_type} = {value}"
    })


@market_bp.route('/bulk', methods=['POST'])
def bulk_update_market():
    """批量更新市場數據"""
    data = request.json
    
    if not isinstance(data, list):
        return jsonify({"status": "error", "message": "Expected array of market data"}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    updated = []
    for item in data:
        market_type = item.get('type', '').upper()
        value = item.get('value', 0)
        source = item.get('source', 'bulk')
        
        if market_type:
            cursor.execute('''
                INSERT INTO market (type, value, source, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(type) DO UPDATE SET
                    value = excluded.value,
                    source = excluded.source,
                    updated_at = excluded.updated_at
            ''', (market_type, value, source, datetime.now().isoformat()))
            updated.append(market_type)
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": f"Updated {len(updated)} market types",
        "updated": updated
    })


# 便捷函數
def get_vix():
    """獲取 VIX 值"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM market WHERE type = 'VIX'")
    row = cursor.fetchone()
    conn.close()
    
    return row['value'] if row else None


def get_market_drop():
    """獲取市場漲跌幅"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT value FROM market WHERE type = 'MARKET_DROP'")
    row = cursor.fetchone()
    conn.close()
    
    return row['value'] if row else 0
