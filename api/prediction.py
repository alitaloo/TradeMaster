#!/usr/bin/env python3
"""
預測 API - REST API 接口
"""

from flask import Blueprint, request, jsonify
from .engine import PredictionEngine

# 創建 Blueprint
prediction_bp = Blueprint('prediction', __name__, url_prefix='/api/v1')

# 全局引擎實例 (可由主程序注入)
engine: PredictionEngine = None


def init_engine(data_engine=None):
    """初始化預測引擎"""
    global engine
    engine = PredictionEngine(data_engine)


@prediction_bp.route('/prediction', methods=['POST'])
def create_prediction():
    """
    創建價格預測
    
    Request Body:
    {
        "symbol": "TSLA",
        "direction": "UP",  // UP/DOWN/VOLATILITY
        "threshold": 10,     // 百分比
        "period_days": 5
    }
    
    Response:
    {
        "success": true,
        "data": {
            "symbol": "TSLA",
            "direction": "UP",
            "probability": 0.68,
            "confidence": "HIGH",
            "factors": {...}
        }
    }
    """
    global engine
    
    if engine is None:
        return jsonify({
            "success": False,
            "error": "預測引擎未初始化"
        }), 500
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "error": "請求體為空"
            }), 400
        
        # 提取參數
        symbol = data.get('symbol', '').upper().strip()
        direction = data.get('direction', 'UP')
        threshold = float(data.get('threshold', 10))
        period_days = int(data.get('period_days', 5))
        
        # 驗證參數
        if not symbol:
            return jsonify({
                "success": False,
                "error": "缺少 symbol 參數"
            }), 400
        
        valid_directions = ['UP', 'DOWN', 'VOLATILITY']
        if direction not in valid_directions:
            return jsonify({
                "success": False,
                "error": f"無效方向，支援: {valid_directions}"
            }), 400
        
        # 執行預測
        result = engine.predict(symbol, direction, threshold, period_days)
        
        return jsonify(result)
        
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": f"參數錯誤: {str(e)}"
        }), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"服務器錯誤: {str(e)}"
        }), 500


@prediction_bp.route('/prediction/command', methods=['POST'])
def prediction_from_command():
    """
    從指令格式創建預測
    
    Request Body:
    {
        "command": "TSLA/📈/10/5"
    }
    """
    global engine
    
    if engine is None:
        return jsonify({
            "success": False,
            "error": "預測引擎未初始化"
        }), 500
    
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        
        if not command:
            return jsonify({
                "success": False,
                "error": "缺少 command 參數"
            }), 400
        
        result = engine.predict_from_command(command)
        
        if result.get('success'):
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"服務器錯誤: {str(e)}"
        }), 500


@prediction_bp.route('/prediction/batch', methods=['POST'])
def batch_prediction():
    """
    批量預測
    
    Request Body:
    {
        "symbols": ["TSLA", "AAPL", "MSFT"],
        "direction": "UP",
        "threshold": 10,
        "period_days": 5
    }
    """
    global engine
    
    if engine is None:
        return jsonify({
            "success": False,
            "error": "預測引擎未初始化"
        }), 500
    
    try:
        data = request.get_json()
        
        symbols = data.get('symbols', [])
        direction = data.get('direction', 'UP')
        threshold = float(data.get('threshold', 10))
        period_days = int(data.get('period_days', 5))
        
        if not symbols:
            return jsonify({
                "success": False,
                "error": "缺少 symbols 參數"
            }), 400
        
        results = engine.batch_predict(symbols, direction, threshold, period_days)
        
        return jsonify({
            "success": True,
            "data": {
                "predictions": results,
                "count": len(results)
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"服務器錯誤: {str(e)}"
        }), 500


@prediction_bp.route('/prediction/statistics', methods=['GET'])
def get_statistics():
    """獲取引擎統計"""
    global engine
    
    if engine is None:
        return jsonify({
            "success": False,
            "error": "預測引擎未初始化"
        }), 500
    
    try:
        return jsonify({
            "success": True,
            "data": engine.get_statistics()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"服務器錯誤: {str(e)}"
        }), 500
