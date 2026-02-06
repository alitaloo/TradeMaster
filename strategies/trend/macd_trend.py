# MACD 交叉策略 - Trend Following
# MACD 金叉 (MACD 上穿 Signal) 做多，死叉 (MACD 下穿 Signal) 做空

from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult
import pandas as pd


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


@strategy(
    name="MACDTrend",
    type="trend_following",
    indicators=["MACD"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"]
)
class MACDTrendStrategy(BaseStrategy):
    """MACD 交叉策略"""
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
    
    def generate_signal(self, indicators: dict, data) -> SignalResult:
        """生成交易信號"""
        macd = indicators.get("MACD", {}).get("macd", data["Close"] * 0)
        signal = indicators.get("MACD", {}).get("signal", data["Close"] * 0)
        current_price = _get_current_price(data)
        
        if len(macd) < self.slow_period + self.signal_period:
            return SignalResult(signal="HOLD", confidence=0.0, price=_get_current_price(data), reason="Hold position", metadata={})
        
        latest_macd = macd.iloc[-1]
        latest_signal = signal.iloc[-1]
        
        prev_macd = macd.iloc[-2] if len(macd) > 1 else latest_macd
        prev_signal = signal.iloc[-2] if len(signal) > 1 else latest_signal
        
        # 金叉：MACD 從下方穿越 Signal
        if prev_macd <= prev_signal and latest_macd > latest_signal:
            # 計算交叉強度
            diff = latest_macd - latest_signal
            hist = indicators.get("MACD", {}).get("histogram", pd.Series([0]))
            if len(hist) > 1:
                hist_change = hist.iloc[-1] - hist.iloc[-2]
                momentum = 1 if hist_change > 0 else 0
            else:
                momentum = 1
            
            return SignalResult(
                signal="LONG",
                confidence=min(abs(diff) * 10 + momentum * 0.2, 1.0),
                price=_get_current_price(data),
                reason="MACD golden cross detected",
                metadata={
                    "macd": latest_macd,
                    "signal": latest_signal,
                    "crossover": "golden"
                }
            )
        
        # 死叉：MACD 從上方穿越 Signal
        elif prev_macd >= prev_signal and latest_macd < latest_signal:
            diff = latest_signal - latest_macd
            hist = indicators.get("MACD", {}).get("histogram", pd.Series([0]))
            if len(hist) > 1:
                hist_change = hist.iloc[-1] - hist.iloc[-2]
                momentum = 1 if hist_change < 0 else 0
            else:
                momentum = 1
            
            return SignalResult(
                signal="SHORT",
                confidence=min(abs(diff) * 10 + momentum * 0.2, 1.0),
                price=_get_current_price(data),
                reason="MACD death cross detected",
                metadata={
                    "macd": latest_macd,
                    "signal": latest_signal,
                    "crossover": "death"
                }
            )
        
        # 持有判斷
        elif latest_macd > latest_signal:
            return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"macd": latest_macd, "signal": latest_signal, "position": "long"})
        else:
            return SignalResult(signal="HOLD", confidence=0.3, price=_get_current_price(data), reason="Hold position", metadata={"macd": latest_macd, "signal": latest_signal, "position": "short"})
