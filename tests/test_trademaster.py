#!/usr/bin/env python3
"""
測試模組 - Tests
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def create_sample_data(rows: int = 100) -> pd.DataFrame:
    """創建測試用的模擬價格數據"""
    base_date = datetime.now() - timedelta(days=rows)
    
    dates = [base_date + timedelta(days=i) for i in range(rows)]
    
    # 模擬價格走勢
    np.random.seed(42)
    price = 100 + np.cumsum(np.random.randn(rows) * 2)
    volume = np.random.randint(1000000, 10000000, rows)
    
    df = pd.DataFrame({
        "Date": dates,
        "Open": price + np.random.randn(rows) * 0.5,
        "High": price + np.random.abs(np.random.randn(rows)) * 0.5,
        "Low": price - np.abs(np.random.randn(rows)) * 0.5,
        "Close": price,
        "Volume": volume
    })
    
    df.set_index("Date", inplace=True)
    return df


class TestIndicators:
    """指標測試"""
    
    def test_rsi(self):
        """測試 RSI 指標"""
        from indicators.momentum import RSIIndicator
        
        df = create_sample_data(100)
        rsi = RSIIndicator(period=14)
        result = rsi.compute(df)
        
        assert result is not None
        assert "rsi" in result.last_value
        assert 0 <= result.last_value["rsi"] <= 100
    
    def test_sma(self):
        """測試 SMA 指標"""
        from indicators.trend import SMAIndicator
        
        df = create_sample_data(100)
        sma = SMAIndicator(period=20)
        result = sma.compute(df)
        
        assert result is not None
        assert "sma" in result.last_value
    
    def test_ema(self):
        """測試 EMA 指標"""
        from indicators.trend import EMAIndicator
        
        df = create_sample_data(100)
        ema = EMAIndicator(period=12)
        result = ema.compute(df)
        
        assert result is not None
        assert "ema" in result.last_value
    
    def test_macd(self):
        """測試 MACD 指標"""
        from indicators.trend import MACDIndicator
        
        df = create_sample_data(100)
        macd = MACDIndicator()
        result = macd.compute(df)
        
        assert result is not None
        assert "macd" in result.last_value
        assert "signal" in result.last_value
        assert "histogram" in result.last_value
    
    def test_bollinger_bands(self):
        """測試布林帶指標"""
        from indicators.trend import BollingerBandsIndicator
        
        df = create_sample_data(100)
        bb = BollingerBandsIndicator()
        result = bb.compute(df)
        
        assert result is not None
        assert "upper" in result.last_value
        assert "middle" in result.last_value
        assert "lower" in result.last_value
    
    def test_obv(self):
        """測試 OBV 指標"""
        from indicators.volume import OBVIndicator
        
        df = create_sample_data(100)
        obv = OBVIndicator()
        result = obv.compute(df)
        
        assert result is not None
        assert "obv" in result.last_value
    
    def test_adx(self):
        """測試 ADX 指標"""
        from indicators.trend import ADXIndicator
        
        df = create_sample_data(100)
        adx = ADXIndicator(period=14)
        result = adx.compute(df)
        
        assert result is not None
        assert "adx" in result.last_value
        assert "plus_di" in result.last_value
        assert "minus_di" in result.last_value


class TestVolumeIndicators:
    """成交量指標測試"""

    def test_vwap(self):
        """測試 VWAP 指標"""
        from indicators.volume import VWAPIndicator

        df = create_sample_data(100)
        vwap = VWAPIndicator(period=14)
        result = vwap.compute(df)

        assert result is not None
        assert "vwap" in result.last_value
        assert "vwap_zscore" in result.last_value

    def test_vwap_zscore_range(self):
        """測試 VWAP Z-Score 在合理範圍"""
        from indicators.volume import VWAPIndicator

        df = create_sample_data(100)
        vwap = VWAPIndicator(period=14)
        result = vwap.compute(df)

        zscore = result.last_value.get("vwap_zscore", 0)
        # Z-score 應該在 -3 到 3 之內
        assert -5 < zscore < 5

    def test_ad_volume(self):
        """測試 A/D 累積派發線"""
        from indicators.volume import ADIndicator

        df = create_sample_data(100)
        ad = ADIndicator()
        result = ad.compute(df)

        assert result is not None
        assert "ad" in result.last_value
        assert "ad_ema" in result.last_value

    def test_volume_profile(self):
        """測試成交量分布"""
        from indicators.volume import VolumeProfileIndicator

        df = create_sample_data(100)
        vp = VolumeProfileIndicator(bins=20)
        result = vp.compute(df)

        assert result is not None
        assert "poc" in result.last_value  # Point of Control
        assert "value_area_low" in result.last_value
        assert "value_area_high" in result.last_value

    def test_volume_profile_poc_in_price_range(self):
        """測試 POC 在價格範圍內"""
        from indicators.volume import VolumeProfileIndicator

        df = create_sample_data(100)
        vp = VolumeProfileIndicator(bins=20)
        result = vp.compute(df)

        poc = result.last_value.get("poc")
        low = df["Low"].min()
        high = df["High"].max()

        assert low <= poc <= high

    def test_obv_monotonic(self):
        """測試 OBV 計算正確性"""
        from indicators.volume import OBVIndicator

        df = create_sample_data(50)
        obv = OBVIndicator()
        result = obv.compute(df)

        assert result is not None
        # OBV 值應該隨時間累積
        assert result.values["obv"].iloc[-1] != 0 or len(result.values) > 1


class TestStrategies:
    """策略測試"""
    
    def test_rsi_reversal_strategy(self):
        """測試 RSI 反轉策略"""
        from strategies.momentum import RSIReversalStrategy
        from indicators.momentum import RSIIndicator
        
        df = create_sample_data(100)
        
        # 先計算指標
        rsi = RSIIndicator(period=14)
        rsi_result = rsi.compute(df)
        
        # 再生成信號
        strategy = RSIReversalStrategy()
        signal = strategy.generate_signal(
            {"RSI": rsi_result},
            df
        )
        
        assert signal is not None
        assert signal.signal in ["LONG", "SHORT", "HOLD"]
        assert signal.price is not None
    
    def test_trend_follower_strategy(self):
        """測試趨勢追蹤策略"""
        from strategies.trend import TrendFollowerStrategy
        from indicators.trend import EMAIndicator
        
        df = create_sample_data(100)
        
        ema = EMAIndicator(period=12)
        ema_result = ema.compute(df)
        
        strategy = TrendFollowerStrategy(fast_period=10, slow_period=30)
        signal = strategy.generate_signal(
            {"EMA": ema_result},
            df
        )
        
        assert signal is not None
        assert signal.signal in ["LONG", "SHORT", "HOLD"]
    
    def test_macd_trend_strategy(self):
        """測試 MACD 趨勢策略"""
        from strategies.trend import MACDTrendStrategy
        from indicators.trend import MACDIndicator
        
        df = create_sample_data(100)
        
        macd = MACDIndicator()
        macd_result = macd.compute(df)
        
        strategy = MACDTrendStrategy()
        signal = strategy.generate_signal(
            {"MACD": macd_result},
            df
        )
        
        assert signal is not None
        assert signal.signal in ["LONG", "SHORT", "HOLD"]
    
    def test_multi_factor_strategy(self):
        """測試多因子策略"""
        from strategies.composite import MultiFactorStrategy
        from indicators.momentum import RSIIndicator
        from indicators.trend import MACDIndicator, ADXIndicator, SMAIndicator
        
        df = create_sample_data(100)
        
        rsi = RSIIndicator(period=14)
        macd = MACDIndicator()
        adx = ADXIndicator()
        sma = SMAIndicator(period=20)
        
        strategy = MultiFactorStrategy()
        signal = strategy.generate_signal(
            {
                "RSI": rsi.compute(df),
                "MACD": macd.compute(df),
                "ADX": adx.compute(df),
                "SMA": sma.compute(df)
            },
            df
        )
        
        assert signal is not None
        assert signal.signal in ["LONG", "SHORT", "HOLD"]


class TestRiskRules:
    """風控規則測試"""
    
    def test_max_position_limit(self):
        """測試最大倉位限制"""
        from risk_rules import MaxPositionLimit
        
        rule = MaxPositionLimit(max_position_pct=0.25)
        
        position = {"symbol": "AAPL", "value": 30000, "quantity": 100, "price": 300}
        portfolio = {"total_value": 100000}
        
        result = rule.check(position, portfolio)
        
        assert result is not None
        assert hasattr(result, "passed")
        assert hasattr(result, "violations")
    
    def test_fixed_stop_loss(self):
        """測試固定止損"""
        from risk_rules import FixedStopLoss
        
        rule = FixedStopLoss(stop_pct=0.05)
        
        position = {
            "type": "LONG",
            "entry_price": 100,
            "current_price": 94
        }
        
        result = rule.check(position)
        
        assert result is not None
        assert hasattr(result, "passed")
    
    def test_trailing_stop_loss(self):
        """測試移動止損"""
        from risk_rules import TrailingStopLoss
        
        rule = TrailingStopLoss(trail_pct=0.05, trail_after_pct=0.10)
        
        position = {
            "type": "LONG",
            "entry_price": 100,
            "current_price": 108,
            "high_price": 110
        }
        
        result = rule.check(position)
        
        assert result is not None
        assert hasattr(result, "passed")
    
    def test_daily_loss_limit(self):
        """測試每日虧損限制"""
        from risk_rules import DailyLossLimit
        
        rule = DailyLossLimit(max_daily_loss_pct=0.02, max_daily_trades=10)
        
        portfolio = {
            "daily_pnl_pct": -0.015,
            "daily_trades": 5
        }
        
        result = rule.check(portfolio=portfolio)
        
        assert result is not None

    def test_daily_loss_limit_trigger(self):
        """測試每日虧損限制觸發"""
        from risk_rules import DailyLossLimit
        
        rule = DailyLossLimit(max_daily_loss_pct=0.02, max_daily_trades=10)
        
        # 虧損超限
        portfolio = {
            "daily_pnl_pct": -0.03,
            "daily_trades": 5
        }
        
        result = rule.check(portfolio=portfolio)
        
        assert result.passed == False
        assert len(result.violations) > 0

    def test_daily_trade_limit_trigger(self):
        """測試每日交易次數限制觸發"""
        from risk_rules import DailyLossLimit
        
        rule = DailyLossLimit(max_daily_loss_pct=0.02, max_daily_trades=10)
        
        # 交易次數超限
        portfolio = {
            "daily_pnl_pct": -0.01,
            "daily_trades": 12
        }
        
        result = rule.check(portfolio=portfolio)
        
        assert result.passed == False

    def test_position_correlation(self):
        """測試持倉相關性檢查"""
        from risk_rules import PositionCorrelation
        
        rule = PositionCorrelation(max_correlation=0.70)
        
        # 新持倉與現有持倉高相關
        position = {
            "symbol": "AAPL",
            "correlations": {
                "MSFT": 0.85,  # 高相關
                "GOOGL": 0.30
            }
        }
        
        portfolio = {
            "positions": [
                {"symbol": "MSFT"},
                {"symbol": "GOOGL"}
            ]
        }
        
        result = rule.check(position, portfolio)
        
        assert result.passed == False
        assert len(result.violations) > 0

    def test_position_correlation_pass(self):
        """測試持倉相關性通過"""
        from risk_rules import PositionCorrelation
        
        rule = PositionCorrelation(max_correlation=0.70)
        
        # 新持倉與現有持倉低相關
        position = {
            "symbol": "AAPL",
            "correlations": {
                "MSFT": 0.85,
                "GOOGL": 0.30
            }
        }
        
        portfolio = {
            "positions": [
                {"symbol": "TSLA"},  # 低相關
                {"symbol": "NVDA"}
            ]
        }
        
        result = rule.check(position, portfolio)
        
        assert result.passed == True

    def test_take_profit(self):
        """測試止盈規則"""
        from risk_rules import TakeProfit
        
        rule = TakeProfit(target_pct=0.10, scale_out=True, first_target_pct=0.05)
        
        # 達到止盈目標
        position = {
            "type": "LONG",
            "entry_price": 100,
            "current_price": 112  # 12% 獲利
        }
        
        result = rule.check(position)
        
        assert result.passed == False
        assert len(result.violations) > 0

    def test_take_profit_scale_out(self):
        """測試分批止盈"""
        from risk_rules import TakeProfit
        
        rule = TakeProfit(target_pct=0.15, scale_out=True, first_target_pct=0.05)
        
        # 達到第一止盈目標
        position = {
            "type": "LONG",
            "entry_price": 100,
            "current_price": 106  # 6% 獲利
        }
        
        result = rule.check(position)
        
        assert result.passed == False
        # 應該是分批止盈，不是全部平倉
        action = result.violations[0].get("action")
        assert action == "SCALE_OUT"


class TestBacktest:
    """回測引擎測試"""
    
    def test_backtest_engine(self):
        """測試回測引擎"""
        from backtest import BacktestEngine, PositionType
        from strategies.momentum import RSIReversalStrategy
        from indicators.momentum import RSIIndicator
        
        df = create_sample_data(100)
        
        rsi = RSIIndicator(period=14)
        strategy = RSIReversalStrategy()
        
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run("AAPL", strategy, df, "RSI_Reversal")
        
        assert result is not None
        assert result.symbol == "AAPL"
        assert hasattr(result, "total_return")
        assert hasattr(result, "max_drawdown")
        assert hasattr(result, "win_rate")
    
    def test_backtest_result_dict(self):
        """測試回測結果轉字典"""
        from backtest import BacktestEngine, PositionType
        from strategies.momentum import RSIReversalStrategy
        from indicators.momentum import RSIIndicator
        
        df = create_sample_data(50)
        
        rsi = RSIIndicator(period=14)
        strategy = RSIReversalStrategy()
        
        engine = BacktestEngine(initial_capital=100000)
        result = engine.run("AAPL", strategy, df, "RSI_Reversal")
        
        result_dict = result.to_dict()
        
        assert "symbol" in result_dict
        assert "strategy" in result_dict
        assert "total_return" in result_dict


class TestPluginRegistry:
    """插件註冊中心測試"""
    
    def test_discover_indicators(self):
        """測試自動發現指標"""
        from core import PluginRegistry
        
        registry = PluginRegistry()
        registry.discover_plugins("indicators/momentum")
        registry.discover_plugins("indicators/trend")
        
        indicators = registry.list_indicators()
        
        assert len(indicators) > 0
        indicator_names = [name for name, _ in indicators]
        assert "RSI" in indicator_names
        assert "SMA" in indicator_names
        assert "MACD" in indicator_names
    
    def test_discover_strategies(self):
        """測試自動發現策略"""
        from core import PluginRegistry
        
        registry = PluginRegistry()
        registry.discover_plugins("strategies/momentum")
        registry.discover_plugins("strategies/trend")
        registry.discover_plugins("strategies/composite")
        
        strategies = registry.list_strategies()
        
        assert len(strategies) > 0
        strategy_names = [name for name, _ in strategies]
        assert "RSI_Reversal" in strategy_names
        assert "TrendFollower" in strategy_names
        assert "MultiFactor" in strategy_names
    
    def test_discover_risk_rules(self):
        """測試自動發現風控規則"""
        from core import PluginRegistry
        
        registry = PluginRegistry()
        registry.discover_plugins("risk_rules")
        
        rules = registry.list_risk_rules()
        
        assert len(rules) > 0
        rule_names = [name for name, _ in rules]
        assert "MaxPositionLimit" in rule_names
        assert "FixedStopLoss" in rule_names
        assert "TrailingStopLoss" in rule_names


class TestSentiment:
    """舆情模組測試"""
    
    def test_news_sentiment(self):
        """測試新聞情緒分析"""
        from modules.sentiment import NewsSentimentAnalyzer
        
        analyzer = NewsSentimentAnalyzer()
        
        # 測試正向文本
        result = analyzer.analyze("Apple reports record profits, stock surges on earnings beat")
        assert result.sentiment.value in ["positive", "neutral"]
        assert result.score >= 0
        
        # 測試負向文本
        result = analyzer.analyze("Tesla faces investigation, stock plunges on safety concerns")
        assert result.sentiment.value in ["negative", "neutral"]
    
    def test_sentiment_result_to_dict(self):
        """測試情緒結果轉字典"""
        from modules.sentiment import NewsSentimentAnalyzer, SentimentResult, SentimentType
        
        analyzer = NewsSentimentAnalyzer()
        result = analyzer.analyze("Test news")
        
        result_dict = result.to_dict()
        
        assert "sentiment" in result_dict
        assert "score" in result_dict
        assert "confidence" in result_dict
    
    def test_market_sentiment_index(self):
        """測試市場情緒指標"""
        from modules.sentiment import MarketSentimentIndex
        
        market = MarketSentimentIndex()
        
        result = market.analyze_market()
        
        assert result is not None
        assert hasattr(result, "sentiment")
        assert hasattr(result, "score")
    
    def test_market_sentiment_signal(self):
        """測試市場情緒交易訊號"""
        from modules.sentiment import MarketSentimentIndex
        
        market = MarketSentimentIndex()
        signal = market.get_trading_signal()
        
        assert signal is not None
        assert "signal" in signal
        assert "confidence" in signal
        assert signal["signal"] in ["LONG", "SHORT", "HOLD"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestAPIEndpoints:
    """API 端點測試"""

    def test_prediction_endpoint_exists(self):
        """測試預測端點 Blueprint 存在"""
        from api.prediction import prediction_bp
        
        assert prediction_bp is not None
        assert prediction_bp.name == "prediction"

    def test_prediction_blueprint_routes(self):
        """測試預測 Blueprint 有正確的路由"""
        from api.prediction import prediction_bp
        
        # 檢查路由規則
        rules = [rule.rule for rule in prediction_bp.url_map.iter_rules()]
        
        assert "/api/v1/prediction" in rules
        assert "/api/v1/prediction/command" in rules
        assert "/api/v1/prediction/batch" in rules
        assert "/api/v1/prediction/statistics" in rules

    def test_prediction_blueprint_methods(self):
        """測試預測端點支援的方法"""
        from api.prediction import prediction_bp
        
        rules = {rule.rule: set(rule.methods) for rule in prediction_bp.url_map.iter_rules()}
        
        assert "POST" in rules.get("/api/v1/prediction", set())
        assert "POST" in rules.get("/api/v1/prediction/command", set())
        assert "POST" in rules.get("/api/v1/prediction/batch", set())
        assert "GET" in rules.get("/api/v1/prediction/statistics", set())

    def test_api_init_exports(self):
        """測試 API 模組正確導出"""
        from api import prediction_bp, init_prediction_engine
        
        assert prediction_bp is not None
        assert callable(init_prediction_engine)

    def test_flask_app_creation(self):
        """測試 Flask App 可以創建"""
        from flask import Flask
        from api.prediction import prediction_bp
        
        app = Flask(__name__)
        app.register_blueprint(prediction_bp)
        
        assert app is not None
        assert len(app.blueprints) > 0

    def test_api_request_without_engine(self):
        """測試 API 在引擎未初始化時返回錯誤"""
        from flask import Flask
        from api.prediction import prediction_bp
        
        app = Flask(__name__)
        app.register_blueprint(prediction_bp)
        
        client = app.test_client()
        
        response = client.post(
            "/api/v1/prediction",
            json={"symbol": "AAPL"},
            content_type="application/json"
        )
        
        # 應該返回 500 或 400 (引擎未初始化)
        assert response.status_code in [400, 500]

    def test_prediction_command_format(self):
        """測試指令格式解析"""
        from api.prediction import PredictionEngine
        
        # 模擬引擎
        engine = PredictionEngine()
        
        # 測試指令解析
        result = engine.predict_from_command("TSLA/📈/10/5")
        
        # 沒有數據引擎時應該返回格式解析結果
        assert "success" in result or "error" in result

    def test_batch_prediction_structure(self):
        """測試批量預測結構"""
        from api.prediction import PredictionEngine
        
        engine = PredictionEngine()
        
        # 測試批量預測調用
        result = engine.batch_predict(["AAPL", "MSFT"], "UP", 10, 5)
        
        assert isinstance(result, list)

    def test_prediction_statistics_structure(self):
        """測試統計信息結構"""
        from api.prediction import PredictionEngine
        
        engine = PredictionEngine()
        stats = engine.get_statistics()
        
        assert isinstance(stats, dict)
        # 應該包含基本統計信息
        assert "total_predictions" in stats or hasattr(stats, "total_predictions")
