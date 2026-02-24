#!/usr/bin/env python3
"""
Stock Strategies API
提供每支股票每個週期的最佳策略配置
"""

from flask import Blueprint, jsonify, request
import mysql.connector
import json
import os

# 數據庫配置
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'alita'),
    'password': os.getenv('DB_PASSWORD', 'alitamysql'),
    'database': os.getenv('DB_NAME', 'trademaster')
}

stock_strategies_bp = Blueprint('stock_strategies', __name__, url_prefix='/api/v1/stock-strategies')


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


@stock_strategies_bp.route('', methods=['GET'])
def get_all_strategies():
    """獲取所有股票策略配置"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT symbol, timeframe, indicator, params, sharpe, 
                   return_pct, win_rate, trades, batch_id, score, selection_rule, updated_at
            FROM stock_strategies
            ORDER BY symbol, timeframe
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        # 轉換 JSON 欄位
        for row in rows:
            if row.get('params'):
                row['params'] = json.loads(row['params'])
            if row.get('selection_rule'):
                try:
                    row['selection_rule'] = json.loads(row['selection_rule'])
                except Exception:
                    pass
        
        return jsonify({
            'status': 'ok',
            'count': len(rows),
            'strategies': rows
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@stock_strategies_bp.route('/<symbol>', methods=['GET'])
def get_strategy_by_symbol(symbol):
    """根據股票代碼獲取策略配置"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT symbol, timeframe, indicator, params, sharpe,
                   return_pct, win_rate, trades, batch_id, score, selection_rule, updated_at
            FROM stock_strategies
            WHERE symbol = %s
            ORDER BY timeframe
        """, (symbol,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return jsonify({
                'status': 'error',
                'message': f'Strategy for {symbol} not found'
            }), 404
        
        # 轉換 JSON 欄位
        for row in rows:
            if row.get('params'):
                row['params'] = json.loads(row['params'])
            if row.get('selection_rule'):
                try:
                    row['selection_rule'] = json.loads(row['selection_rule'])
                except Exception:
                    pass
        
        return jsonify({
            'status': 'ok',
            'symbol': symbol,
            'strategies': rows
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@stock_strategies_bp.route('/<symbol>/<timeframe>', methods=['GET'])
def get_strategy_by_symbol_tf(symbol, timeframe):
    """根據股票代碼和週期獲取策略配置"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT symbol, timeframe, indicator, params, sharpe,
                   return_pct, win_rate, trades, batch_id, score, selection_rule, updated_at
            FROM stock_strategies
            WHERE symbol = %s AND timeframe = %s
        """, (symbol, timeframe))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({
                'status': 'error',
                'message': f'Strategy for {symbol} {timeframe} not found'
            }), 404
        
        if row.get('params'):
            row['params'] = json.loads(row['params'])
        if row.get('selection_rule'):
            try:
                row['selection_rule'] = json.loads(row['selection_rule'])
            except Exception:
                pass
        
        return jsonify({
            'status': 'ok',
            'strategy': row
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@stock_strategies_bp.route('', methods=['POST'])
def save_strategy():
    """保存股票策略配置"""
    try:
        data = request.get_json()
        
        symbol = data.get('symbol')
        timeframe = data.get('timeframe')
        indicator = data.get('indicator')
        params = data.get('params', {})
        sharpe = data.get('sharpe')
        return_pct = data.get('return_pct')
        win_rate = data.get('win_rate')
        trades = data.get('trades')
        batch_id = data.get('batch_id')
        score = data.get('score')
        selection_rule = data.get('selection_rule')
        
        if not all([symbol, timeframe, indicator]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        params_json = json.dumps(params, ensure_ascii=False)
        selection_rule_json = json.dumps(selection_rule, ensure_ascii=False) if selection_rule is not None else None
        
        # Upsert
        cursor.execute("""
            INSERT INTO stock_strategies (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades, batch_id, score, selection_rule)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                indicator = VALUES(indicator),
                params = VALUES(params),
                sharpe = VALUES(sharpe),
                return_pct = VALUES(return_pct),
                win_rate = VALUES(win_rate),
                trades = VALUES(trades),
                batch_id = VALUES(batch_id),
                score = VALUES(score),
                selection_rule = VALUES(selection_rule)
        """, (symbol, timeframe, indicator, params_json, sharpe, return_pct, win_rate, trades, batch_id, score, selection_rule_json))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'status': 'ok',
            'message': f'Strategy for {symbol} {timeframe} saved'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@stock_strategies_bp.route('/refresh', methods=['POST'])
def refresh_strategies():
    """重新運行回測並更新數據（調用 generate_stock_strategies.py）"""
    try:
        import subprocess
        result = subprocess.run(
            ['python3', '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/backtests/run_full_backtest.py'],
            capture_output=True,
            text=True,
            timeout=36000  # full backtest may take time
        )
        
        if result.returncode == 0:
            return jsonify({
                'status': 'ok',
                'message': 'Strategies refreshed successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': result.stderr
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
