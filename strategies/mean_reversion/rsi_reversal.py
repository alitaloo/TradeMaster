# RSI 反轉策略 - Mean Reversion
# 當 RSI 進入超賣區域反彈時做多，超買區域回落時做空

from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


@strategy(
    name="RSI_Reversal",
    type="mean_reversion",
    indicators=["RSI"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["neutral", "volatile"]
)
class RSIReversalStrategy(BaseStrategy):
    """RSI 反轉策略"""
    
    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
    
    def generate_signal(self, indicators: dict, data) -> SignalResult:
        """生成交易信號"""
        rsi = indicators.get("RSI", {}).get("rsi", data["Close"] * 0 + 50)
        current_price = _get_current_price(data)
        
        if len(rsi) < self.period:
            return SignalResult(signal="HOLD", confidence=0.0, price=current_price, reason="Hold position", metadata={})
        
        latest_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else latest_rsi
        
        # 反轉信號
        if latest_rsi < self.oversold and prev_rsi <= latest_rsi:
            # 超賣 + 反彈
            confidence = min((self.oversold - latest_rsi) / self.oversold, 1.0)
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=current_price,
                reason="RSI oversold with reversal signal",
                metadata={"rsi": latest_rsi, "reason": "oversold_reversal"}
            )
        
        elif latest_rsi > self.overbought and prev_rsi >= latest_rsi:
            # 超買 + 回落
            confidence = min((latest_rsi - self.overbought) / (100 - self.overbought), 1.0)
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=current_price,
                reason="RSI overbought with reversal signal",
                metadata={"rsi": latest_rsi, "reason": "overbought_reversal"}
            )
        
        return SignalResult(signal="HOLD", confidence=0.0, price=current_price, reason="Hold position", metadata={"rsi": latest_rsi})
