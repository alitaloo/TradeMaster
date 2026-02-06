# 複合策略集 #1 - Technical Indicator Combinations (策略 1-15)
# 2026-02-05

from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult
import pandas as pd
import numpy as np


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


import numpy as np


# ========== 策略 1-5: RSI 系列 ==========

@strategy(name="RSI_BB_Squeeze", type="composite",
    indicators=["RSI", "BollingerBands"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile", "neutral"])
class RSIBBSqueeze(BaseStrategy):
    """RSI + Bollinger Bands 擠壓策略"""
    def __init__(self, rsi_period: int = 14, bb_period: int = 20):
        self.rsi_period = rsi_period
        self.bb_period = bb_period
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        bb_percent = ind.get("BollingerBands", {}).get("percent", pd.Series([0.5]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        bb_val = bb_percent.iloc[-1] if len(bb_percent) > 0 else 0.5
        
        if bb_val < 0.1 and rsi_val < 35:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "squeeze_long"})
        elif bb_val > 0.9 and rsi_val > 65:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "squeeze_short"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"bb": bb_val, "rsi": rsi_val})


@strategy(name="RSI_MACD_Divergence", type="composite",
    indicators=["RSI", "MACD"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class RSIMACDDivergence(BaseStrategy):
    """RSI + MACD 背離策略"""
    def __init__(self, rsi_period: int = 14):
        self.rsi_period = rsi_period
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        prev_rsi = rsi.iloc[-5] if len(rsi) > 5 else rsi_val
        
        price = data["Close"]
        price_val = price.iloc[-1] if len(price) > 0 else 0
        prev_price = price.iloc[-5] if len(price) > 5 else price_val
        
        # 簡化背離檢測
        if rsi_val < 30 and rsi_val > prev_rsi and price_val < prev_price:
            return SignalResult(signal="LONG", confidence=0.75, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "bullish_divergence"})
        elif rsi_val > 70 and rsi_val < prev_rsi and price_val > prev_price:
            return SignalResult(signal="SHORT", confidence=0.75, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "bearish_divergence"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val})


@strategy(name="RSI_ADX_TrendConfirm", type="composite",
    indicators=["RSI", "ADX"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class RSIADXTrendConfirm(BaseStrategy):
    """RSI + ADX 趨勢確認策略"""
    def __init__(self, rsi_period: int = 14, adx_threshold: float = 25):
        self.rsi_period = rsi_period
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        
        if adx_val > self.adx_threshold:
            if plus_di.iloc[-1] > minus_di.iloc[-1] and rsi_val > 50:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "uptrend_confirm"})
            elif minus_di.iloc[-1] > plus_di.iloc[-1] and rsi_val < 50:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "downtrend_confirm"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val, "rsi": rsi_val})


@strategy(name="RSI_Stochastic_Oversold", type="composite",
    indicators=["RSI", "Stochastic"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"])
class RSIStochasticOversold(BaseStrategy):
    """RSI + Stochastic 雙重超賣"""
    def __init__(self, rsi_period: int = 14, stoch_period: int = 14):
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        
        if rsi_val < 30 and stoch_val < 20:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "double_oversold"})
        elif rsi_val > 70 and stoch_val > 80:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "double_overbought"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val, "stoch": stoch_val})


@strategy(name="RSI_Volume_Confirmation", type="composite",
    indicators=["RSI", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class RSIVolumeConfirmation(BaseStrategy):
    """RSI + 成交量確認"""
    def __init__(self, rsi_period: int = 14):
        self.rsi_period = rsi_period
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        
        if rsi_val < 30 and vr > 1.5:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "high_volume_bottom"})
        elif rsi_val > 70 and vr > 1.5:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "high_volume_top"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val, "vol_ratio": vr})


# ========== 策略 6-10: MACD 系列 ==========

