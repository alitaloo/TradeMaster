# 複合策略集 #3 - Advanced Combinations & Special Strategies (策略 31-50)
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


# ========== 策略 31-40: Advanced Technical Combinations ==========

@strategy(name="Triple_Indicator_Confirm", type="composite",
    indicators=["RSI", "MACD", "Stochastic"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class TripleIndicatorConfirm(BaseStrategy):
    """三重指標確認"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        signal = ind.get("MACD", {}).get("signal", pd.Series([0]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        sig_val = signal.iloc[-1] if len(signal) > 0 else 0
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        current_price = _get_current_price(data)
        
        long_confirm = (rsi_val > 50) and (macd_val > sig_val) and (stoch_val > 50)
        short_confirm = (rsi_val < 50) and (macd_val < sig_val) and (stoch_val < 50)
        
        if long_confirm:
            return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Triple indicator bullish confirmation", metadata={"type": "triple_confirm_up"})
        elif short_confirm:
            return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Triple indicator bearish confirmation", metadata={"type": "triple_confirm_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val, "stoch": stoch_val})


@strategy(name="Trend_Volume_Alignment", type="composite",
    indicators=["SMA", "EMA", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class TrendVolumeAlignment(BaseStrategy):
    """趨勢成交量對齊"""
    def __init__(self, sma_period: int = 50):
        self.sma_period = sma_period
    
    def generate_signal(self, ind, data):
        sma = ind.get("SMA", {}).get("sma", pd.Series([0]))
        ema = ind.get("EMA", {}).get("ema", pd.Series([0]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        sma_val = sma.iloc[-1] if len(sma) > 0 else 0
        ema_val = ema.iloc[-1] if len(ema) > 0 else 0
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        current_price = _get_current_price(data)
        
        close = data["Close"].iloc[-1]
        trend_aligned = (sma_val > ema_val) and (close > ema_val)
        down_trend = (sma_val < ema_val) and (close < ema_val)
        
        if trend_aligned and vr > 1.1:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Trend aligned upward with volume", metadata={"type": "aligned_uptrend"})
        elif down_trend and vr > 1.1:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Trend aligned downward with volume", metadata={"type": "aligned_downtrend"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"vol_ratio": vr})


@strategy(name="Oversold_Bounce", type="composite",
    indicators=["RSI", "Stochastic", "WilliamsR", "CCI"],
    signals=["LONG", "HOLD"],
    market_regimes=["neutral", "volatile"])
class OversoldBounce(BaseStrategy):
    """超賣反彈策略 - 添加止盈止損"""
    def __init__(self, 
                 take_profit: float = 0.12,      # 12% 止盈
                 stop_loss: float = 0.08,        # 8% 止損
                 max_holding_days: int = 15):     # 最多持倉 15 天
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        williams = ind.get("WilliamsR", {}).get("williams_r", pd.Series([-50]))
        cci = ind.get("CCI", {}).get("cci", pd.Series([0]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        w_val = williams.iloc[-1] if len(williams) > 0 else -50
        cci_val = cci.iloc[-1] if len(cci) > 0 else 0
        current_price = _get_current_price(data)
        
        # 持倉檢查
        close = data["Close"]
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            # 止盈檢查
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            
            # 止損檢查
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            
            # 時間退出
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        # 入場訊號
        oversold_count = 0
        if rsi_val < 30: oversold_count += 1
        if stoch_val < 20: oversold_count += 1
        if w_val < -80: oversold_count += 1
        if cci_val < -100: oversold_count += 1
        
        if oversold_count >= 2:
            return SignalResult(signal="LONG", confidence=0.7 + oversold_count * 0.1, price=current_price,
                reason=f"Multiple oversold indicators ({oversold_count})", metadata={"oversold_count": oversold_count})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price,
            reason="Hold position", metadata={"oversold_count": oversold_count})


@strategy(name="Overbought_Decline", type="composite",
    indicators=["RSI", "Stochastic", "WilliamsR", "CCI"],
    signals=["SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"])
class OverboughtDecline(BaseStrategy):
    """超買回落策略 - 添加止盈止損"""
    def __init__(self,
                 take_profit: float = 0.12,      # 12% 止盈
                 stop_loss: float = 0.08,        # 8% 止損
                 max_holding_days: int = 15):     # 最多持倉 15 天
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        williams = ind.get("WilliamsR", {}).get("williams_r", pd.Series([-50]))
        cci = ind.get("CCI", {}).get("cci", pd.Series([0]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        w_val = williams.iloc[-1] if len(williams) > 0 else -50
        cci_val = cci.iloc[-1] if len(cci) > 0 else 0
        current_price = _get_current_price(data)
        
        # 持倉檢查
        close = data["Close"]
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            # 做空止盈（價格下跌 = 獲利）
            if price_change <= -self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit SHORT ({price_change*100:.1f}%)", metadata={"type": "take_profit"})
            
            # 做空止損（價格上漲 = 虧損）
            if price_change >= self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss SHORT ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            
            # 時間退出
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        # 入場訊號
        overbought_count = 0
        if rsi_val > 70: overbought_count += 1
        if stoch_val > 80: overbought_count += 1
        if w_val > -20: overbought_count += 1
        if cci_val > 100: overbought_count += 1
        
        if overbought_count >= 2:
            return SignalResult(signal="SHORT", confidence=0.7 + overbought_count * 0.1, price=current_price,
                reason=f"Multiple overbought indicators ({overbought_count})", metadata={"overbought_count": overbought_count})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price,
            reason="Hold position", metadata={"overbought_count": overbought_count})
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        w_val = williams.iloc[-1] if len(williams) > 0 else -50
        cci_val = cci.iloc[-1] if len(cci) > 0 else 0
        current_price = _get_current_price(data)
        
        overbought_count = 0
        if rsi_val > 70: overbought_count += 1
        if stoch_val > 80: overbought_count += 1
        if w_val > -20: overbought_count += 1
        if cci_val > 100: overbought_count += 1
        
        if overbought_count >= 2:
            return SignalResult(signal="SHORT", confidence=0.7 + overbought_count * 0.1, price=_get_current_price(data), reason="Multiple overbought indicators", metadata={"overbought_count": overbought_count})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"overbought_count": overbought_count})


@strategy(name="ADX_DI_Crossover", type="composite",
    indicators=["ADX", "Stochastic"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class ADXDI(BaseStrategy):
    """ADX DI 交叉策略"""
    def __init__(self, adx_threshold: float = 20):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        di_plus = plus_di.iloc[-1] if len(plus_di) > 0 else 20
        di_minus = minus_di.iloc[-1] if len(minus_di) > 0 else 20
        current_price = _get_current_price(data)
        
        if adx_val > self.adx_threshold:
            if di_plus > di_minus and stoch_val < 70:
                return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="DI+ crossing above DI-", metadata={"type": "di_plus_up"})
            elif di_minus > di_plus and stoch_val > 30:
                return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="DI- crossing above DI+", metadata={"type": "di_minus_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val, "stoch": stoch_val})


@strategy(name="Bollinger_Mean_Reversion", type="composite",
    indicators=["BollingerBands", "CCI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class BollingerMeanReversion(BaseStrategy):
    """布林帶均值回歸"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        bb = ind.get("BollingerBands", {})
        percent = bb.get("percent", pd.Series([0.5]))
        cci = ind.get("CCI", {}).get("cci", pd.Series([0]))
        
        bb_pct = percent.iloc[-1] if len(percent) > 0 else 0.5
        cci_val = cci.iloc[-1] if len(cci) > 0 else 0
        current_price = _get_current_price(data)
        
        if bb_pct < 0.1 and cci_val < -100:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="BB oversold with CCI confirmation", metadata={"type": "bb_oversold_cci"})
        elif bb_pct > 0.9 and cci_val > 100:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="BB overbought with CCI confirmation", metadata={"type": "bb_overbought_cci"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"bb_percent": bb_pct, "cci": cci_val})


