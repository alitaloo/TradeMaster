#!/usr/bin/env python3
"""
Positions API Blueprint
持倉管理的 CRUD 接口
"""

from flask import Blueprint, jsonify, request
import pymysql
from pymysql.cursors import DictCursor
from api.db import get_db_connection
from datetime import datetime, timezone, timedelta
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import secrets
from functools import wraps
from flask import request as flask_request
from config.constants import DEFAULT_CAPITAL

_TZ_TAIPEI = timezone(timedelta(hours=8))

positions_bp = Blueprint('positions', __name__, url_prefix='/api/v1/positions')

API_BASE = 'http://localhost:8080/api/v1'

# ====== 認證相關函數（從 middleware/auth.py 導入）======
def hash_api_key(key):
    """Hash API Key"""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key):
    """驗證 API Key"""
    if not key:
        return None

    # 解析 key_id_key 格式
    parts = key.split('_')
    if len(parts) < 3:
        return None

    key_id = f"{parts[0]}_{parts[1]}"
    key_part = '_'.join(parts[2:])
    key_hash = hash_api_key(key_part)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor(DictCursor)
            cursor.execute(
                '''
                SELECT * FROM api_keys
                WHERE key_id = %s AND key_hash = %s AND is_active = 1
                ''',
                (key_id, key_hash)
            )
            row = cursor.fetchone()

            if row:
                # 更新最後使用時間
                cursor.execute(
                    "UPDATE api_keys SET last_used_at = %s WHERE key_id = %s",
                    (datetime.now().isoformat(), key_id)
                )
                conn.commit()
                return row
    except Exception:
        pass

    return None


