# 趨勢指標 - Trend Indicators

import pandas as pd
import numpy as np
from core.decorators import indicator
from core.base_classes import BaseIndicator, IndicatorResult


@indicator(name="SMA", category="trend",
    parameters={"period": {"type": int, "default": 20}},
    outputs=["sma", "sma_slope"], tags=["trend", "moving_average"])
class SMAIndicator(BaseIndicator):
    """Simple Moving Average"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        sma = close.rolling(self.period).mean()
        
        # SMA 斜率
        sma_slope = sma.diff(self.period) / self.period
        
        return IndicatorResult(
            values={"sma": sma, "sma_slope": sma_slope},
            last_value={"sma": sma.iloc[-1], "sma_slope": sma_slope.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="EMA", category="trend",
    parameters={"period": {"type": int, "default": 12}},
    outputs=["ema", "ema_slope"], tags=["trend", "moving_average"])
class EMAIndicator(BaseIndicator):
    """Exponential Moving Average"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        ema = close.ewm(span=self.period, adjust=False).mean()
        ema_slope = ema.diff(self.period) / self.period
        
        return IndicatorResult(
            values={"ema": ema, "ema_slope": ema_slope},
            last_value={"ema": ema.iloc[-1], "ema_slope": ema_slope.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="MACD", category="trend",
    parameters={"fast_period": {"type": int, "default": 12}, "slow_period": {"type": int, "default": 26}, "signal_period": {"type": int, "default": 9}},
    outputs=["macd", "signal", "histogram"], tags=["trend", "momentum", "oscillator"])
class MACDIndicator(BaseIndicator):
    """MACD"""
    
    def compute(self, data):
        self.validate_input(data, ["Close"])
        close = data["Close"]
        
        fast = close.ewm(span=self.fast_period, adjust=False).mean()
        slow = close.ewm(span=self.slow_period, adjust=False).mean()
        
        macd = fast - slow
        signal = macd.ewm(span=self.signal_period, adjust=False).mean()
        histogram = macd - signal
        
        return IndicatorResult(
            values={"macd": macd, "signal": signal, "histogram": histogram},
            last_value={"macd": macd.iloc[-1], "signal": signal.iloc[-1], "histogram": histogram.iloc[-1]},
            metadata={"fast": self.fast_period, "slow": self.slow_period}
        )


@indicator(name="ADX", category="trend",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["adx", "plus_di", "minus_di", "trend_strength"], tags=["trend", "strength", "directional"])
class ADXIndicator(BaseIndicator):
    """Average Directional Index"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(self.period).mean()
        
        plus_dm = high.diff().clip(lower=0).where(high.diff() > low.diff().abs(), 0)
        minus_dm = (-low.diff()).clip(lower=0).where(low.diff().abs() > high.diff(), 0)
        
        plus_di = 100 * plus_dm.rolling(self.period).mean() / atr
        minus_di = 100 * minus_dm.rolling(self.period).mean() / atr
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        adx = dx.rolling(self.period).mean()
        
        trend_strength = pd.cut(adx, bins=[0, 20, 25, 50, 100], labels=["very_weak", "weak", "moderate", "strong"])
        
        return IndicatorResult(
            values={"adx": adx, "plus_di": plus_di, "minus_di": minus_di, "trend_strength": trend_strength},
            last_value={"adx": adx.iloc[-1], "plus_di": plus_di.iloc[-1], "minus_di": minus_di.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="ParabolicSAR", category="trend",
    parameters={"af_start": {"type": float, "default": 0.02}, "af_max": {"type": float, "default": 0.2}},
    outputs=["sar", "trend_direction"], tags=["trend", "stop_reversal"])
class ParabolicSARIndicator(BaseIndicator):
    """Parabolic SAR"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        sar = pd.Series(0.0, index=data.index)
        trend = pd.Series(1, index=data.index)  # 1=up, -1=down
        af = self.af_start
        ep = high.iloc[0] if trend.iloc[0] == 1 else low.iloc[0]
        
        sar.iloc[0] = low.iloc[0] if trend.iloc[0] == 1 else high.iloc[0]
        
        for i in range(1, len(data)):
            prev_sar = sar.iloc[i-1]
            
            if trend.iloc[i-1] == 1:
                sar.iloc[i] = prev_sar + af * (ep - prev_sar)
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + self.af_start, self.af_max)
                if sar.iloc[i] > low.iloc[i]:
                    trend.iloc[i] = -1
                    sar.iloc[i] = ep
                    af = self.af_start
                    ep = low.iloc[i]
            else:
                sar.iloc[i] = prev_sar - af * (prev_sar - ep)
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + self.af_start, self.af_max)
                if sar.iloc[i] < high.iloc[i]:
                    trend.iloc[i] = 1
                    sar.iloc[i] = ep
                    af = self.af_start
                    ep = high.iloc[i]
        
        return IndicatorResult(
            values={"sar": sar, "trend_direction": trend},
            last_value={"sar": sar.iloc[-1], "trend_direction": int(trend.iloc[-1])},
            metadata={"af_start": self.af_start}
        )


