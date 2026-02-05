#!/usr/bin/env python3
"""
TradeMaster v2.0 API 服務器
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify
import yaml

logger = logging.getLogger(__name__)

# 添加專案根目錄
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from api import prediction_bp, init_prediction_engine
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
                "POST /api/v1/prediction": "創建單一預測",
                "POST /api/v1/prediction/command": "從指令創建預測",
                "POST /api/v1/prediction/batch": "批量創建預測",
                "GET /api/v1/prediction/statistics": "獲取引擎統計"
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
