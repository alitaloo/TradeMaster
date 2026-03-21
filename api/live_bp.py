#!/usr/bin/env python3
"""
Live Trading API Blueprint
真實交易接口 - 從富途 API 獲取持倉和訂單
FUTUSG + TrdMarket.US + unlock_trade
"""

import logging
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

live_bp = Blueprint('live', __name__, url_prefix='/api/v1/live')

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111


def get_live_trading_enabled():
    from config.database import get_db_cursor
    try:
        with get_db_cursor() as c:
            c.execute("SELECT config_value FROM system_config WHERE config_key='live_trading_enabled'")
            row = c.fetchone()
            return row and row['config_value'] == 'true'
    except:
        return False


def get_trade_password():
    """從 system_config 讀取交易密碼（加密存儲）"""
    from config.database import get_db_cursor
    try:
        with get_db_cursor() as c:
            c.execute("SELECT config_value FROM system_config WHERE config_key='live_trade_password'")
            row = c.fetchone()
            return row['config_value'] if row else None
    except:
        return None


def get_live_ctx():
    """取得真實交易 context（FUTUSG + US + 協議加密 + 解鎖）"""
    from futu import OpenSecTradeContext, TrdMarket, SecurityFirm
    ctx = OpenSecTradeContext(
        filter_trdmarket=TrdMarket.US,
        host=FUTU_HOST, port=FUTU_PORT,
        security_firm=SecurityFirm.FUTUSG
        # is_encrypt=True 需要先在 OpenD 設定 RSA 公鑰才能啟用
    )
    pwd = get_trade_password()
    if pwd:
        ret, msg = ctx.unlock_trade(password=pwd)
        if ret != 0:
            logger.warning(f"unlock_trade failed: {msg}")
    return ctx


@live_bp.route('/status', methods=['GET'])
def live_status():
    enabled = get_live_trading_enabled()
    return jsonify({'enabled': enabled, 'mode': 'live' if enabled else 'paper'})


@live_bp.route('/positions', methods=['GET'])
def live_positions():
    if not get_live_trading_enabled():
        return jsonify({'status': 'error', 'message': '真實交易未啟用'}), 403
    
    try:
        from futu import TrdEnv
        ctx = get_live_ctx()
        ret, data = ctx.position_list_query(trd_env=TrdEnv.REAL)
        ctx.close()
        
        if ret != 0:
            return jsonify({'status': 'error', 'message': str(data)}), 500
        
        positions = []
        if data is not None and not data.empty:
            for _, row in data.iterrows():
                qty = float(row.get('qty', 0) or 0)
                if qty > 0:
                    positions.append({
                        'symbol': row.get('code'),
                        'quantity': int(qty),
                        'average_cost': float(row.get('cost_price', 0) or 0),
                        'current_price': float(row.get('nominal_price', 0) or 0),
                        'market_value': float(row.get('market_val', 0) or 0),
                        'unrealized_pnl': float(row.get('pl_val', 0) or 0),
                        'unrealized_pnl_pct': float(row.get('pl_ratio', 0) or 0) * 100,
                    })
        
        return jsonify({'status': 'ok', 'positions': positions, 'count': len(positions)})
    except Exception as e:
        logger.exception("live_positions error")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@live_bp.route('/orders', methods=['GET'])
def live_orders():
    if not get_live_trading_enabled():
        return jsonify({'status': 'error', 'message': '真實交易未啟用'}), 403
    
    try:
        from futu import TrdEnv
        ctx = get_live_ctx()
        ret, data = ctx.history_order_list_query(trd_env=TrdEnv.REAL)
        ctx.close()
        
        if ret != 0:
            return jsonify({'status': 'error', 'message': str(data)}), 500
        
        orders = []
        if data is not None and not data.empty:
            for _, row in data.iterrows():
                trd_side = str(row.get('trd_side', '')).upper()
                orders.append({
                    'order_id': str(row.get('order_id', '')),
                    'symbol': row.get('code', ''),
                    'order_type': 'BUY' if 'BUY' in trd_side else 'SELL',
                    'quantity': int(float(row.get('qty', 0) or 0)),
                    'price': float(row.get('price', 0) or 0),
                    'filled_quantity': int(float(row.get('dealt_qty', 0) or 0)),
                    'filled_price': float(row.get('dealt_avg_price', 0) or 0),
                    'status': str(row.get('order_status', '')).lower(),
                    'created_at': str(row.get('create_time', '')),
                })
        
        return jsonify({'status': 'ok', 'orders': orders, 'count': len(orders)})
    except Exception as e:
        logger.exception("live_orders error")
        return jsonify({'status': 'error', 'message': str(e)}), 500
