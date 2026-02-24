"""
K線數據 API
本地 SQLite 快取 + 富途數據源

策略：
1. 使用本地 SQLite 數據庫存儲 K 線
2. 通過 scripts/futu_update_aapl.py 定期更新數據
3. API 僅讀取本地快取
"""

from flask import Blueprint, jsonify, request
import pymysql
from api.db import get_connection
import os
from datetime import datetime

kline_bp = Blueprint('kline', __name__)

# 數據庫路徑
# Using MySQL
# DB_PATH not needed for MySQL

# 默認股票池（實盤）
DEFAULT_WATCHLIST = [
    {"symbol": "AAPL", "name": "Apple", "type": "live"},
    {"symbol": "MSFT", "name": "Microsoft", "type": "live"},
    {"symbol": "NVDA", "name": "NVIDIA", "type": "live"},
    {"symbol": "TSM", "name": "TSMC", "type": "live"},
    {"symbol": "AMZN", "name": "Amazon", "type": "live"},
    {"symbol": "META", "name": "Meta", "type": "live"},
    {"symbol": "UBER", "name": "Uber", "type": "live"},
    {"symbol": "MU", "name": "Micron", "type": "live"},
    {"symbol": "AMD", "name": "AMD", "type": "live"},
    {"symbol": "ORCL", "name": "Oracle", "type": "live"},
    {"symbol": "GOOGL", "name": "Google", "type": "live"},
    {"symbol": "GOOG", "name": "Google", "type": "live"},
    {"symbol": "NFLX", "name": "Netflix", "type": "live"},
    {"symbol": "ADBE", "name": "Adobe", "type": "live"},
    {"symbol": "CRM", "name": "Salesforce", "type": "live"},
    {"symbol": "QCOM", "name": "Qualcomm", "type": "live"},
    {"symbol": "TXN", "name": "Texas Instruments", "type": "live"},
    {"symbol": "AVGO", "name": "Broadcom", "type": "live"},
    {"symbol": "COIN", "name": "Coinbase", "type": "live"},
    {"symbol": "MSTR", "name": "MicroStrategy", "type": "live"},
]

def init_db():
    """初始化數據庫"""
    # Using MySQL - no local file needed
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # K線快取表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kline_cache (
            symbol TEXT NOT NULL,
            interval_val TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL,
            volume INTEGER,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (symbol, interval_val, timestamp)
        )
    ''')
    
    # 股票清單表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_list (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            type TEXT DEFAULT 'live',
            is_backtest BOOLEAN DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    
    # 如果 stock_list 為空，插入默認值
    cursor.execute('SELECT COUNT(*) FROM stock_list')
    if cursor.fetchone()[0] == 0:
        now = datetime.now().isoformat()
        for stock in DEFAULT_WATCHLIST:
            cursor.execute('''
                INSERT INTO stock_list (symbol, name, type, is_backtest, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            ''', (stock['symbol'], stock['name'], stock['type'], 0, now, now))
    
    conn.commit()
    conn.close()

def get_cached_kline(symbol, interval, limit=2000):
    """獲取本地快取的 K 線數據"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT timestamp, open_price, high_price, low_price, close_price, volume
        FROM kline_cache
        WHERE symbol = %s AND interval_val = %s
        ORDER BY timestamp DESC
        LIMIT %s
    ''', (symbol, interval, limit))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return []
    
    # 按時間正序返回 (支援 DictCursor 和 tuple)
    result = []
    for row in rows:
        if isinstance(row, dict):
            result.append({
                "timestamp": row.get('timestamp'),
                "open": row.get('open_price'),
                "high": row.get('high_price'),
                "low": row.get('low_price'),
                "close": row.get('close_price'),
                "volume": row.get('volume')
            })
        else:
            result.append({
                "timestamp": row[0],
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5]
            })
    return result[::-1]

