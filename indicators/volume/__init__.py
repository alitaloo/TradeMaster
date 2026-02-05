# 成交量指標 - Volume Indicators

import pandas as pd
import numpy as np
from core.decorators import indicator
from core.base_classes import BaseIndicator, IndicatorResult


@indicator(name="OBV", category="volume",
    parameters={},
    outputs=["obv", "obv_sma"], tags=["volume", "on_balance"])
class OBVIndicator(BaseIndicator):
    """On-Balance Volume - 能量潮"""
    
    def compute(self, data):
        self.validate_input(data, ["Close", "Volume"])
        close, volume = data["Close"], data["Volume"]
        
        # OBV 計算
        obv = pd.Series(0, index=data.index)
        for i in range(1, len(data)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        # OBV 移動平均
        obv_sma = obv.rolling(20).mean()
        
        return IndicatorResult(
            values={"obv": obv, "obv_sma": obv_sma},
            last_value={"obv": obv.iloc[-1], "obv_sma": obv_sma.iloc[-1]},
            metadata={}
        )


@indicator(name="VolumeEMA", category="volume",
    parameters={"period": {"type": int, "default": 20}},
    outputs=["volume_ema", "volume_ratio"], tags=["volume", "ema"])
class VolumeEMAIndicator(BaseIndicator):
    """成交量 EMA"""
    
    def compute(self, data):
        self.validate_input(data, ["Volume"])
        volume = data["Volume"]
        
        vol_ema = volume.ewm(span=self.period, adjust=False).mean()
        volume_ratio = volume / vol_ema
        
        return IndicatorResult(
            values={"volume_ema": vol_ema, "volume_ratio": volume_ratio},
            last_value={"volume_ema": vol_ema.iloc[-1], "volume_ratio": volume_ratio.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="VWAP", category="volume",
    parameters={},
    outputs=["vwap", "vwap_deviation"], tags=["volume", "average_price"])
class VWAPIndicator(BaseIndicator):
    """Volume Weighted Average Price"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close", "Volume"])
        high, low, close, volume = data["High"], data["Low"], data["Close"], data["Volume"]
        
        # 典型價格
        typical_price = (high + low + close) / 3
        
        # VWAP
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        
        # 價格偏離 VWAP
        vwap_deviation = (close - vwap) / vwap * 100
        
        return IndicatorResult(
            values={"vwap": vwap, "vwap_deviation": vwap_deviation},
            last_value={"vwap": vwap.iloc[-1], "vwap_deviation": vwap_deviation.iloc[-1]},
            metadata={}
        )


@indicator(name="AccumulationDistribution", category="volume",
    parameters={"period": {"type": int, "default": 14}},
    outputs=["ad", "ad_ema"], tags=["volume", "accumulation"])
class ADIndicator(BaseIndicator):
    """Accumulation/Distribution - 累積/分配"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close", "Volume"])
        high, low, close, volume = data["High"], data["Low"], data["Close"], data["Volume"]
        
        # Money Flow Multiplier
        mfm = ((close - low) - (high - close)) / (high - low + 1e-10)
        
        # Money Flow Volume
        mfv = mfm * volume
        
        # Accumulation/Distribution Line
        ad = mfv.cumsum()
        ad_ema = ad.ewm(span=self.period, adjust=False).mean()
        
        return IndicatorResult(
            values={"ad": ad, "ad_ema": ad_ema},
            last_value={"ad": ad.iloc[-1], "ad_ema": ad_ema.iloc[-1]},
            metadata={"period": self.period}
        )


@indicator(name="ChaikinOscillator", category="volume",
    parameters={"short_period": {"type": int, "default": 3}, "long_period": {"type": int, "default": 10}},
    outputs=["chaikin_osc", "signal"], tags=["volume", "oscillator"])
class ChaikinOscillator(BaseIndicator):
    """Chaikin Oscillator"""
    
    def compute(self, data):
        self.validate_input(data, ["High", "Low", "Close", "Volume"])
        high, low, close, volume = data["High"], data["Low"], data["Close"], data["Volume"]
        
        mfm = ((close - low) - (high - close)) / (high - low + 1e-10)
        mfv = mfm * volume
        ad = mfv.cumsum()
        
        short_ema = ad.ewm(span=self.short_period, adjust=False).mean()
        long_ema = ad.ewm(span=self.long_period, adjust=False).mean()
        
        chaikin_osc = short_ema - long_ema
        signal = chaikin_osc.ewm(span=5, adjust=False).mean()
        
        return IndicatorResult(
            values={"chaikin_osc": chaikin_osc, "signal": signal},
            last_value={"chaikin_osc": chaikin_osc.iloc[-1], "signal": signal.iloc[-1]},
            metadata={"short": self.short_period, "long": self.long_period}
        )
