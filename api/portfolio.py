#!/usr/bin/env python3
"""
Portfolio API - 投資組合端點
從數據庫讀取真實持倉數據
"""

from flask import Blueprint, jsonify
import pymysql
from pymysql.cursors import DictCursor

portfolio_bp = Blueprint('portfolio', __name__, url_prefix='/api/v1/portfolio')

# 數據庫配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'alita',
    'password': 'alitamysql',
    'database': 'trademaster'
}

# 默認總資金
DEFAULT_CAPITAL = 100000


def get_db_connection():
    """獲取數據庫連接"""
    config = DB_CONFIG.copy()
    config['cursorclass'] = DictCursor
    return pymysql.connect(**config)


def get_portfolio_data():
    """從數據庫獲取真實持倉數據"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 獲取所有持倉
    cursor.execute("""
        SELECT symbol, quantity, avg_price, current_price, pnl, pnl_pct, status
        FROM positions 
        WHERE quantity > 0
        ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    
    # 獲取總資金配置
    try:
        cursor.execute("SELECT value FROM config WHERE name = 'total_capital'")
        config_row = cursor.fetchone()
        total_capital = float(config_row['value']) if config_row else DEFAULT_CAPITAL
    except:
        total_capital = DEFAULT_CAPITAL
    
    conn.close()
    
    # 計算持倉數據
    positions = []
    total_positions_value = 0
    total_pnl_amount = 0
    
    for row in rows:
        quantity = float(row['quantity'] or 0)
        avg_price = float(row['avg_price'] or 0)
        current_price = float(row['current_price'] or avg_price)
        
        # 計算市值和損益
        market_value = quantity * current_price
        cost_value = quantity * avg_price
        pnl_amount = market_value - cost_value
        pnl_pct = (pnl_amount / cost_value * 100) if cost_value > 0 else 0
        
        total_positions_value += market_value
        total_pnl_amount += pnl_amount
        
        # 清理 symbol (去掉 US. 前綴)
        symbol = row['symbol']
        if symbol and symbol.startswith('US.'):
            symbol = symbol[3:]
        
        positions.append({
            'symbol': symbol,
            'shares': int(quantity),
            'avg_price': round(avg_price, 2),
            'current_price': round(current_price, 2),
            'market_value': round(market_value, 2),
            'pnl': round(pnl_pct, 2),  # 百分比
            'pnl_amount': round(pnl_amount, 2),  # 金額
            'allocation': 0  # 稍後計算
        })
    
    # 計算各持倉的配置占比
    if total_positions_value > 0:
        for pos in positions:
            pos['allocation'] = round(pos['market_value'] / total_positions_value * 100, 1)
    
    # 計算現金餘額 (總資金 - 持倉市值)
    cash = total_capital - total_positions_value
    
    # 今日損益 (使用當前浮動損益作為近似值)
    today_pnl = total_pnl_amount
    
    return {
        "total_assets": round(total_capital, 2),
        "today_pnl": round(today_pnl, 2),
        "positions_value": round(total_positions_value, 2),
        "positions_count": len(positions),
        "cash": round(cash, 2),
        "positions": positions
    }


@portfolio_bp.route('/overview', methods=['GET'])
def get_overview():
    """獲取投資組合概覽"""
    try:
        data = get_portfolio_data()
        
        pnl_percent = (data["today_pnl"] / data["total_assets"] * 100) if data["total_assets"] > 0 else 0
        
        return jsonify({
            "status": "ok",
            "overview": {
                "total_assets": data["total_assets"],
                "today_pnl": data["today_pnl"],
                "today_pnl_percent": round(pnl_percent, 2),
                "positions_value": data["positions_value"],
                "cash": data["cash"],
                "positions_count": data["positions_count"]
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@portfolio_bp.route('/positions', methods=['GET'])
def get_positions():
    """獲取持倉列表"""
    try:
        data = get_portfolio_data()
        
        return jsonify({
            "status": "ok",
            "count": len(data["positions"]),
            "positions": data["positions"]
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@portfolio_bp.route('/positions/<symbol>', methods=['GET'])
def get_position(symbol):
    """獲取特定持倉"""
    try:
        data = get_portfolio_data()
        
        position = next(
            (p for p in data["positions"] if p["symbol"].upper() == symbol.upper()),
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
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@portfolio_bp.route('/allocation', methods=['GET'])
def get_allocation():
    """獲取資產配置"""
    try:
        data = get_portfolio_data()
        positions = data["positions"]
        
        allocation = {
            "symbols": [p["symbol"] for p in positions],
            "values": [p["market_value"] for p in positions],
            "percentages": [p["allocation"] for p in positions]
        }
        
        return jsonify({
            "status": "ok",
            "allocation": allocation
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@portfolio_bp.route('/performance', methods=['GET'])
def get_performance():
    """獲取投資組合表現"""
    try:
        data = get_portfolio_data()
        positions = data["positions"]
        
        total_pnl = sum(p["pnl_amount"] for p in positions)
        avg_pnl = sum(p["pnl"] for p in positions) / len(positions) if positions else 0
        
        return jsonify({
            "status": "ok",
            "performance": {
                "total_pnl": round(total_pnl, 2),
                "avg_pnl_percent": round(avg_pnl, 2),
                "winning_positions": len([p for p in positions if p["pnl"] > 0]),
                "losing_positions": len([p for p in positions if p["pnl"] < 0])
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@portfolio_bp.route('/summary', methods=['GET'])
def get_summary():
    """獲取完整摘要"""
    try:
        data = get_portfolio_data()
        
        return jsonify({
            "status": "ok",
            "portfolio": data
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