def save_kline_to_cache(symbol, interval, kline_list):
    """保存 K 線數據到本地快取"""
    if not kline_list:
        return False
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    for kline in kline_list:
        cursor.execute('''
            INSERT OR REPLACE INTO kline_cache
            (symbol, interval_val, timestamp, open_price, high_price, low_price, close_price, volume, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            symbol, interval,
            kline.get('timestamp') or kline.get('time_key'),
            kline.get('open'), kline.get('high'), 
            kline.get('low'), kline.get('close'),
            kline.get('volume'), now
        ))
    
    # 更新元數據
    cursor.execute('''
        INSERT OR REPLACE INTO cache_meta (symbol, interval_val, last_update)
        VALUES (%s, %s, %s)
    ''', (symbol, interval, now))
    
    conn.commit()
    conn.close()
    return True

# ==================== API 端點 ====================

@kline_bp.route('/api/v1/kline', methods=['GET'])
def get_kline():
    """獲取 K 線數據（本地快取）"""
    symbol = request.args.get('symbol', 'AAPL').upper()
    interval = request.args.get('interval', '5m')
    limit = int(request.args.get('limit', 2000))
    
    # 保留 US. 前綴（數據庫中有 US. 前綴）
    # if symbol.startswith('US.'):
    #     symbol = symbol[3:]
    
    # 直接返回本地快取數據
    kline_data = get_cached_kline(symbol, interval, limit)
    
    # 獲取最新數據的時間戳作為 data_timestamp
    data_timestamp = None
    if kline_data:
        data_timestamp = kline_data[-1].get('timestamp')
    
    return jsonify({
        "symbol": symbol,
        "interval": interval,
        "source": "cache",
        "count": len(kline_data),
        "kline": kline_data,
        "data_timestamp": data_timestamp,
        "timestamp": datetime.now().isoformat()
    })

@kline_bp.route('/api/v1/kline/history', methods=['GET'])
def get_kline_history():
    """獲取歷史 K 線數據（指定時間戳之前的數據）"""
    symbol = request.args.get('symbol', 'AAPL').upper()
    interval = request.args.get('interval', '5m')
    before = request.args.get('before')
    limit = int(request.args.get('limit', 100))
    
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'
    
    if not before:
        return jsonify({
            "error": "Missing 'before' parameter",
            "example": "/api/v1/kline/history%ssymbol=AAPL&interval=5m&before=2025-01-01T00:00:00&limit=100"
        }), 400
    
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT timestamp, open_price, high_price, low_price, close_price, volume
            FROM kline_cache
            WHERE symbol = %s AND interval_val = %s AND timestamp < %s
            ORDER BY timestamp ASC
            LIMIT %s
        ''', (symbol, interval, before, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        kline_data = [{
            "timestamp": row[0],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5]
        } for row in rows]
        
        return jsonify({
            "symbol": symbol,
            "interval": interval,
            "before": before,
            "count": len(kline_data),
            "kline": kline_data
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e),
            "symbol": symbol
        }), 500

