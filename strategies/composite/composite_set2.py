# 複合策略集 #2 - Volume & Volatility Combinations (策略 16-30)
# 2026-02-05
# 修復：所有 SignalResult 都包含 price 和 reason 參數

from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult
import pandas as pd
import numpy as np


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


# ========== 策略 16-20: Volume 系列 ==========

@strategy(name="Volume_Price_Confirmation", type="composite",
    indicators=["VolumeEMA", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class VolumePriceConfirmation(BaseStrategy):
    """成交量價格確認"""
    def __init__(self, vol_threshold: float = 1.5):
        self.vol_threshold = vol_threshold
    
    def generate_signal(self, ind, data):
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        
        close = data["Close"]
        close_prev = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
        price_up = close.iloc[-1] > close_prev
        current_price = _get_current_price(data)
        
        if vr > self.vol_threshold:
            if price_up and rsi_val > 50:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Volume confirmation with RSI bullish", metadata={"type": "volume_confirmation_up"})
            elif not price_up and rsi_val < 50:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Volume confirmation with RSI bearish", metadata={"type": "volume_confirmation_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"vol_ratio": vr})


@strategy(name="OBV_Trend_Follow", type="composite",
    indicators=["OBV", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class OBVTrendFollow(BaseStrategy):
    """OBV 趨勢跟隨"""
    def __init__(self, sma_period: int = 20):
        self.sma_period = sma_period
    
    def generate_signal(self, ind, data):
        obv = ind.get("OBV", {}).get("obv", pd.Series([0]))
        obv_sma = ind.get("OBV", {}).get("obv_sma", pd.Series([0]))
        close = data["Close"]
        sma = ind.get("SMA", {}).get("sma", pd.Series([0]))
        
        obv_val = obv.iloc[-1] if len(obv) > 0 else 0
        obv_sma_val = obv_sma.iloc[-1] if len(obv_sma) > 0 else 0
        price_val = close.iloc[-1] if len(close) > 0 else 0
        sma_val = sma.iloc[-1] if len(sma) > 0 else 0
        current_price = _get_current_price(data)
        
        obv_trend = obv_val > obv_sma_val
        price_trend = price_val > sma_val
        
        if obv_trend == price_trend:
            if obv_trend:
                return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="OBV confirmed uptrend", metadata={"type": "confirmed_uptrend"})
            else:
                return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="OBV confirmed downtrend", metadata={"type": "confirmed_downtrend"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"obv_trend": obv_trend, "price_trend": price_trend})


