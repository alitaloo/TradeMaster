"""新策略模組 - 簡單有效的交易策略"""
import pandas as pd
from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


@strategy(name="SimpleMA_Crossover", type="trend_following",
    indicators=["SMA"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class SimpleMACrossover(BaseStrategy):
    """簡單 MA 交叉策略 - 50/200 黃金交叉/死叉"""
    def __init__(self,
                 fast_period: int = 50,
                 slow_period: int = 200,
                 take_profit: float = 0.15,
                 stop_loss: float = 0.10,
                 max_holding_days: int = 30):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        sma_fast = close.rolling(self.fast_period).mean()
        sma_slow = close.rolling(self.slow_period).mean()
        
        current_price = _get_current_price(data)
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            # 止盈/止損/時間退出
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            if price_change <= -self.stop_loss:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Stop loss ({price_change*100:.1f}%)", metadata={"type": "stop_loss"})
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        # MA 交叉訊號
        if len(sma_fast) < 2 or len(sma_slow) < 2:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        prev_fast = sma_fast.iloc[-2]
        prev_slow = sma_slow.iloc[-2]
        curr_fast = sma_fast.iloc[-1]
        curr_slow = sma_slow.iloc[-1]
        
        # 黃金交叉 (做多)
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return SignalResult(signal="LONG", confidence=0.75, price=current_price,
                reason=f"Golden Cross ({self.fast_period}/{self.slow_period})", metadata={"type": "golden_cross"})
        
        # 死叉 (做空)
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return SignalResult(signal="SHORT", confidence=0.75, price=current_price,
                reason=f"Death Cross ({self.fast_period}/{self.slow_period})", metadata={"type": "death_cross"})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


@strategy(name="PriceBreakout", type="trend_following",
    indicators=["High", "Low"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"])
class PriceBreakout(BaseStrategy):
    """價格突破策略 - 突破 N 日高點/低點"""
    def __init__(self,
                 period: int = 20,
                 take_profit: float = 0.12,
                 stop_loss: float = 0.08,
                 max_holding_days: int = 20):
        self.period = period
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        high = data["High"]
        low = data["Low"]
        close = data["Close"]
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
        
        if len(high) < self.period + 1:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 計算 N 日高點/低點
        rolling_high = high.rolling(self.period).max()
        rolling_low = low.rolling(self.period).min()
        
        prev_high = rolling_high.iloc[-2]
        prev_low = rolling_low.iloc[-2]
        curr_high = rolling_high.iloc[-1]
        curr_low = rolling_low.iloc[-1]
        
        # 突破高點 (做多)
        if prev_high < curr_high and close.iloc[-1] >= curr_high:
            return SignalResult(signal="LONG", confidence=0.7, price=current_price,
                reason=f"Breakout High ({self.period} days)", metadata={"type": "high_breakout"})
        
        # 跌破低點 (做空)
        if prev_low > curr_low and close.iloc[-1] <= curr_low:
            return SignalResult(signal="SHORT", confidence=0.7, price=current_price,
                reason=f"Breakout Low ({self.period} days)", metadata={"type": "low_breakout"})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


@strategy(name="VIXReversal", type="mean_reversion",
    indicators=["Close"],
    signals=["LONG", "HOLD"],
    market_regimes=["volatile"])
class VIXReversal(BaseStrategy):
    """VIX 反轉策略 - 高波動時入場抄底"""
    def __init__(self,
                 vix_threshold: float = 25.0,
                 lookback_days: int = 5,
                 take_profit: float = 0.08,
                 stop_loss: float = 0.05,
                 max_holding_days: int = 10):
        self.vix_threshold = vix_threshold
        self.lookback_days = lookback_days
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
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
        
        if len(close) < self.lookback_days + 1:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 計算波動率指標（如果沒有 VIX）
        volatility = close.pct_change().rolling(20).std() * (252 ** 0.5) * 100
        vix_val = volatility.iloc[-1]
        
        rolling_low = close.rolling(self.lookback_days).min()
        is_new_low = close.iloc[-1] <= rolling_low.iloc[-1]
        
        if vix_val > self.vix_threshold and is_new_low:
            confidence = min(0.6 + (vix_val - self.vix_threshold) * 0.02, 0.85)
            return SignalResult(signal="LONG", confidence=confidence, price=current_price,
                reason=f"VIX Reversal (VIX={vix_val:.1f})", metadata={"vix": vix_val, "type": "vix_reversal"})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


@strategy(name="ATRTrailingStop", type="trend_following",
    indicators=["ATR"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"])
class ATRTrailingStop(BaseStrategy):
    """ATR 移動止損策略 - 趨勢追蹤"""
    def __init__(self,
                 atr_period: int = 14,
                 atr_multiplier: float = 2.0,
                 sma_period: int = 50,
                 take_profit: float = 0.20,
                 max_holding_days: int = 40):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.sma_period = sma_period
        self.take_profit = take_profit
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        atr = ind.get("ATR", pd.Series([0]))
        if isinstance(atr, pd.Series) and len(atr) > 0:
            atr_val = atr.iloc[-1]
        else:
            atr_val = close.std()
        
        sma = close.rolling(self.sma_period).mean()
        current_price = _get_current_price(data)
        
        # 持倉檢查
        prices = close.iloc[-self.max_holding_days:].tolist() if len(close) >= self.max_holding_days else close.tolist()
        
        if len(prices) >= 2:
            entry_price = prices[0]
            price_change = (current_price - entry_price) / entry_price
            holding_days = len(prices) - 1
            
            # 止盈
            if price_change >= self.take_profit:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Take profit (+{price_change*100:.1f}%)", metadata={"type": "take_profit"})
            
            # 時間退出
            if holding_days >= self.max_holding_days:
                return SignalResult(signal="HOLD", confidence=0.5, price=current_price,
                    reason=f"Time exit ({holding_days} days)", metadata={"type": "time_exit"})
        
        if len(sma) < 2:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 趨勢判斷
        trend_up = current_price > sma.iloc[-1]
        trend_down = current_price < sma.iloc[-1]
        
        # 計算移動止損位
        trailing_stop_long = current_price - atr_val * self.atr_multiplier
        trailing_stop_short = current_price + atr_val * self.atr_multiplier
        
        prev_close = close.iloc[-2]
        
        # 做多
        if trend_up and prev_close > trailing_stop_long:
            return SignalResult(signal="LONG", confidence=0.7, price=current_price,
                reason="ATR Long Trail", metadata={"atr": atr_val, "stop": trailing_stop_long})
        
        # 做空
        if trend_down and prev_close < trailing_stop_short:
            return SignalResult(signal="SHORT", confidence=0.7, price=current_price,
                reason="ATR Short Trail", metadata={"atr": atr_val, "stop": trailing_stop_short})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")


@strategy(name="DualMomentum", type="momentum",
    indicators=["RSI", "ROC"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "neutral"])
class DualMomentum(BaseStrategy):
    """雙重動量策略 - 相對強度 + 絕對動量"""
    def __init__(self,
                 rsi_period: int = 14,
                 rsi_oversold: float = 35,
                 rsi_overbought: float = 65,
                 roc_period: int = 10,
                 roc_threshold: float = 2.0,
                 take_profit: float = 0.12,
                 stop_loss: float = 0.08,
                 max_holding_days: int = 20):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.roc_period = roc_period
        self.roc_threshold = roc_threshold
        self.take_profit = take_profit
        self.stop_loss = stop_loss
        self.max_holding_days = max_holding_days
    
    def generate_signal(self, ind, data):
        close = data["Close"]
        rsi = ind.get("RSI", {}).get("rsi", pd.Series([50]))
        if isinstance(rsi, pd.Series) and len(rsi) > 0:
            rsi_val = rsi.iloc[-1]
        else:
            rsi_val = 50
        
        # 計算 ROC
        roc = close.pct_change(self.roc_period) * 100
        roc_val = roc.iloc[-1]
        
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
        
        if len(close) < self.rsi_period + self.roc_period + 1:
            return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="Insufficient data")
        
        # 做多：RSI 偏多 + ROC 為正
        if rsi_val > self.rsi_oversold and roc_val > self.roc_threshold:
            confidence = min(0.6 + (rsi_val - self.rsi_oversold) * 0.02 + abs(roc_val) * 0.05, 0.85)
            return SignalResult(signal="LONG", confidence=confidence, price=current_price,
                reason=f"Dual Momentum LONG (RSI={rsi_val:.1f}, ROC={roc_val:.1f})", 
                metadata={"rsi": rsi_val, "roc": roc_val, "type": "bullish"})
        
        # 做空：RSI 偏空 + ROC 為負
        if rsi_val < self.rsi_overbought and roc_val < -self.roc_threshold:
            confidence = min(0.6 + (self.rsi_overbought - rsi_val) * 0.02 + abs(roc_val) * 0.05, 0.85)
            return SignalResult(signal="SHORT", confidence=confidence, price=current_price,
                reason=f"Dual Momentum SHORT (RSI={rsi_val:.1f}, ROC={roc_val:.1f})", 
                metadata={"rsi": rsi_val, "roc": roc_val, "type": "bearish"})
        
        return SignalResult(signal="HOLD", confidence=0.3, price=current_price, reason="No signal")
