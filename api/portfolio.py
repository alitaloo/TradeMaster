#!/usr/bin/env python3
"""
Portfolio API - 投資組合端點
"""

from flask import Blueprint, jsonify

portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/api/v1/portfolio')


# 模擬投資組合數據
portfolio_data = {
    "total_assets": 156420,
    "today_pnl": 3240,
    "positions_value": 128500,
    "positions_count": 8,
    "cash": 27920,
    "positions": [
        {
            "symbol": "TSM",
            "shares": 100,
            "avg_price": 145.20,
            "current_price": 152.30,
            "market_value": 15230,
            "pnl": 4.9,
            "pnl_amount": 710,
            "allocation": 22
        },
        {
            "symbol": "NVDA",
            "shares": 50,
            "avg_price": 820.50,
            "current_price": 875.20,
            "market_value": 43760,
            "pnl": 6.7,
            "pnl_amount": 2735,
            "allocation": 18
        },
        {
            "symbol": "AMD",
            "shares": 200,
            "avg_price": 138.40,
            "current_price": 142.50,
            "market_value": 28500,
            "pnl": 3.0,
            "pnl_amount": 820,
            "allocation": 15
        },
        {
            "symbol": "AVGO",
            "shares": 30,
            "avg_price": 1180.00,
            "current_price": 1240.00,
            "market_value": 37200,
            "pnl": 5.1,
            "pnl_amount": 1800,
            "allocation": 12
        },
        {
            "symbol": "WDC",
            "shares": 80,
            "avg_price": 92.50,
            "current_price": 98.75,
            "market_value": 7900,
            "pnl": 6.8,
            "pnl_amount": 500,
            "allocation": 10
        }
    ]
}


@portfolio_bp.route('/overview', methods=['GET'])
def get_overview():
    """獲取投資組合概覽"""
    return jsonify({
        "status": "ok",
        "overview": {
            "total_assets": portfolio_data["total_assets"],
            "today_pnl": portfolio_data["today_pnl"],
            "today_pnl_percent": round(portfolio_data["today_pnl"] / portfolio_data["total_assets"] * 100, 2),
            "positions_value": portfolio_data["positions_value"],
            "cash": portfolio_data["cash"],
            "positions_count": portfolio_data["positions_count"]
        }
    })


@portfolio_bp.route('/positions', methods=['GET'])
def get_positions():
    """獲取持倉列表"""
    return jsonify({
        "status": "ok",
        "count": len(portfolio_data["positions"]),
        "positions": portfolio_data["positions"]
    })


@portfolio_bp.route('/positions/<symbol>', methods=['GET'])
def get_position(symbol):
    """獲取特定持倉"""
    position = next(
        (p for p in portfolio_data["positions"] if p["symbol"].upper() == symbol.upper()),
        None
    )
    
    if not position:
        return jsonify({
            "status": "error",
            "message": "Position not found"
        }), 404
    
    return jsonify({
        "status": "ok",
        "position": position
    })


@portfolio_bp.route('/allocation', methods=['GET'])
def get_allocation():
    """獲取資產配置"""
    positions = portfolio_data["positions"]
    
    allocation = {
        "symbols": [p["symbol"] for p in positions],
        "values": [p["market_value"] for p in positions],
        "percentages": [p["allocation"] for p in positions]
    }
    
    return jsonify({
        "status": "ok",
        "allocation": allocation
    })


@portfolio_bp.route('/performance', methods=['GET'])
def get_performance():
    """獲取投資組合表現"""
    positions = portfolio_data["positions"]
    
    total_pnl = sum(p["pnl_amount"] for p in positions)
    avg_pnl = sum(p["pnl"] for p in positions) / len(positions) if positions else 0
    
    return jsonify({
        "status": "ok",
        "performance": {
            "total_pnl": total_pnl,
            "avg_pnl_percent": round(avg_pnl, 2),
            "winning_positions": len([p for p in positions if p["pnl"] > 0]),
            "losing_positions": len([p for p in positions if p["pnl"] < 0])
        }
    })


@portfolio_bp.route('/summary', methods=['GET'])
def get_summary():
    """獲取完整摘要"""
    return jsonify({
        "status": "ok",
        "portfolio": portfolio_data
    })
