#!/usr/bin/env python3
"""
Live Trading API Blueprint
真實交易接口 - 從富途 API 獲取持倉和訂單
"""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

live_bp = Blueprint('live', __name__, url_prefix='/api/v1/live')


def get_live_trading_enabled():
    """檢查真實交易是否啟用"""
    from api.db import get_db_connection
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT config_value FROM system_config WHERE config_key = 'live_trading_enabled'",
        )
        row = cursor.fetchone()
    return row and row['config_value'] == 'true'


@live_bp.route('/status', methods=['GET'])
def live_status():
    """檢查真實交易狀態和開關"""
    enabled = get_live_trading_enabled()
    return jsonify({
        'enabled': enabled,
        'mode': 'live' if enabled else 'paper'
    })


@live_bp.route('/positions', methods=['GET'])
def live_positions():
    """從 Futu 查詢真實持倉"""
    if not get_live_trading_enabled():
        return jsonify({'status': 'error', 'message': '真實交易未啟用'}), 403
    
    try:
        from futu import OpenUSTradeContext, TrdEnv
        
        ctx = OpenUSTradeContext(host='127.0.0.1', port=11111)
        ret, data = ctx.position_list_query(trd_env=TrdEnv.REAL)
        ctx.close()
        
        if ret != 0:
            logger.error(f"Failed to query live positions: {data}")
            return jsonify({'status': 'error', 'message': str(data)}), 500
        
        positions = []
        if data is not None and not data.empty:
            for _, row in data.iterrows():
                qty = float(row.get('qty', 0))
                if qty > 0:
                    positions.append({
                        'symbol': row.get('code'),
                        'quantity': int(qty),
                        'average_cost': float(row.get('cost_price', 0)),
                        'current_price': float(row.get('nominal_price', 0)),
                        'market_value': float(row.get('market_val', 0)),
                        'unrealized_pnl': float(row.get('pl_val', 0)),
                        'unrealized_pnl_pct': float(row.get('pl_ratio', 0)) * 100 if row.get('pl_ratio') else 0,
                    })
        
        return jsonify({'status': 'ok', 'positions': positions, 'count': len(positions)})
    except Exception as e:
        logger.error(f"Error querying live positions: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@live_bp.route('/orders', methods=['GET'])
def live_orders():
    """從 Futu 查詢真實訂單"""
    if not get_live_trading_enabled():
        return jsonify({'status': 'error', 'message': '真實交易未啟用'}), 403
    
    try:
        from futu import OpenUSTradeContext, TrdEnv
        
        ctx = OpenUSTradeContext(host='127.0.0.1', port=11111)
        ret, data = ctx.history_order_list_query(trd_env=TrdEnv.REAL)
        ctx.close()
        
        if ret != 0:
            logger.error(f"Failed to query live orders: {data}")
            return jsonify({'status': 'error', 'message': str(data)}), 500
        
        orders = []
        if data is not None and not data.empty:
            for _, row in data.iterrows():
                orders.append({
                    'order_id': str(row.get('order_id', '')),
                    'symbol': row.get('code', ''),
                    'order_type': 'BUY' if str(row.get('trd_side', '')).upper() == 'BUY' else 'SELL',
                    'quantity': int(float(row.get('qty', 0))),
                    'price': float(row.get('price', 0)),
                    'filled_quantity': int(float(row.get('dealt_qty', 0))),
                    'filled_price': float(row.get('dealt_avg_price', 0)),
                    'status': str(row.get('order_status', '')).lower(),
                    'created_at': str(row.get('create_time', '')),
                })
        
        return jsonify({'status': 'ok', 'orders': orders, 'count': len(orders)})
    except Exception as e:
        logger.error(f"Error querying live orders: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