@kline_bp.route('/api/v1/watchlist', methods=['GET'])
def get_watchlist():
    """獲取股票清單（從數據庫）"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT symbol, name, type, is_backtest FROM stock_list ORDER BY symbol')
    rows = cursor.fetchall()
    conn.close()
    
    stocks = [{"symbol": row[0], "name": row[1], "type": row[2], "is_backtest": bool(row[3])} for row in rows]
    
    return jsonify({
        "watchlist": stocks,
        "count": len(stocks)
    })

@kline_bp.route('/api/v1/watchlist/add', methods=['POST'])
def add_stock():
    """添加股票到清單"""
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    name = data.get('name', symbol)
    is_backtest = data.get('is_backtest', False)
    
    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO stock_list (symbol, name, type, is_backtest, created_at, updated_at)
            VALUES (%s, %s, 'live', %s, %s, %s)
        ''', (symbol, name, 1 if is_backtest else 0, now, now))
        
        conn.commit()
        success = True
    except Exception as e:
        success = False
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()
    
    return jsonify({"status": "ok", "symbol": symbol, "is_backtest": is_backtest})

@kline_bp.route('/api/v1/watchlist/remove', methods=['POST'])
def remove_stock():
    """從清單中移除股票"""
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    
    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM stock_list WHERE symbol = %s', (symbol,))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "ok", "symbol": symbol})

@kline_bp.route('/api/v1/watchlist/backtest', methods=['POST'])
def toggle_backtest():
    """標記/取消標記回測股票"""
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    is_backtest = data.get('is_backtest', True)
    
    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    cursor.execute('''
        UPDATE stock_list SET is_backtest = %s, updated_at = %s WHERE symbol = %s
    ''', (1 if is_backtest else 0, now, symbol))
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "ok", "symbol": symbol, "is_backtest": is_backtest})

@kline_bp.route('/api/v1/watchlist/reset', methods=['POST'])
def reset_watchlist():
    """重置股票清單為默認值"""
    conn = get_connection()
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    # 清空並重新插入
    cursor.execute('DELETE FROM stock_list')
    for stock in DEFAULT_WATCHLIST:
        cursor.execute('''
            INSERT INTO stock_list (symbol, name, type, is_backtest, created_at, updated_at)
            VALUES (%s, %s, %s, 0, %s, %s)
        ''', (stock['symbol'], stock['name'], stock['type'], now, now))
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "ok", "message": "Watchlist reset to default"})

@kline_bp.route('/api/v1/kline/batch', methods=['GET'])
def batch_get_kline():
    """批量獲取多個股票的 K 線數據"""
    # 從數據庫獲取股票清單
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT symbol FROM stock_list')
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    interval = request.args.get('interval', '5m')
    
    results = {}
    
    for symbol in symbols:
        symbol = symbol.strip().upper()
        if not symbol:
            continue
        
        if not symbol.startswith('US.'):
            full_symbol = f'US.{symbol}'
        else:
            full_symbol = symbol
        
        kline_data = get_cached_kline(full_symbol, interval)
        results[symbol] = {
            "status": "ok",
            "source": "cache",
            "count": len(kline_data),
            "kline": kline_data
        }
    
    return jsonify({
        "interval": interval,
        "results": results,
        "timestamp": datetime.now().isoformat()
    })

@kline_bp.route('/api/v1/cache/status', methods=['GET'])
def cache_status():
    """查看快取狀態"""
    # 從數據庫獲取股票清單
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT symbol FROM stock_list')
    symbols = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    conn = get_connection()
    cursor = conn.cursor()
    
    status = {}
    for symbol in symbols:
        full_symbol = f'US.{symbol}'
        for interval in ['5m', '1h', '1d']:
            key = f'{symbol}_{interval}'
            cursor.execute(
                'SELECT COUNT(*), MAX(timestamp) FROM kline_cache WHERE symbol=%s AND interval_val=%s',
                (full_symbol, interval)
            )
            count, latest = cursor.fetchone()
            status[key] = {
                "count": count,
                "latest": latest
            }
    
    conn.close()
    
    return jsonify({
        "status": "ok",
        "cache": status,
        "timestamp": datetime.now().isoformat()
    })

@kline_bp.route('/api/v1/cache/refresh', methods=['POST'])
def refresh_cache():
    """手動刷新快取（標記需要更新）"""
    symbol = request.args.get('symbol', 'AAPL').upper()
    interval = request.args.get('interval', '5m')
    
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        'DELETE FROM cache_meta WHERE symbol=%s AND interval_val=%s',
        (symbol, interval)
    )
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "ok",
        "message": f"{symbol} {interval} cache marked for refresh",
        "note": "Run futu_update_aapl.py to actually update data"
    })

# 初始化數據庫
# init_db() - table already exists in MySQL
