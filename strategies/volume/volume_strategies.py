"""成交量策略模組"""
import pandas as pd
from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


@strategy(name="VolumeMA_Crossover", type="trend_following",
    indicators=["Volume", "SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class VolumeMACrossover(BaseStrategy):
    """成交量 MA 交叉策略 - 放量突破"""
    def __init__(self,
                 vol_period: int = 20,
                 price_period: int = 50,
                 vol_multiplier: float = 2.0,
                 take_profit: float = 0.12,
                 stop_loss: float = 0.08,
                 max_holding_days: int = 20):
        self.vol_period = vol_period
        self.price_period = price_period
        self.vol_multiplier = vol_multiplier
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        volume = data["Volume"]
        current_price = _get_current_price(data)
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        if len(volume) < self.vol_period + 1:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 成交量 MA
        vol_ma = volume.rolling(self.vol_period).mean()
        vol_current = volume.iloc[-1]
        vol_prev = volume.iloc[-2] if len(volume) > 1 else vol_current
        
        # 價格趨勢
        sma = close.rolling(self.price_period).mean()
        
        # 放量條件
        is_volume_surge = vol_current > vol_ma.iloc[-1] * self.vol_multiplier
        
        if len(sma) < 2:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 放量上漲 (做多)
        if is_volume_surge and close.iloc[-1] > sma.iloc[-1]:
            confidence = min(0.6 + (vol_current / vol_ma.iloc[-1] - 1) * 0.1, 0.85)
            return SignalResult(signal="LONG", confidence=confidence, price=current_price,
                reason=f"Volume Surge (+{(vol_current/vol_ma.iloc[-1]-1)*100:.0f}%)", metadata={"vol_ratio": vol_current/vol_ma.iloc[-1]})
        
        # 放量下跌 (做空)
        if is_volume_surge and close.iloc[-1] < sma.iloc[-1]:
            confidence = min(0.6 + (vol_current / vol_ma.iloc[-1] - 1) * 0.1, 0.85)
            return SignalResult(signal="SHORT", confidence=confidence, price=current_price,
                reason=f"Volume Surge Down (+{(vol_current/vol_ma.iloc[-1]-1)*100:.0f}%)", metadata={"vol_ratio": vol_current/vol_ma.iloc[-1]})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


@strategy(name="OBV_Divergence", type="momentum",
    indicators=["OBV", "Close"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"])
class OBVDivergence(BaseStrategy):
    """OBV 背離策略 - 量價背離"""
    def __init__(self,
                 obv_period: int = 14,
                 lookback: int = 10,
                 take_profit: float = 0.10,
                 stop_loss: float = 0.07,
                 max_holding_days: int = 15):
        self.obv_period = obv_period
        self.lookback = lookback
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        # 計算 OBV
        obv = (pd.Series(1) * 0).iloc[:0]
        if "Volume" in data.columns:
            volume = data["Volume"]
            close_diff = close.diff()
            obv = pd.Series(0, index=close.index)
            for i in range(1, len(close)):
                if close_diff.iloc[i] > 0:
                    obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
                elif close_diff.iloc[i] < 0:
                    obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
                else:
                    obv.iloc[i] = obv.iloc[i-1]
        else:
            obv = close * 0
        
        current_price = _get_current_price(data)
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        if len(close) < self.lookback + 1:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 計算價格和 OBV 的趨勢
        price_trend = close.iloc[-1] - close.iloc[-self.lookback]
        obv_trend = obv.iloc[-1] - obv.iloc[-self.lookback]
        
        # 正背離：價格新低但 OBV 沒新低 (做多)
        if close.iloc[-1] < close.iloc[-self.lookback:].min() and obv.iloc[-1] > obv.iloc[-self.lookback:].min():
            confidence = min(0.65 + abs(obv_trend) / abs(price_trend + 1) * 0.1, 0.85)
            return SignalResult(signal="LONG", confidence=confidence, price=current_price,
                reason="OBV Bullish Divergence", metadata={"obv_trend": obv_trend})
        
        # 負背離：價格新高但 OBV 沒新高 (做空)
        if close.iloc[-1] > close.iloc[-self.lookback:].max() and obv.iloc[-1] < obv.iloc[-self.lookback:].max():
            confidence = min(0.65 + abs(obv_trend) / abs(price_trend + 1) * 0.1, 0.85)
            return SignalResult(signal="SHORT", confidence=confidence, price=current_price,
                reason="OBV Bearish Divergence", metadata={"obv_trend": obv_trend})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


@strategy(name="VWAP_Reversion", type="mean_reversion",
    indicators=["VWAP", "Close"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"])
class VWAPReversion(BaseStrategy):
    """VWAP 回歸策略 - 價格偏離均值回歸"""
    def __init__(self,
                 vwap_period: int = 14,
                 deviation_threshold: float = 0.02,
                 take_profit: float = 0.08,
                 stop_loss: float = 0.05,
                 max_holding_days: int = 10):
        self.vwap_period = vwap_period
        self.deviation_threshold = deviation_threshold
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        high = data["High"]
        low = data["Low"]
        volume = data.get("Volume", pd.Series(1, index=close.index))
        current_price = _get_current_price(data)
        
        # 計算 VWAP
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        vwap = vwap.rolling(self.vwap_period).mean() if len(vwap) > self.vwap_period else vwap
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        if len(vwap) < 2:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        vwap_val = vwap.iloc[-1]
        deviation = (current_price - vwap_val) / vwap_val
        
        # 價格低於 VWAP 超過閾值 (做多)
        if deviation < -self.deviation_threshold:
            confidence = min(0.6 + abs(deviation) * 10, 0.85)
            return SignalResult(signal="LONG", confidence=confidence, price=current_price,
                reason=f"Below VWAP ({deviation*100:.1f}%)", metadata={"deviation": deviation})
        
        # 價格高於 VWAP 超過閾值 (做空)
        if deviation > self.deviation_threshold:
            confidence = min(0.6 + abs(deviation) * 10, 0.85)
            return SignalResult(signal="SHORT", confidence=confidence, price=current_price,
                reason=f"Above VWAP ({deviation*100:.1f}%)", metadata={"deviation": deviation})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Near VWAP")


@strategy(name="VolumePrice_Confirm", type="trend_following",
    indicators=["Volume", "Close", "SMA_20"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class VolumePriceConfirm(BaseStrategy):
    """量價確認策略 - 價漲量增"""
    def __init__(self,
                 vol_period: int = 20,
                 price_period: int = 20,
                 take_profit: float = 0.15,
                 stop_loss: float = 0.10,
                 max_holding_days: int = 25):
        self.vol_period = vol_period
        self.price_period = price_period
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        volume = data["Volume"]
        current_price = _get_current_price(data)
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        if len(close) < self.price_period + 2:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 價格趨勢
        sma = close.rolling(self.price_period).mean()
        price_up = close.iloc[-1] > close.iloc[-2] > sma.iloc[-1]
        price_down = close.iloc[-1] < close.iloc[-2] < sma.iloc[-1]
        
        # 成交量趨勢
        vol_ma = volume.rolling(self.vol_period).mean()
        vol_up = volume.iloc[-1] > volume.iloc[-2] and volume.iloc[-1] > vol_ma.iloc[-1]
        vol_down = volume.iloc[-1] < volume.iloc[-2] and volume.iloc[-1] < vol_ma.iloc[-1]
        
        # 價漲量增 (做多)
        if price_up and vol_up:
            return SignalResult(signal="LONG", confidence=0.75, price=current_price,
                reason="Volume Price Confirmation (Bull)", metadata={"type": "confirmation"})
        
        # 價跌量增 (做空)
        if price_down and vol_down:
            return SignalResult(signal="SHORT", confidence=0.75, price=current_price,
                reason="Volume Price Confirmation (Bear)", metadata={"type": "confirmation"})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No confirmation")