def require_auth(f):
    """認證裝飾器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # 從 Header 獲取 API Key
        auth_header = flask_request.headers.get('Authorization', '')

        if not auth_header:
            return jsonify({'error': 'Missing Authorization header'}), 401

        # 支援 Bearer token 或直接 key
        if auth_header.startswith('Bearer '):
            api_key = auth_header[7:]
        else:
            api_key = auth_header

        # 驗證
        user = verify_api_key(api_key)

        if not user:
            return jsonify({'error': 'Invalid API key'}), 401

        # 傳遞用戶信息
        flask_request.api_user = user
        return f(*args, **kwargs)

    return decorated
# ====== 認證相關函數結束 ======


def row_to_dict(row):
    if row is None:
        return None
    # With DictCursor, row is already a dict
    return dict(row) if not isinstance(row, dict) else row


@positions_bp.route('', methods=['GET'])
def get_positions():
    """獲取持倉列表"""
    status = request.args.get('status')

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        query = "SELECT * FROM positions WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)

        query += " ORDER BY updated_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

    positions = [row for row in rows]

    return jsonify({
        "status": "ok",
        "count": len(positions),
        "positions": positions
    })


@positions_bp.route('/<symbol>', methods=['GET'])
def get_position(symbol):
    """獲取單個持倉"""
    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)
        cursor.execute("SELECT * FROM positions WHERE symbol = %s", (symbol.upper(),))
        row = cursor.fetchone()

    if not row:
        return jsonify({"status": "error", "message": "Position not found"}), 404

    return jsonify({
        "status": "ok",
        "position": row
    })


@positions_bp.route('', methods=['POST'])
@require_auth
def create_position():
    """創建持倉記錄"""
    data = request.json

    if not data or 'symbol' not in data:
        return jsonify({"status": "error", "message": "Missing symbol"}), 400

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 檢查是否已存在
        cursor.execute("SELECT id FROM positions WHERE symbol = %s", (data['symbol'].upper(),))
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "Position already exists"}), 400

        # 自動計算字段
        average_cost = data.get('average_cost') or data.get('entry_price') or 0
        current_quantity = data.get('current_quantity') or data.get('entry_quantity') or 0
        total_capital = data.get('total_capital') or DEFAULT_CAPITAL
        entry_total = data.get('entry_total') or (average_cost * current_quantity)
        current_value = current_quantity * average_cost
        unrealized_pnl = current_value - entry_total
        return_pct = (unrealized_pnl / entry_total * 100) if entry_total > 0 else 0

        cursor.execute('''
            INSERT INTO positions (symbol, quantity, avg_price, current_price, pnl, pnl_pct, open_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
        ''', (
            data['symbol'].upper(),
            data.get('quantity', 0),
            data.get('avg_price', 0),
            data.get('current_price', 0),
            data.get('pnl', 0),
            data.get('pnl_pct', 0),
            data.get('status', 'OPEN')
        ))

        position_id = cursor.lastrowid
        conn.commit()

    return jsonify({
        "status": "ok",
        "message": "Position created",
        "position_id": position_id
    }), 201


@positions_bp.route('/<symbol>', methods=['PUT'])
@require_auth
def update_position(symbol):
    """更新持倉"""
    data = request.json

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 先獲取現有數據
        cursor.execute("SELECT * FROM positions WHERE symbol = %s", (symbol.upper(),))
        row = cursor.fetchone()
        if not row:
            return jsonify({"status": "error", "message": "Position not found"}), 404

        # 現有值
        existing = row

        # 簡單更新 - 支援新舊欄位名稱
        updates = []
        params = []

        # 欄位映射
        field_map = {
            'quantity': 'quantity',
            'avg_price': 'avg_price',
            'average_cost': 'avg_price',
            'current_price': 'current_price',
            'status': 'status',
        }

        for old_field, new_field in field_map.items():
            if old_field in data:
                updates.append(f"{new_field} = %s")
                params.append(data[old_field])

        # 計算 PnL
        quantity = data.get('quantity') or data.get('current_quantity') or existing.get('quantity', 0)
        avg_price = data.get('avg_price') or data.get('average_cost') or existing.get('avg_price', 0)
        current_price = data.get('current_price') or existing.get('current_price', 0)

        if quantity and avg_price:
            pnl = (current_price - avg_price) * quantity
            pnl_pct = (current_price - avg_price) / avg_price * 100
            updates.extend(["pnl = %s", "pnl_pct = %s"])
            params.extend([pnl, pnl_pct])

        updates.append("updated_at = %s")
        params.append(datetime.now(_TZ_TAIPEI).isoformat())
        params.append(symbol.upper())

        cursor.execute(
            f"UPDATE positions SET {', '.join(updates)} WHERE symbol = %s",
            params
        )

        conn.commit()
        affected = cursor.rowcount

    if affected == 0:
        return jsonify({"status": "error", "message": "Position not found"}), 404

    return jsonify({
        "status": "ok",
        "message": "Position updated"
    })


@positions_bp.route('/<symbol>', methods=['DELETE'])
@require_auth
def delete_position(symbol):
    """刪除持倉"""
    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        cursor.execute("DELETE FROM positions WHERE symbol = %s", (symbol.upper(),))

        conn.commit()
        affected = cursor.rowcount

    if affected == 0:
        return jsonify({"status": "error", "message": "Position not found"}), 404

    return jsonify({
        "status": "ok",
        "message": "Position deleted"
    })


@positions_bp.route('/summary', methods=['GET'])
def get_positions_summary():
    """持倉摘要 - 從 K線獲取最新價格"""

    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 從 K線表獲取最新價格來計算總市值和浮動損益
        query = """
            SELECT
                p.symbol,
                p.quantity,
                p.avg_price,
                COALESCE(k.close_price, p.avg_price) as current_price
            FROM positions p
            LEFT JOIN (
                SELECT symbol, MAX(timestamp) as max_ts
                FROM kline_cache
                WHERE interval_val = '1d'
                GROUP BY symbol
            ) mk ON CONCAT('US.', p.symbol) = mk.symbol
            LEFT JOIN kline_cache k ON CONCAT('US.', p.symbol) = k.symbol AND k.interval_val = '1d' AND k.timestamp = mk.max_ts
            WHERE p.quantity > 0
        """
        cursor.execute(query)
        positions = cursor.fetchall()

        total_value = 0
        total_pnl = 0

        for pos in positions:
            qty = float(pos['quantity'] or 0)
            avg = float(pos['avg_price'] or 0)
            curr = float(pos['current_price'] or avg)

            total_value += qty * curr
            total_pnl += qty * (curr - avg)

        # 持倉數
        position_count = len(positions)

        # 總資金 (從 config 表獲取，否則用默認)
        try:
            cursor.execute("SELECT value FROM config WHERE name = 'total_capital'")
            row = cursor.fetchone()
            total_capital = float(row['value']) if row else DEFAULT_CAPITAL
        except Exception:
            total_capital = DEFAULT_CAPITAL

    # 可用資金 = 總資金 - 總市值
    available_cash = total_capital - total_value

    # 報酬率
    return_pct = (total_pnl / total_value * 100) if total_value > 0 else 0

    return jsonify({
        "status": "ok",
        "summary": {
            "total_value": total_value,
            "total_capital": total_capital,
            "available_cash": available_cash,
            "unrealized_pnl": total_pnl,
            "return_pct": return_pct,
            "position_count": position_count
        }
    })


def fetch_price_for_symbol(symbol: str, api_base: str = API_BASE) -> dict:
    """
    並發獲取單個股票價格
    
    Returns:
        dict: 包含 symbol, current_price, error 等字段
    """
    try:
        resp = requests.get(f"{api_base}/kline?symbol=US.{symbol}&interval=1d&limit=1", timeout=5)
        data = resp.json()

        if data.get('kline') and len(data['kline']) > 0:
            return {
                'symbol': symbol,
                'current_price': data['kline'][0]['close'],
                'success': True
            }
        else:
            return {'symbol': symbol, 'error': '無法獲取價格', 'success': False}
    except Exception as e:
        return {'symbol': symbol, 'error': str(e), 'success': False}


@positions_bp.route('/sync', methods=['POST'])
@require_auth
def sync_positions():
    """同步持倉價格 - 從 K-line API 並發獲取最新股價並更新浮動損益"""
    with get_db_connection() as conn:
        cursor = conn.cursor(DictCursor)

        # 獲取所有持倉 (數量 > 0)
        cursor.execute("SELECT * FROM positions WHERE quantity > 0")
        positions = cursor.fetchall()

        # 如果沒有持倉，直接返回
        if not positions:
            return jsonify({
                "status": "ok",
                "message": "無持倉需要同步",
                "updated": [],
                "errors": []
            })

        # 提取所有股票代碼
        symbols = [pos['symbol'] for pos in positions]

        # 使用 ThreadPoolExecutor 並發獲取價格
        updated = []
        errors = []
        
        # 根據持倉數量調整執行緒數（最多 10 個）
        max_workers = min(10, len(symbols))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任務
            future_to_symbol = {
                executor.submit(fetch_price_for_symbol, symbol): symbol 
                for symbol in symbols
            }
            
            # 收集結果
            results = {}
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result()
                    results[symbol] = result
                except Exception as e:
                    results[symbol] = {'symbol': symbol, 'error': str(e), 'success': False}

        # 根據結果更新持倉
        for pos in positions:
            symbol = pos['symbol']
            quantity = pos.get('current_quantity') or pos.get('quantity', 0)
            entry_total = pos.get('entry_total') or 0
            
            result = results.get(symbol, {})
            
            if result.get('success'):
                current_price = result['current_price']
                current_value = current_price * float(quantity)
                unrealized_pnl = current_value - float(entry_total)
                return_pct = (unrealized_pnl / float(entry_total) * 100) if entry_total > 0 else 0

                # 更新持倉
                cursor.execute('''
                    UPDATE positions
                    SET current_price = %s, current_value = %s, unrealized_pnl = %s, return_pct = %s, updated_at = %s
                    WHERE symbol = %s
                ''', (current_price, current_value, unrealized_pnl, return_pct, datetime.now(_TZ_TAIPEI).isoformat(), symbol))

                updated.append({
                    'symbol': symbol,
                    'current_price': current_price,
                    'current_value': current_value,
                    'unrealized_pnl': unrealized_pnl,
                    'return_pct': return_pct
                })
            else:
                errors.append(f"{symbol}: {result.get('error', 'Unknown error')}")

        conn.commit()

    return jsonify({
        "status": "ok",
        "message": f"同步完成: {len(updated)} 成功, {len(errors)} 失敗",
        "updated": updated,
        "errors": errors
    })