@strategy(name="VWAP_Reversal", type="composite",
    indicators=["VWAP", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"])
class VWAPReversal(BaseStrategy):
    """VWAP 反轉策略"""
    def __init__(self, deviation_threshold: float = 2.0):
        self.deviation_threshold = deviation_threshold
    
    def generate_signal(self, ind, data):
        vwap_dev = ind.get("VWAP", {}).get("vwap_deviation", pd.Series([0]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        dev_val = vwap_dev.iloc[-1] if len(vwap_dev) > 0 else 0
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        current_price = _get_current_price(data)
        
        if dev_val < -self.deviation_threshold and rsi_val < 35:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="VWAP oversold with RSI", metadata={"type": "vwap_oversold"})
        elif dev_val > self.deviation_threshold and rsi_val > 65:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="VWAP overbought with RSI", metadata={"type": "vwap_overbought"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"deviation": dev_val, "rsi": rsi_val})


@strategy(name="AD_Accumulation", type="composite",
    indicators=["AccumulationDistribution", "MACD"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class ADAccumulation(BaseStrategy):
    """A/D 累積/分配策略"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        ad = ind.get("AccumulationDistribution", {}).get("ad", pd.Series([0]))
        ad_ema = ind.get("AccumulationDistribution", {}).get("ad_ema", pd.Series([0]))
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        signal = ind.get("MACD", {}).get("signal", pd.Series([0]))
        
        ad_val = ad.iloc[-1] if len(ad) > 0 else 0
        ad_ema_val = ad_ema.iloc[-1] if len(ad_ema) > 0 else 0
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        sig_val = signal.iloc[-1] if len(signal) > 0 else 0
        current_price = _get_current_price(data)
        
        ad_trend = ad_val > ad_ema_val
        macd_bullish = macd_val > sig_val
        
        if ad_trend and macd_bullish:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="A/D accumulation with MACD bullish", metadata={"type": "accumulation"})
        elif not ad_trend and not macd_bullish:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="A/D distribution with MACD bearish", metadata={"type": "distribution"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={})


@strategy(name="Chaikin_Volume_Oscillator", type="composite",
    indicators=["ChaikinOscillator", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class ChaikinVolumeOscillator(BaseStrategy):
    """Chaikin 成交量振盪器"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        chaikin = ind.get("ChaikinOscillator", {}).get("chaikin_osc", pd.Series([0]))
        signal = ind.get("ChaikinOscillator", {}).get("signal", pd.Series([0]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        osc_val = chaikin.iloc[-1] if len(chaikin) > 0 else 0
        sig_val = signal.iloc[-1] if len(signal) > 0 else 0
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        current_price = _get_current_price(data)
        
        if osc_val > sig_val and rsi_val > 50:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Chaikin bullish flow", metadata={"type": "bullish_flow"})
        elif osc_val < sig_val and rsi_val < 50:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Chaikin bearish flow", metadata={"type": "bearish_flow"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"osc": osc_val})


# ========== 策略 21-25: Volatility 系列 ==========

@strategy(name="ATR_Trend_Confirmation", type="composite",
    indicators=["ATR", "ADX"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class ATRTrendConfirmation(BaseStrategy):
    """ATR 趨勢確認"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        atr = ind.get("ATR", {}).get("atr", pd.Series([0]))
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        
        atr_val = atr.iloc[-1] if len(atr) > 0 else 0
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        current_price = _get_current_price(data)
        
        if adx_val > 25:
            if plus_di.iloc[-1] > minus_di.iloc[-1]:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Strong uptrend with ATR confirmation", metadata={"type": "strong_trend", "atr": float(atr_val)})
            else:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Strong downtrend with ATR confirmation", metadata={"type": "strong_trend", "atr": float(atr_val)})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": float(adx_val)})


@strategy(name="BollingerWidth_Expansion", type="composite",
    indicators=["BollingerBands", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class BollingerWidthExpansion(BaseStrategy):
    """布林帶寬度擴張"""
    def __init__(self, width_threshold: float = 0.1):
        self.width_threshold = width_threshold
    
    def generate_signal(self, ind, data):
        bb = ind.get("BollingerBands", {})
        upper = bb.get("upper", pd.Series([0]))
        lower = bb.get("lower", pd.Series([0]))
        middle = bb.get("middle", pd.Series([0]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        width = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1] if len(middle) > 0 else 0
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        
        close = data["Close"].iloc[-1]
        prev_close = data["Close"].iloc[-2] if len(data["Close"]) > 1 else close
        price_up = close > prev_close
        current_price = _get_current_price(data)
        
        if width > self.width_threshold and vr > 1.3:
            if price_up:
                return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="BB breakout upward", metadata={"type": "breakout_up"})
            else:
                return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="BB breakout downward", metadata={"type": "breakout_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"width": width, "vol": vr})


@strategy(name="Keltner_Bollinger_Squeeze", type="composite",
    indicators=["KeltnerChannel", "BollingerBands"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class KeltnerBollingerSqueeze(BaseStrategy):
    """Keltner + BB 擠壓策略"""
    def __init__(self, squeeze_threshold: float = 0.5):
        self.squeeze_threshold = squeeze_threshold
    
    def generate_signal(self, ind, data):
        keltner = ind.get("KeltnerChannel", {})
        k_upper = keltner.get("upper", pd.Series([0]))
        k_lower = keltner.get("lower", pd.Series([0]))
        bb = ind.get("BollingerBands", {})
        b_upper = bb.get("upper", pd.Series([0]))
        b_lower = bb.get("lower", pd.Series([0]))
        
        k_width = k_upper.iloc[-1] - k_lower.iloc[-1] if len(k_upper) > 0 else 0
        b_width = b_upper.iloc[-1] - b_lower.iloc[-1] if len(b_upper) > 0 else 0
        
        ratio = b_width / (k_width + 0.001)
        close = data["Close"].iloc[-1]
        k_middle = keltner.get("middle", pd.Series([close])).iloc[-1]
        current_price = _get_current_price(data)
        
        if ratio < self.squeeze_threshold:
            if close > k_middle:
                return SignalResult(signal="LONG", confidence=0.75, price=_get_current_price(data), reason="BB squeeze bullish", metadata={"type": "squeeze_long", "ratio": ratio})
            else:
                return SignalResult(signal="SHORT", confidence=0.75, price=_get_current_price(data), reason="BB squeeze bearish", metadata={"type": "squeeze_short", "ratio": ratio})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"ratio": ratio})


@strategy(name="HistoricalVolatility_Range", type="composite",
    indicators=["HistoricalVolatility", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class HistoricalVolatilityRange(BaseStrategy):
    """歷史波動率範圍"""
    def __init__(self, hv_percentile_high: float = 80, hv_percentile_low: float = 20):
        self.hv_percentile_high = hv_percentile_high
        self.hv_percentile_low = hv_percentile_low
    
    def generate_signal(self, ind, data):
        hv = ind.get("HistoricalVolatility", {})
        hv_val = hv.get("hv", pd.Series([0.2]))
        hv_pct = hv.get("hv_percentile", pd.Series([50]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        hv_value = hv_val.iloc[-1] if len(hv_val) > 0 else 0.2
        percentile = hv_pct.iloc[-1] if len(hv_pct) > 0 else 50
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        current_price = _get_current_price(data)
        
        if percentile > self.hv_percentile_high and rsi_val > 65:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="High volatility with overbought RSI", metadata={"type": "high_vol_sell"})
        elif percentile < self.hv_percentile_low and rsi_val < 35:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Low volatility with oversold RSI", metadata={"type": "low_vol_buy"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"hv_percentile": percentile})


@strategy(name="VolatilityRatio_Trend", type="composite",
    indicators=["VolatilityRatio", "ADX"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class VolatilityRatioTrend(BaseStrategy):
    """波動率比率趨勢"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        vol_ratio = ind.get("VolatilityRatio", {}).get("ratio", pd.Series([1.0]))
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        current_price = _get_current_price(data)
        
        if adx_val > 25:
            if plus_di.iloc[-1] > minus_di.iloc[-1] and vr > 0.8:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Trending expansion upward", metadata={"type": "trending_expansion"})
            elif minus_di.iloc[-1] > plus_di.iloc[-1] and vr > 0.8:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Trending expansion downward", metadata={"type": "trending_expansion"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"vol_ratio": vr, "adx": adx_val})


# ========== 策略 26-30: Momentum 系列 ==========

@strategy(name="Momentum_RateOfChange", type="composite",
    indicators=["Momentum", "RateOfChange"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class MomentumROC(BaseStrategy):
    """動量 + 變化率"""
    def __init__(self, threshold: float = 5.0):
        self.threshold = threshold
    
    def generate_signal(self, ind, data):
        momentum = ind.get("Momentum", {}).get("momentum", pd.Series([0]))
        roc = ind.get("RateOfChange", {}).get("roc", pd.Series([0]))
        
        mom_val = momentum.iloc[-1] if len(momentum) > 0 else 0
        roc_val = roc.iloc[-1] if len(roc) > 0 else 0
        current_price = _get_current_price(data)
        
        if mom_val > self.threshold and roc_val > self.threshold:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Strong positive momentum", metadata={"type": "strong_momentum_up"})
        elif mom_val < -self.threshold and roc_val < -self.threshold:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Strong negative momentum", metadata={"type": "strong_momentum_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"momentum": float(mom_val), "roc": float(roc_val)})


@strategy(name="Momentum_ADX_Strength", type="composite",
    indicators=["Momentum", "ADX"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class MomentumADXStrength(BaseStrategy):
    """動量 + ADX 強度"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        momentum = ind.get("Momentum", {}).get("momentum", pd.Series([0]))
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        
        mom_val = momentum.iloc[-1] if len(momentum) > 0 else 0
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        current_price = _get_current_price(data)
        
        if adx_val > self.adx_threshold:
            if plus_di.iloc[-1] > minus_di.iloc[-1] and mom_val > 0:
                return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Strong up momentum with ADX confirmation", metadata={"type": "strong_up_momentum"})
            elif minus_di.iloc[-1] > plus_di.iloc[-1] and mom_val < 0:
                return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Strong down momentum with ADX confirmation", metadata={"type": "strong_down_momentum"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"momentum": float(mom_val), "adx": adx_val})


@strategy(name="Momentum_Volume_Rally", type="composite",
    indicators=["Momentum", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class MomentumVolumeRally(BaseStrategy):
    """動量 + 成交量漲勢"""
    def __init__(self, mom_threshold: float = 2.0, vol_threshold: float = 1.3):
        self.mom_threshold = mom_threshold
        self.vol_threshold = vol_threshold
    
    def generate_signal(self, ind, data):
        momentum = ind.get("Momentum", {}).get("momentum", pd.Series([0]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        mom_val = momentum.iloc[-1] if len(momentum) > 0 else 0
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        current_price = _get_current_price(data)
        
        if mom_val > self.mom_threshold and vr > self.vol_threshold:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Momentum rally with volume confirmation", metadata={"type": "volume_rally"})
        elif mom_val < -self.mom_threshold and vr > self.vol_threshold:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Momentum selloff with volume confirmation", metadata={"type": "volume_selloff"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"momentum": float(mom_val), "vol_ratio": vr})


@strategy(name="Stochastic_Momentum", type="composite",
    indicators=["Stochastic", "Momentum"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class StochasticMomentumCombo(BaseStrategy):
    """隨機動量策略"""
    def __init__(self, stoch_overbought: float = 80, stoch_oversold: float = 20):
        self.stoch_overbought = stoch_overbought
        self.stoch_oversold = stoch_oversold
    
    def generate_signal(self, ind, data):
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        stoch_d = ind.get("Stochastic", {}).get("stoch_d", pd.Series([50]))
        momentum = ind.get("Momentum", {}).get("momentum", pd.Series([0]))
        
        k_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        d_val = stoch_d.iloc[-1] if len(stoch_d) > 0 else 50
        mom_val = momentum.iloc[-1] if len(momentum) > 0 else 0
        current_price = _get_current_price(data)
        
        k_above_d = k_val > d_val
        k_below_d = k_val < d_val
        
        if k_above_d and mom_val > 0 and k_val < 80:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Stochastic bullish with momentum", metadata={"type": "stoch_bullish"})
        elif k_below_d and mom_val < 0 and k_val > 20:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Stochastic bearish with momentum", metadata={"type": "stoch_bearish"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"k": k_val, "d": d_val, "mom": float(mom_val)})


@strategy(name="WilliamsR_Momentum", type="composite",
    indicators=["WilliamsR", "Momentum"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class WilliamsRMomentum(BaseStrategy):
    """Williams %R + 動量"""
    def __init__(self, williams_overbought: float = -20, williams_oversold: float = -80):
        self.williams_overbought = williams_overbought
        self.williams_oversold = williams_oversold
    
    def generate_signal(self, ind, data):
        williams = ind.get("WilliamsR", {}).get("williams_r", pd.Series([-50]))
        momentum = ind.get("Momentum", {}).get("momentum", pd.Series([0]))
        
        w_val = williams.iloc[-1] if len(williams) > 0 else -50
        mom_val = momentum.iloc[-1] if len(momentum) > 0 else 0
        current_price = _get_current_price(data)
        
        if w_val < self.williams_oversold and mom_val > 0:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Williams %R oversold with positive momentum", metadata={"type": "oversold_recovery"})
        elif w_val > self.williams_overbought and mom_val < 0:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Williams %R overbought with negative momentum", metadata={"type": "overbought_decline"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"williams": float(w_val), "momentum": float(mom_val)})