@strategy(name="MACD_Zero_Cross", type="composite",
    indicators=["MACD", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class MACDZeroCross(BaseStrategy):
    """MACD 零軸交叉"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        macd = ind.get("MACD", {}).get("macd", pd.Series([0]))
        hist = ind.get("MACD", {}).get("histogram", pd.Series([0]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        macd_val = macd.iloc[-1] if len(macd) > 0 else 0
        macd_prev = macd.iloc[-2] if len(macd) > 1 else macd_val
        hist_val = hist.iloc[-1] if len(hist) > 0 else 0
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        current_price = _get_current_price(data)
        
        zero_cross_up = (macd_prev < 0) and (macd_val > 0)
        zero_cross_down = (macd_prev > 0) and (macd_val < 0)
        
        if zero_cross_up and vr > 1.2:
            return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="MACD zero line bullish cross", metadata={"type": "zero_cross_up"})
        elif zero_cross_down and vr > 1.2:
            return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="MACD zero line bearish cross", metadata={"type": "zero_cross_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"macd": macd_val, "vol": vr})


@strategy(name="Stochastic_RSI_Oscillator", type="composite",
    indicators=["Stochastic", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class StochasticRSIOscillator(BaseStrategy):
    """隨機 RSI 振盪器"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        current_price = _get_current_price(data)
        
        if stoch_val < 20 and rsi_val < 30:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Both Stochastic and RSI oversold", metadata={"type": "double_oversold"})
        elif stoch_val > 80 and rsi_val > 70:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Both Stochastic and RSI overbought", metadata={"type": "double_overbought"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"stoch": stoch_val, "rsi": rsi_val})


@strategy(name="Trend_Filter_RSI", type="composite",
    indicators=["SMA", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "neutral"])
class TrendFilterRSI(BaseStrategy):
    """趨勢過濾 RSI"""
    def __init__(self, sma_period: int = 200):
        self.sma_period = sma_period
    
    def generate_signal(self, ind, data):
        sma = ind.get("SMA", {}).get("sma", pd.Series([0]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        sma_val = sma.iloc[-1] if len(sma) > 0 else 0
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        current_price = _get_current_price(data)
        
        close = data["Close"].iloc[-1]
        above_sma = close > sma_val
        below_sma = close < sma_val
        
        if above_sma and rsi_val < 50:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Pullback buy in uptrend", metadata={"type": "pullback_buy"})
        elif below_sma and rsi_val > 50:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Pullback sell in downtrend", metadata={"type": "pullback_sell"})
        elif above_sma and rsi_val > 70:
            return SignalResult(signal="LONG", confidence=0.7, price=_get_current_price(data), reason="Trend continuation bullish", metadata={"type": "trend_continuation"})
        elif below_sma and rsi_val < 30:
            return SignalResult(signal="SHORT", confidence=0.7, price=_get_current_price(data), reason="Trend continuation bearish", metadata={"type": "trend_continuation"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"above_sma": above_sma, "rsi": rsi_val})


@strategy(name="Volume_Trend_Divergence", type="composite",
    indicators=["VolumeEMA", "MACD"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class VolumeTrendDivergence(BaseStrategy):
    """成交量趨勢背離"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        macd = ind.get("MACD", {}).get("histogram", pd.Series([0]))
        
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        hist = macd.iloc[-1] if len(macd) > 0 else 0
        hist_prev = macd.iloc[-3] if len(macd) > 3 else hist
        current_price = _get_current_price(data)
        
        close = data["Close"].iloc[-1]
        close_prev = data["Close"].iloc[-3] if len(data["Close"]) > 3 else close
        price_up = close > close_prev
        
        if vr > 1.3 and hist < hist_prev and price_up:
            return SignalResult(signal="SHORT", confidence=0.75, price=_get_current_price(data), reason="Volume increase with weakening momentum", metadata={"type": "weakening_up"})
        elif vr > 1.3 and hist > hist_prev and not price_up:
            return SignalResult(signal="LONG", confidence=0.75, price=_get_current_price(data), reason="Volume increase with weakening downside momentum", metadata={"type": "weakening_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"vol_ratio": vr})


# ========== 策略 41-50: Specialized Strategies ==========

@strategy(name="Opening_Gap", type="composite",
    indicators=["RSI", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["volatile"])
class OpeningGap(BaseStrategy):
    """開盤缺口策略"""
    def __init__(self, gap_threshold: float = 0.02):
        self.gap_threshold = gap_threshold
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        current_price = _get_current_price(data)
        
        if rsi_val < 30 and vr > 1.5:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Gap fill opportunity oversold", metadata={"type": "gap_fill"})
        elif rsi_val > 70 and vr > 1.5:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Gap fill opportunity overbought", metadata={"type": "gap_fill"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val})


@strategy(name="End_of_Day_Reversion", type="composite",
    indicators=["RSI", "Stochastic"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class EndOfDayReversion(BaseStrategy):
    """日終均值回歸"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        stoch_k = ind.get("Stochastic", {}).get("stoch_k", pd.Series([50]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        stoch_val = stoch_k.iloc[-1] if len(stoch_k) > 0 else 50
        current_price = _get_current_price(data)
        
        if rsi_val < 25 and stoch_val < 15:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="EOD oversold bounce", metadata={"type": "eod_oversold"})
        elif rsi_val > 75 and stoch_val > 85:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="EOD overbought decline", metadata={"type": "eod_overbought"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val, "stoch": stoch_val})


@strategy(name="Trend_Pullback", type="composite",
    indicators=["ADX", "RSI", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class TrendPullback(BaseStrategy):
    """趨勢回調策略"""
    def __init__(self, adx_threshold: float = 25):
        self.adx_threshold = adx_threshold
    
    def generate_signal(self, ind, data):
        adx = ind.get("ADX", {}).get("adx", pd.Series([15]))
        plus_di = ind.get("ADX", {}).get("plus_di", pd.Series([20]))
        minus_di = ind.get("ADX", {}).get("minus_di", pd.Series([20]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        adx_val = adx.iloc[-1] if len(adx) > 0 else 15
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        current_price = _get_current_price(data)
        
        if adx_val > self.adx_threshold:
            if plus_di.iloc[-1] > minus_di.iloc[-1] and rsi_val < 45:
                return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Uptrend pullback buy", metadata={"type": "uptrend_pullback"})
            elif minus_di.iloc[-1] > plus_di.iloc[-1] and rsi_val > 55:
                return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Downtrend pullback sell", metadata={"type": "downtrend_pullback"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"adx": adx_val, "rsi": rsi_val})


@strategy(name="Momentum_Exhaustion", type="composite",
    indicators=["Momentum", "RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class MomentumExhaustion(BaseStrategy):
    """動量衰竭策略"""
    def __init__(self, mom_threshold: float = 10.0):
        self.mom_threshold = mom_threshold
    
    def generate_signal(self, ind, data):
        momentum = ind.get("Momentum", {}).get("momentum", pd.Series([0]))
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        
        mom_val = momentum.iloc[-1] if len(momentum) > 0 else 0
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        mom_prev = momentum.iloc[-3] if len(momentum) > 3 else mom_val
        current_price = _get_current_price(data)
        
        mom_fading = abs(mom_val) < abs(mom_prev)
        
        if rsi_val > 70 and mom_fading and mom_val > 0:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Bullish momentum exhaustion", metadata={"type": "bullish_exhaustion"})
        elif rsi_val < 30 and mom_fading and mom_val < 0:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Bearish momentum exhaustion", metadata={"type": "bearish_exhaustion"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"momentum": float(mom_val), "rsi": rsi_val})


@strategy(name="Volatility_Contraction", type="composite",
    indicators=["BollingerBands", "ATR", "VolumeEMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class VolatilityContraction(BaseStrategy):
    """波動率收縮策略"""
    def __init__(self, bb_width_threshold: float = 0.08):
        self.bb_width_threshold = bb_width_threshold
    
    def generate_signal(self, ind, data):
        bb = ind.get("BollingerBands", {})
        upper = bb.get("upper", pd.Series([0]))
        lower = bb.get("lower", pd.Series([0]))
        middle = bb.get("middle", pd.Series([0]))
        vol_ratio = ind.get("VolumeEMA", {}).get("volume_ratio", pd.Series([1.0]))
        
        bb_width = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1] if len(middle) > 0 else 0.1
        vr = vol_ratio.iloc[-1] if len(vol_ratio) > 0 else 1.0
        current_price = _get_current_price(data)
        
        close = data["Close"].iloc[-1]
        
        if bb_width < self.bb_width_threshold and vr < 0.8:
            if close > middle.iloc[-1]:
                return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Volatility contraction breakout up", metadata={"type": "contraction_breakout"})
            else:
                return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Volatility contraction breakdown", metadata={"type": "contraction_breakdown"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"bb_width": bb_width, "vol_ratio": vr})


@strategy(name="RSI_Divergence", type="composite",
    indicators=["RSI", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class RSIDivergence(BaseStrategy):
    """RSI 背離策略"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        close = data["Close"]
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        rsi_prev = rsi.iloc[-10] if len(rsi) > 10 else rsi_val
        close_val = close.iloc[-1] if len(close) > 0 else 0
        close_prev = close.iloc[-10] if len(close) > 10 else close_val
        current_price = _get_current_price(data)
        
        price_new_high = close_val > close_prev
        rsi_not_new_high = rsi_val < rsi_prev
        price_new_low = close_val < close_prev
        rsi_not_new_low = rsi_val > rsi_prev
        
        if price_new_high and rsi_not_new_high:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="Bearish divergence detected", metadata={"type": "bearish_divergence"})
        elif price_new_low and rsi_not_new_low:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="Bullish divergence detected", metadata={"type": "bullish_divergence"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"rsi": rsi_val})


@strategy(name="Dual_Moving_Average_Crossover", type="composite",
    indicators=["SMA", "EMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class DualMACrossover(BaseStrategy):
    """雙均線交叉策略"""
    def __init__(self, short_period: int = 10, long_period: int = 30):
        self.short_period = short_period
        self.long_period = long_period
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        sma_short = close.rolling(self.short_period).mean()
        sma_long = close.rolling(self.long_period).mean()
        
        short_val = sma_short.iloc[-1] if len(sma_short) > 0 else 0
        long_val = sma_long.iloc[-1] if len(sma_long) > 0 else 0
        short_prev = sma_short.iloc[-2] if len(sma_short) > 1 else short_val
        long_prev = sma_long.iloc[-2] if len(sma_long) > 1 else long_val
        current_price = _get_current_price(data)
        
        golden_cross = (short_prev <= long_prev) and (short_val > long_val)
        death_cross = (short_prev >= long_prev) and (short_val < long_val)
        
        if golden_cross:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Golden cross detected", metadata={"type": "golden_cross"})
        elif death_cross:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Death cross detected", metadata={"type": "death_cross"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"above": short_val > long_val})


@strategy(name="Three_MA_Trend", type="composite",
    indicators=["SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class ThreeMATrend(BaseStrategy):
    """三均線趨勢策略"""
    def __init__(self, short: int = 10, mid: int = 30, long: int = 50):
        self.short = short
        self.mid = mid
        self.long = long
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        ma_short = close.rolling(self.short).mean().iloc[-1]
        ma_mid = close.rolling(self.mid).mean().iloc[-1]
        ma_long = close.rolling(self.long).mean().iloc[-1]
        current_price = _get_current_price(data)
        
        aligned_up = (ma_short > ma_mid) and (ma_mid > ma_long)
        aligned_down = (ma_short < ma_mid) and (ma_mid < ma_long)
        
        if aligned_up:
            return SignalResult(signal="LONG", confidence=0.9, price=_get_current_price(data), reason="Triple MA aligned upward", metadata={"type": "aligned_up"})
        elif aligned_down:
            return SignalResult(signal="SHORT", confidence=0.9, price=_get_current_price(data), reason="Triple MA aligned downward", metadata={"type": "aligned_down"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"aligned": aligned_up or aligned_down})


@strategy(name="RSI_SMA_Strategy", type="composite",
    indicators=["RSI", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"])
class RSISMAStrategy(BaseStrategy):
    """RSI + SMA 策略"""
    def __init__(self, rsi_period: int = 14, sma_period: int = 50):
        self.rsi_period = rsi_period
        self.sma_period = sma_period
    
    def generate_signal(self, ind, data):
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        sma = ind.get("SMA", {}).get("sma", pd.Series([0]))
        
        rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
        sma_val = sma.iloc[-1] if len(sma) > 0 else 0
        current_price = _get_current_price(data)
        
        close = data["Close"].iloc[-1]
        above_sma = close > sma_val
        
        if above_sma and rsi_val < 40:
            return SignalResult(signal="LONG", confidence=0.85, price=_get_current_price(data), reason="Above SMA with oversold RSI", metadata={"type": "above_sma_oversold"})
        elif not above_sma and rsi_val > 60:
            return SignalResult(signal="SHORT", confidence=0.85, price=_get_current_price(data), reason="Below SMA with overbought RSI", metadata={"type": "below_sma_overbought"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"above_sma": above_sma, "rsi": rsi_val})


@strategy(name="CCI_Mean_Reversion", type="composite",
    indicators=["CCI", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral"])
class CCIMeanReversion(BaseStrategy):
    """CCI 均值回歸"""
    def __init__(self):
        pass
    
    def generate_signal(self, ind, data):
        cci = ind.get("CCI", {}).get("cci", pd.Series([0]))
        sma = ind.get("SMA", {}).get("sma", pd.Series([0]))
        
        cci_val = cci.iloc[-1] if len(cci) > 0 else 0
        sma_val = sma.iloc[-1] if len(sma) > 0 else 0
        current_price = _get_current_price(data)
        
        close = data["Close"].iloc[-1]
        above_sma = close > sma_val
        
        below_sma = close < sma_val
        if cci_val < -100 and below_sma:
            return SignalResult(signal="LONG", confidence=0.8, price=_get_current_price(data), reason="CCI oversold with price below SMA", metadata={"type": "cci_oversold"})
        elif cci_val > 100 and above_sma:
            return SignalResult(signal="SHORT", confidence=0.8, price=_get_current_price(data), reason="CCI overbought with price above SMA", metadata={"type": "cci_overbought"})
        return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"cci": cci_val, "sma": sma_val})