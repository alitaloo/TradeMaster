# 均值回歸指標 - Mean Reversion Indicators

import pandas as pd
import numpy as np
from core.decorators import indicator
from core.base_classes import BaseIndicator, IndicatorResult


@indicator(name="BollingerBands", category="mean_reversion",
    parameters={"period": {"type": int, "default": 20}, "std_dev": {"type": float, "default": 2.0}},
    outputs=["upper", "middle", "lower", "percent"], tags=["mean_reversion", "bands"])
class BollingerBandsIndicator(BaseIndicator):
    """Bollinger Bands - 布林帶"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        middle = close.rolling(self.period).mean()
        std = close.rolling(self.period).std()
        upper = middle + std * self.std_dev
        lower = middle - std * self.std_dev
        
        # %B 位置
        percent = (close - lower) / (upper - lower + 1e-10)
        
        return IndicatorResult(
            values={"upper": upper, "middle": middle, "lower": lower, "percent": percent},
            last_value={"upper": upper.iloc[-1], "middle": middle.iloc[-1], "lower": lower.iloc[-1], "percent": percent.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="RSI", category="mean_reversion",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["rsi", "signal"], tags=["mean_reversion", "oscillator"])
class RSIIndicator(BaseIndicator):
    """Relative Strength Index"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(self.period).mean()
        
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        
        # 信號
        signal = pd.cut(rsi, bins=[0, 30, 70, 100], labels=["oversold", "neutral", "overbought"])
        
        return IndicatorResult(
            values={"rsi": rsi, "signal": signal},
            last_value={"rsi": rsi.iloc[-1], "signal": str(signal.iloc[-1])},
            metadata={"period": self.period}
        )


@indicator(name="Stochastic", category="mean_reversion",
    parameters={"k_period": {"type": int, "default": 14}, "d_period": {"type": int, "default": 3}},
    outputs=["stoch_k", "stoch_d", "signal"], tags=["mean_reversion", "oscillator"])
class StochasticIndicator(BaseIndicator):
    """Stochastic Oscillator"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        lowest_low = low.rolling(self.k_period).min()
        highest_high = high.rolling(self.k_period).max()
        
        stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-10)
        stoch_d = stoch_k.rolling(self.d_period).mean()
        
        signal = pd.cut(stoch_k, bins=[0, 20, 80, 100], labels=["oversold", "neutral", "overbought"])
        
        return IndicatorResult(
            values={"stoch_k": stoch_k, "stoch_d": stoch_d, "signal": signal},
            last_value={"stoch_k": stoch_k.iloc[-1], "stoch_d": stoch_d.iloc[-1], "signal": str(signal.iloc[-1])},
            metadata={"k_period": self.k_period}
        )


@indicator(name="WilliamsR", category="mean_reversion",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["williams_r", "signal"], tags=["mean_reversion", "oscillator"])
class WilliamsRIndicator(BaseIndicator):
    """Williams %R"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        highest_high = high.rolling(self.period).max()
        lowest_low = low.rolling(self.period).min()
        
        williams_r = -100 * (highest_high - close) / (highest_high - lowest_low + 1e-10)
        
        signal = pd.cut(williams_r, bins=[-100, -80, -20, 0], labels=["oversold", "neutral", "overbought"])
        
        return IndicatorResult(
            values={"williams_r": williams_r, "signal": signal},
            last_value={"williams_r": williams_r.iloc[-1], "signal": str(signal.iloc[-1])},
            metadata={"period": self.period}
        )


@indicator(name="CCI", category="mean_reversion",
    parameters={"period": {"type": int, "default": 20}},
    outputs=["cci", "signal"], tags=["mean_reversion", "oscillator"])
class CCIIndicator(BaseIndicator):
    """Commodity Channel Index"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        typical_price = (high + low + close) / 3
        sma = typical_price.rolling(self.period).mean()
        mad = typical_price.rolling(self.period).apply(lambda x: abs(x - x.mean()).mean())
        
        cci = (typical_price - sma) / (0.015 * mad + 1e-10)
        
        signal = pd.cut(cci, bins=[-np.inf, -100, 100, np.inf], labels=["oversold", "neutral", "overbought"])
        
        return IndicatorResult(
            values={"cci": cci, "signal": signal},
            last_value={"cci": cci.iloc[-1], "signal": str(signal.iloc[-1])},
            metadata={"period": self.period}
        )


@indicator(name="RateOfChange", category="mean_reversion",
    parameters={"period": {"type": int, "default": 10}},
    outputs=["roc", "roc_signal"], tags=["mean_reversion", "momentum"])
class ROCIndicator(BaseIndicator):
    """Rate of Change"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        roc = (close - close.shift(self.period)) / close.shift(self.period) * 100
        
        # 信號
        roc_signal = pd.cut(roc, bins=[-np.inf, -5, 5, np.inf], labels=["oversold", "neutral", "overbought"])
        
        return IndicatorResult(
            values={"roc": roc, "roc_signal": roc_signal},
            last_value={"roc": roc.iloc[-1], "roc_signal": str(roc_signal.iloc[-1])},
            metadata={"period": self.period}
        )


@indicator(name="UltimateOscillator", category="mean_reversion",
    parameters={"period1": {"type": int, "default": 7}, "period2": {"type": int, "default": 14}, "period3": {"type": int, "default": 28}},
    outputs=["uo", "signal"], tags=["mean_reversion", "oscillator"])
class UltimateOscillator(BaseIndicator):
    """Ultimate Oscillator"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        # True Range
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        
        # Buying Pressure
        bp = close - pd.concat([low, close.shift(1)], axis=1).min(axis=1)
        
        # Weighted averages
        avg1 = bp.rolling(self.period1).sum() / tr.rolling(self.period1).sum()
        avg2 = bp.rolling(self.period2).sum() / tr.rolling(self.period2).sum()
        avg3 = bp.rolling(self.period3).sum() / tr.rolling(self.period3).sum()
        
        uo = 100 * (4*avg1 + 2*avg2 + avg3) / 7
        signal = pd.cut(uo, bins=[0, 30, 70, 100], labels=["oversold", "neutral", "overbought"])
        
        return IndicatorResult(
            values={"uo": uo, "signal": signal},
            last_value={"uo": uo.iloc[-1], "signal": str(signal.iloc[-1])},
            metadata={}
        )
