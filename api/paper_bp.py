#!/usr/bin/env python3
"""
Paper Trading API - 模擬交易 API
"""
from flask import Blueprint, jsonify, request
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_service import (
    get_status,
    get_paper_positions,
    get_paper_total_assets,
    submit_paper_order,
    poll_paper_orders,
    is_enabled
)
from paper_reports import (
    push_paper_daily_summary,
    generate_paper_report,
    track_signal_hit_rate,
    compare_backtest_simulation
)
from models import SystemConfig, PaperPosition

paper_bp = Blueprint('paper', __name__, url_prefix='/api/v1/paper')


@paper_bp.route('/status', methods=['GET'])
def get_paper_status():
    """取得模擬交易狀態"""
    return jsonify(get_status())


@paper_bp.route('/enable', methods=['POST'])
def enable_paper_trading():
    """啟用模擬交易"""
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    SystemConfig.set('paper_trading_enabled', 'true' if enabled else 'false')
    return jsonify({'success': True, 'enabled': enabled})


@paper_bp.route('/positions', methods=['GET'])
def get_positions():
    """取得模擬持倉（直接從DB讀取，由watcher定時同步價格）"""
    positions = PaperPosition.find_all()
    
    return jsonify({
        'success': True,
        'positions': [p.to_dict() for p in positions],
        'count': len(positions)
    })


@paper_bp.route('/positions/<symbol>', methods=['GET'])
def get_position(symbol):
    """取得單一持倉"""
    from paper_trading_portfolio import get_paper_position
    pos = get_paper_position(symbol)
    if pos:
        return jsonify({'success': True, 'position': pos})
    return jsonify({'success': False, 'error': 'Position not found'}), 404


@paper_bp.route('/summary', methods=['GET'])
def get_summary():
    """取得模擬交易總覽"""
    assets = get_paper_total_assets()
    return jsonify({
        'success': True,
        'summary': assets
    })


@paper_bp.route('/orders', methods=['GET'])
def get_orders():
    """取得模擬訂單列表"""
    from models import PaperOrder
    limit = request.args.get('limit', 100, type=int)
    orders = PaperOrder.find_all(limit=limit)
    return jsonify({
        'success': True,
        'orders': [o.to_dict() for o in orders],
        'count': len(orders)
    })


@paper_bp.route('/orders', methods=['POST'])
def create_order():
    """創建模擬訂單"""
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'No data'}), 400
    
    result = submit_paper_order(
        symbol=data.get('symbol'),
        order_type=data.get('order_type'),
        quantity=data.get('quantity'),
        price=data.get('price')
    )
    
    if result.get('success'):
        return jsonify(result)
    return jsonify(result), 400


@paper_bp.route('/orders/<int:order_id>', methods=['DELETE'])
def cancel_order(order_id):
    """取消模擬訂單"""
    from paper_trading import cancel_paper_order
    success = cancel_paper_order(order_id)
    return jsonify({'success': success})


@paper_bp.route('/poll', methods=['POST'])
def poll_orders():
    """輪詢訂單狀態"""
    results = poll_paper_orders()
    return jsonify({
        'success': True,
        'results': results
    })


@paper_bp.route('/report', methods=['GET'])
def get_report():
    """取得模擬交易報告"""
    result = generate_paper_report()
    return jsonify(result)


@paper_bp.route('/daily-summary', methods=['GET'])
def get_daily_summary():
    """取得每日結算"""
    from models import PaperDailySummary
    limit = request.args.get('limit', 30, type=int)
    summaries = PaperDailySummary.find_latest(limit=limit)
    return jsonify({
        'success': True,
        'summaries': [s.to_dict() for s in summaries]
    })


@paper_bp.route('/signal-stats', methods=['GET'])
def get_signal_stats():
    """取得信號命中率"""
    result = track_signal_hit_rate()
    return jsonify(result)


@paper_bp.route('/performance', methods=['GET'])
def get_performance():
    """取得回測對比"""
    result = compare_backtest_simulation()
    return jsonify(result)


@paper_bp.route('/push', methods=['POST'])
def push_summary():
    """手動推送到 Successor Bot"""
    result = push_paper_daily_summary()
    return jsonify(result)


# 註冊到 Flask app
def register_paper_routes(app):
    """註冊路由"""
    app.register_blueprint(paper_bp)
    return app