@strategy(name="MACD_ADX_TrendRide", type="composite",
    indicators=["MACD", "ADX"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class MACDADXTrendRide(BaseStrategy):
    """MACD + ADX 趨勢騎乘"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        signal = ind.get("MACD", {}).get("signal", pd.Series([0]))
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        sig_val = signal.iloc[-1] if len(signal) > 0 else 0
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        
        if adx_val > self.adx_threshold:
            if macd_val > sig_val and macd_val > 0:
                return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "strong_uptrend"})
            elif macd_val < sig_val and macd_val < 0:
                return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "strong_downtrend"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val})


@strategy(name="MACD_BB_Breakout", type="composite",
    indicators=["MACD", "BollingerBands"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class MACDBBBreakout(BaseStrategy):
    """MACD + BB 突破策略"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        bb_percent = ind.get("BollingerBands", {}).get("percent", pd.Series([0.5]))
        
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        prev_macd = macd.iloc[-3] if len(macd) > 3 else macd_val
        bb_val = bb_percent.iloc[-1] if len(bb_percent) > 0 else 0.5
        
        # MACD 穿越零軸 + BB 突破
        if prev_macd < 0 and macd_val > 0 and bb_val > 0.8:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "bullish_breakout"})
        elif prev_macd > 0 and macd_val < 0 and bb_val < 0.2:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "bearish_breakout"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"macd": macd_val, "bb": bb_val})


@strategy(name="MACD_RSI_Crossover", type="composite",
    indicators=["MACD", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "neutral"])
class MACDRSICrossover(BaseStrategy):
    """MACD + RSI 交叉策略"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        signal = ind.get("MACD", {}).get("signal", pd.Series([0]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        prev_macd = macd.iloc[-1] if len(macd) > 0 else 0
        sig_val = signal.iloc[-1] if len(signal) > 0 else 0
        prev_sig = signal.iloc[-2] if len(signal) > 1 else sig_val
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        # MACD 金叉/死叉 + RSI 確認
        if prev_macd <= prev_sig and macd_val > sig_val and rsi_val > 50:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "golden_cross"})
        elif prev_macd >= prev_sig and macd_val < sig_val and rsi_val < 50:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "death_cross"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val})


@strategy(name="MACD_Volume_Trend", type="composite",
    indicators=["MACD", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class MACDVolumeTrend(BaseStrategy):
    """MACD + 成交量趨勢"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        macd = ind.get("MACD", {}).get("histogram", pd.Series([0]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        hist_val = macd.iloc[-1] if len(macd) > 0 else 0
        hist_prev = macd.iloc[-2] if len(macd) > 1 else hist_val
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        
        if hist_val > 0 and hist_val > hist_prev and vr > 1.2:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "volume_confirmed_up"})
        elif hist_val < 0 and hist_val < hist_prev and vr > 1.2:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "volume_confirmed_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"hist": hist_val, "vol": vr})


@strategy(name="MACD_SMA_Crossover", type="composite",
    indicators=["MACD", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class MACDSMACrossover(BaseStrategy):
    """MACD + SMA 交叉策略"""
    def __init__(self, sma_period: int = 50):
        self.sma_period = sma_period
    
    def generate_signal(self, ind, data):
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        signal = ind.get("MACD", {}).get("signal", pd.Series([0]))
        sma = ind.get("SMA", {}).get("sma", pd.Series([0]))
        close = data["Close"]
        
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        sig_val = signal.iloc[-1] if len(signal) > 0 else 0
        sma_val = sma.iloc[-1] if len(sma) > 0 else close.iloc[-1]
        price_val = close.iloc[-1] if len(close) > 0 else 0
        
        if macd_val > sig_val and price_val > sma_val:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "trend_aligned"})
        elif macd_val < sig_val and price_val < sma_val:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "trend_aligned"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"above_sma": price_val > sma_val})


# ========== 策略 11-15: ADX 系列 ==========

