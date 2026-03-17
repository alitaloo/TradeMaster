#!/usr/bin/env python3
"""
TradeMaster v2.0 API 服務器
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
import yaml
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# 添加專案根目錄
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from api import prediction_bp, init_prediction_engine
from api import backtests_bp, strategies_bp, portfolio_bp, stocks_bp, kline_bp, futu_bp
# Stage 1: 只使用 DB-based signals blueprint，消除 file-based 路由歧義
from api.signals_bp import signals_bp as new_signals_bp
from api.positions_bp import positions_bp
from api.orders_bp import orders_bp
from api.news_bp import news_bp
from api.market_bp import market_bp
from api.config_bp import config_bp
from api.stock_strategies_bp import stock_strategies_bp
from api.paper_bp import paper_bp
from api.system_status_bp import system_status_bp
from api.manual_actions_bp import manual_actions_bp
from modules.prediction import PredictionEngine
from data import DataEngine


# 全局新聞錯誤計數器 (進程內記憶體，重啟歸零)
_news_error_counter = {'count_24h': 0, 'last_error': None, 'last_error_ts': None}


def news_error_increment(error_msg: str = ""):
    """供 news_bp 或 cron 腳本呼叫，遞增錯誤計數"""
    from datetime import datetime, timezone, timedelta
    _news_error_counter['count_24h'] = _news_error_counter.get('count_24h', 0) + 1
    _news_error_counter['last_error'] = str(error_msg)[:200]
    _news_error_counter['last_error_ts'] = datetime.now(
        timezone(timedelta(hours=8))).isoformat()


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
    app.register_blueprint(system_status_bp)
    app.register_blueprint(manual_actions_bp)
    
    # 健康檢查
    @app.route('/health')
    def health():
        result = {
            "status": "ok",
            "service": "TradeMaster v2.0 API",
            "version": "2.0.0"
        }

        # 如 ?detail=news 或 ?detail=all，附加新聞同步狀態
        detail = request.args.get('detail', '')
        if detail in ('news', 'all'):
            try:
                from config.database import get_db_connection
                _tz = timezone(timedelta(hours=8))
                with get_db_connection() as conn:
                    cur = conn.cursor(dictionary=True)

                    # 最後同步時間
                    cur.execute("SELECT MAX(created_at) AS last_synced FROM news")
                    row = cur.fetchone()
                    last_synced = row['last_synced'] if row else None
                    if last_synced and last_synced.tzinfo is None:
                        last_synced = last_synced.replace(tzinfo=_tz)

                    # 24h 計數
                    cur.execute("SELECT COUNT(*) AS cnt FROM news WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)")
                    count_24h = cur.fetchone()['cnt']

                    # 總計
                    cur.execute("SELECT COUNT(*) AS cnt FROM news")
                    total = cur.fetchone()['cnt']

                news_status = {
                    "news_last_synced": last_synced.isoformat() if last_synced else None,
                    "news_count_24h": count_24h,
                    "news_count_total": total,
                    "news_sync_errors_24h": _news_error_counter.get('count_24h', 0),
                    "news_sync_status": "ok" if count_24h > 0 else ("stale" if last_synced else "never_synced"),
                }
                result["news"] = news_status
            except Exception as e:
                result["news"] = {"news_sync_status": "error", "detail": str(e)}

        return jsonify(result)

    # 專用新聞同步狀態 endpoint
    @app.route('/api/v1/news/sync-status')
    def news_sync_status():
        """新聞同步狀態 (freshness / observability)"""
        try:
            from config.database import get_db_connection
            _tz = timezone(timedelta(hours=8))
            with get_db_connection() as conn:
                cur = conn.cursor(dictionary=True)

                cur.execute("SELECT MAX(created_at) AS last_synced FROM news")
                row = cur.fetchone()
                last_synced = row['last_synced'] if row else None
                if last_synced and last_synced.tzinfo is None:
                    last_synced = last_synced.replace(tzinfo=_tz)

                cur.execute("SELECT COUNT(*) AS cnt FROM news WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)")
                count_24h = cur.fetchone()['cnt']

                cur.execute("SELECT COUNT(*) AS cnt FROM news")
                total = cur.fetchone()['cnt']

                # 每來源統計
                cur.execute("""
                    SELECT source, COUNT(*) AS cnt, MAX(created_at) AS latest
                    FROM news WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
                    GROUP BY source ORDER BY cnt DESC LIMIT 10
                """)
                by_source = []
                for r in cur.fetchall():
                    lt = r['latest']
                    if lt and lt.tzinfo is None:
                        lt = lt.replace(tzinfo=_tz)
                    by_source.append({
                        "source": r['source'],
                        "count_24h": r['cnt'],
                        "latest": lt.isoformat() if lt else None
                    })

            # 判定 sync_status
            if last_synced is None:
                sync_status = "never_synced"
            elif count_24h > 0:
                sync_status = "ok"
            else:
                sync_status = "stale"

            return jsonify({
                "status": "ok",
                "news_last_synced": last_synced.isoformat() if last_synced else None,
                "news_count_24h": count_24h,
                "news_count_total": total,
                "news_sync_errors_24h": _news_error_counter.get('count_24h', 0),
                "news_sync_status": sync_status,
                "by_source": by_source
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    
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
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TradeMaster v2.0 API Server")
    parser.add_argument("--host", default="0.0.0.0", help="綁定地址")
    parser.add_argument("--port", type=int, default=8080, help="端口")
    parser.add_argument("--debug", action="store_true", help="調試模式")
    
    args = parser.parse_args()
    
    run_server(args.host, args.port, args.debug)