@indicator(name="IchimokuCloud", category="trend",
    parameters={"tenkan": {"type": int, "default": 9}, "kijun": {"type": int, "default": 26}, "senkou_b": {"type": int, "default": 52}},
    outputs=["tenkan", "kijun", "senkou_a", "senkou_b", "cloud_top", "cloud_bottom", "chikou"], tags=["trend", "cloud", "comprehensive"])
class IchimokuCloudIndicator(BaseIndicator):
    """Ichimoku Cloud"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close"])
        high, low, close = data["High"], data["Low"], data["Close"]
        
        # Tenkan-sen (Conversion Line)
        tenkan = (high.rolling(self.tenkan).max() + low.rolling(self.tenkan).min()) / 2
        
        # Kijun-sen (Base Line)
        kijun = (high.rolling(self.kijun).max() + low.rolling(self.kijun).min()) / 2
        
        # Senkou Span A (Leading Span A)
        senkou_a = ((tenkan + kijun) / 2).shift(self.kijun)
        
        # Senkou Span B (Leading Span B)
        senkou_b = ((high.rolling(self.senkou_b).max() + low.rolling(self.senkou_b).min()) / 2).shift(self.kijun)
        
        # Cloud
        cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)
        
        # Chikou Span (Lagging Span)
        chikou = close.shift(-self.kijun)
        
        return IndicatorResult(
            values={"tenkan": tenkan, "kijun": kijun, "senkou_a": senkou_a, "senkou_b": senkou_b, 
                   "cloud_top": cloud_top, "cloud_bottom": cloud_bottom, "chikou": chikou},
            last_value={"tenkan": tenkan.iloc[-1], "kijun": kijun.iloc[-1]},
            metadata={}
        )


@indicator(name=" Aroon", category="trend",
    parameters={"period": {"type": int, "default": 25}},
    outputs=["aroon_up", "aroon_down", "aroon_oscillator"], tags=["trend", "oscillator"])
class AroonIndicator(BaseIndicator):
    """Aroon Indicator"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low"])
        high, low = data["High"], data["Low"]
        
        aroon_up = 100 * (self.period - high.rolling(self.period).apply(lambda x: self.period - x.argmax())) / self.period
        aroon_down = 100 * (self.period - low.rolling(self.period).apply(lambda x: self.period - x.argmin())) / self.period
        
        aroon_osc = aroon_up - aroon_down
        
        return IndicatorResult(
            values={"aroon_up": aroon_up, "aroon_down": aroon_down, "aroon_oscillator": aroon_osc},
            last_value={"aroon_up": aroon_up.iloc[-1], "aroon_down": aroon_down.iloc[-1], "aroon_oscillator": aroon_osc.iloc[-1]},
            metadata={"period": self.period}
        )