@strategy(name="ADX_Trend_Strength", type="composite",
    indicators=["ADX", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class ADXTrendStrength(BaseStrategy):
    """ADX 趨勢強度策略"""
    def __init__(self, adx_strong: float = 30, adx_weak: float = 20):
        self.adx_strong = adx_strong
        self.adx_weak = adx_weak
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        if adx_val > self.adx_strong:
            if plus_di.iloc[-1] > minus_di.iloc[-1]:
                return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "strong_trend_up"})
            else:
                return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "strong_trend_down"})
        elif adx_val < self.adx_weak:
            return SignalResult(signal="HOLD", confidence=0.5, price=_get_current_price(data), reason="Hold position", metadata={"type": "weak_trend"})
        return SignalResult(signal="HOLD", confidence=0.4, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val, "rsi": rsi_val})


@strategy(name="ADX_Volatility_Expansion", type="composite",
    indicators=["ADX", "ATR"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class ADXVolatilityExpansion(BaseStrategy):
    """ADX + ATR 波動率擴張"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        atr = ind.get("ATR", {}).get("atr", pd.Series([0]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        atr_val = atr.iloc[-1] if len(atr) > 0 else 0
        atr_prev = atr.iloc[-5] if len(atr) > 5 else atr_val
        atr_change = (atr_val - atr_prev) / atr_prev if atr_prev > 0 else 0
        
        if adx_val > self.adx_threshold and atr_change > 0.2:
            if plus_di.iloc[-1] > minus_di.iloc[-1]:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "volatility_expansion_up"})
            else:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "volatility_expansion_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val, "atr_change": atr_change})


@strategy(name="ADX_Stochastic_Momentum", type="composite",
    indicators=["ADX", "Stochastic"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class ADXStochasticMomentum(BaseStrategy):
    """ADX + Stochastic 動量策略"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        
        if adx_val > self.adx_threshold:
            if plus_di.iloc[-1] > minus_di.iloc[-1] and stoch_val < 80:
                return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "uptrend_momentum"})
            elif minus_di.iloc[-1] > plus_di.iloc[-1] and stoch_val > 20:
                return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "downtrend_momentum"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val, "stoch": stoch_val})


@strategy(name="ADX_ParabolicSAR_Stop", type="composite",
    indicators=["ADX", "ParabolicSAR"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class ADXParabolicSARStop(BaseStrategy):
    """ADX + ParabolicSAR 止損策略"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        sar = ind.get("ParabolicSAR", {}).get("sar", pd.Series([0]))
        trend = ind.get("ParabolicSAR", {}).get("trend_direction", pd.Series([1]))
        close = data["Close"]
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        sar_val = sar.iloc[-1] if len(sar) > 0 else close.iloc[-1]
        trend_val = trend.iloc[-1] if len(trend) > 0 else 1
        price_val = close.iloc[-1] if len(close) > 0 else 0
        
        if adx_val > self.adx_threshold:
            if trend_val == 1 and price_val > sar_val:
                return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "sar_below_price"})
            elif trend_val == -1 and price_val < sar_val:
                return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "sar_above_price"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val})


@strategy(name="ADX_Ichimoku_Cloud", type="composite",
    indicators=["ADX", "IchimokuCloud"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class ADXIchimokuCloud(BaseStrategy):
    """ADX + Ichimoku 雲圖策略"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        ichimoku = ind.get("IchimokuCloud", {})
        kijun = ichimoku.get("kijun", pd.Series([0]))
        tenkan = ichimoku.get("tenkan", pd.Series([0]))
        cloud_top = ichimoku.get("cloud_top", pd.Series([0]))
        cloud_bottom = ichimoku.get("cloud_bottom", pd.Series([0]))
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        kijun_val = kijun.iloc[-1] if len(kijun) > 0 else 0
        tenkan_val = tenkan.iloc[-1] if len(tenkan) > 0 else 0
        close = data["Close"].iloc[-1] if len(data["Close"]) > 0 else 0
        
        if adx_val > self.adx_threshold:
            # 價格在雲上方 + 趨勢確認
            if close > cloud_top.iloc[-1] and tenkan_val > kijun_val:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Bullish signal detected", metadata={"type": "above_cloud"})
            elif close < cloud_bottom.iloc[-1] and tenkan_val < kijun_val:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Bearish signal detected", metadata={"type": "below_cloud"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val})
