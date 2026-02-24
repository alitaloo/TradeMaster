#!/usr/bin/env python3
"""
TradeMaster v2.0 API 服務器
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS
import yaml

logger = logging.getLogger(__name__)

# 添加專案根目錄
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from api import prediction_bp, init_prediction_engine
from api import signals_bp, backtests_bp, strategies_bp, portfolio_bp, stocks_bp, kline_bp, futu_bp
from api.signals_bp import signals_bp as new_signals_bp
from api.positions_bp import positions_bp
from api.orders_bp import orders_bp
from api.news_bp import news_bp
from api.market_bp import market_bp
from api.config_bp import config_bp
from api.stock_strategies_bp import stock_strategies_bp
from api.paper_bp import paper_bp
from modules.prediction import PredictionEngine
from data import DataEngine


def load_config(config_path: str = None) -> dict:
    """載入配置"""
    if config_path is None:
        config_path = PROJECT_ROOT / "config" / "modules.yaml"
    
    config_path = Path(config_path)
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            return {}
    else:
        logger.info(f"Config file not found at {config_path}, using defaults")
        return {}


def create_app(config: dict = None) -> Flask:
    """創建 Flask 應用"""
    app = Flask(__name__)
    
    # CORS 支援 - 允許所有來源（開發環境）
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    # 配置
    app.config['JSON_SORT_KEYS'] = False
    
    # 初始化數據引擎
    data_engine = DataEngine()
    
    # 初始化預測引擎
    prediction_config = (config or {}).get('prediction', {})
    weights = prediction_config.get('weights', {})
    
    engine = PredictionEngine(data_engine=data_engine, weights=weights)
    init_prediction_engine(engine)
    
    # 註冊路由
    app.register_blueprint(prediction_bp)
    app.register_blueprint(new_signals_bp)
    app.register_blueprint(positions_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(backtests_bp)
    app.register_blueprint(strategies_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(stocks_bp)
    app.register_blueprint(kline_bp)
    app.register_blueprint(futu_bp)
    app.register_blueprint(news_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(stock_strategies_bp)
    app.register_blueprint(paper_bp)
    
    # 健康檢查
    @app.route('/health')
    def health():
        return jsonify({
            "status": "ok",
            "service": "TradeMaster v2.0 API",
            "version": "2.0.0"
        })
    
    # API 信息
    @app.route('/api/v1')
    def api_info():
        return jsonify({
            "service": "TradeMaster v2.0 API",
            "version": "2.0.0",
            "endpoints": {
                # 預測
                "POST /api/v1/prediction": "創建單一預測",
                "POST /api/v1/prediction/command": "從指令創建預測",
                "POST /api/v1/prediction/batch": "批量創建預測",
                "GET /api/v1/prediction/statistics": "獲取引擎統計",
                # 信號
                "GET /api/v1/signals": "獲取所有信號",
                "GET /api/v1/signals/latest": "獲取最新信號",
                "GET /api/v1/signals/<symbol>": "獲取特定股票信號",
                "GET /api/v1/signals/summary": "獲取信號摘要",
                # 回測
                "GET /api/v1/backtests": "獲取所有回測結果",
                "GET /api/v1/backtests/strategy/<name>": "獲取策略回測",
                "GET /api/v1/backtests/symbol/<symbol>": "獲取股票回測",
                "GET /api/v1/backtests/top": "獲取表現最好的回測",
                "GET /api/v1/backtests/statistics": "獲取回測統計",
                # 策略
                "GET /api/v1/strategies": "獲取所有策略",
                "POST /api/v1/strategies": "創建新策略",
                "GET /api/v1/strategies/<id>": "獲取策略詳情",
                "PUT /api/v1/strategies/<id>": "更新策略",
                "DELETE /api/v1/strategies/<id>": "刪除策略（自定義）",
                "PUT /api/v1/strategies/<id>/toggle": "切換策略狀態",
                "GET /api/v1/strategies/enabled": "獲取已啟用策略",
                "GET /api/v1/strategies/top": "獲取表現最好的策略",
                # 投資組合
                "GET /api/v1/portfolio/overview": "獲取組合概覽",
                "GET /api/v1/portfolio/positions": "獲取持倉列表",
                "GET /api/v1/portfolio/positions/<symbol>": "獲取特定持倉",
                "GET /api/v1/portfolio/allocation": "獲取資產配置",
                "GET /api/v1/portfolio/performance": "獲取表現統計",
                "GET /api/v1/portfolio/summary": "獲取完整摘要"
            }
        })
    
    logger.info("TradeMaster v2.0 API 服務初始化完成")
    return app


def run_server(host: str = "0.0.0.0", port: int = 8080, debug: bool = False):
    """運行服務器"""
    config = load_config()
    app = create_app(config)
    
    logger.info(f"啟動服務器: {host}:{port}")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TradeMaster v2.0 API Server")
    parser.add_argument("--host", default="0.0.0.0", help="綁定地址")
    parser.add_argument("--port", type=int, default=8080, help="端口")
    parser.add_argument("--debug", action="store_true", help="調試模式")
    
    args = parser.parse_args()
    
    run_server(args.host, args.port, args.debug)
