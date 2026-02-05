# 波動率指標 - Volatility Indicators

import pandas as pd
import numpy as np
from core.decorators import indicator
from core.base_classes import BaseIndicator, IndicatorResult


@indicator(name="ATR", category="volatility",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["atr", "true_range"], tags=["volatility", "atr"])
class ATRIndicator(BaseIndicator):
    """Average True Range - 平均真實波幅"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(self.period).mean()
        
        return IndicatorResult(
            values={"atr": atr, "true_range": tr},
            last_value={"atr": atr.iloc[-1], "true_range": tr.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="VolatilityRatio", category="volatility",
    parameters={"short_period": {"type": int, "default": 5}, "long_period": {"type": int, "default": 20}},
    outputs=["ratio", "volatility_state"], tags=["volatility", "ratio"])
class VolatilityRatioIndicator(BaseIndicator):
    """波動率比率 - 短期/長期波動率比較"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        short_vol = close.rolling(self.short_period).std()
        long_vol = close.rolling(self.long_period).std()
        ratio = short_vol / long_vol
        
        # 波動率狀態
        volatility_state = pd.cut(
            ratio,
            bins=[0, 0.8, 1.2, np.inf],
            labels=["contracting", "normal", "expanding"]
        )
        
        return IndicatorResult(
            values={"ratio": ratio, "volatility_state": volatility_state},
            last_value={"ratio": ratio.iloc[-1], "volatility_state": str(volatility_state.iloc[-1])},
            metadata={"short": self.short_period, "long": self.long_period}
        )


@indicator(name="KeltnerChannel", category="volatility",
    parameters={"period": {"type": int, "default": 20}, "atr_period": {"type": int, "default": 10}, "multiplier": {"type": float, "default": 2.0}},
    outputs=["upper", "middle", "lower"], tags=["volatility", "channel"])
class KeltnerChannelIndicator(BaseIndicator):
    """Keltner Channel - 肯特納通道"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        # EMA 中軌
        middle = close.ewm(span=self.period, adjust=False).mean()
        
        # True Range
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(self.atr_period).mean()
        
        upper = middle + atr * self.multiplier
        lower = middle - atr * self.multiplier
        
        return IndicatorResult(
            values={"upper": upper, "middle": middle, "lower": lower},
            last_value={"upper": upper.iloc[-1], "middle": middle.iloc[-1], "lower": lower.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="HistoricalVolatility", category="volatility",
    parameters={"period": {"type": int, "default": 21}, "rolling_period": {"type": int, "default": 252}},
    outputs=["hv", "hv_percentile"], tags=["volatility", "historical"])
class HistoricalVolatilityIndicator(BaseIndicator):
    """歷史波動率"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        returns = close.pct_change()
        hv = returns.rolling(self.period).std() * np.sqrt(252)
        
        # 歷史百分位
        hv_percentile = returns.rolling(self.rolling_period).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100
        )
        
        return IndicatorResult(
            values={"hv": hv, "hv_percentile": hv_percentile},
            last_value={"hv": hv.iloc[-1], "hv_percentile": hv_percentile.iloc[-1]},
            metadata={"period": self.period}
        )
