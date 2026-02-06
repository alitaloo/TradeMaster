# ADX 趨勢策略 - Trend Following
# 當 ADX > 25 確認趨勢後，+DI > -DI 做多，-DI > +DI 做空

from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult
import pandas as pd


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


@strategy(
    name="ADXTrend",
    type="trend_following",
    indicators=["ADX"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending"]
)
class ADXTrendStrategy(BaseStrategy):
    """ADX 趨勢策略"""
    
    def __init__(self, adx_threshold: float = 25.0, period: int = 14):
        self.adx_threshold = adx_threshold
        self.period = period
    
    def generate_signal(self, indicators: dict, data) -> SignalResult:
        """生成交易信號"""
        adx = indicators.get("ADX", {}).get("adx", data["Close"] * 0 + 15)
        plus_di = indicators.get("ADX", {}).get("plus_di", data["Close"] * 0 + 20)
        minus_di = indicators.get("ADX", {}).get("minus_di", data["Close"] * 0 + 20)
        current_price = _get_current_price(data)
        
        if len(adx) < self.period:
            return SignalResult(signal="HOLD", confidence=0.0, price=current_price, reason="Hold position", metadata={})
        
        latest_adx = adx.iloc[-1]
        latest_plus = plus_di.iloc[-1]
        latest_minus = minus_di.iloc[-1]
        
        # ADX 低於閾值，趨勢不明確
        if latest_adx < self.adx_threshold:
            return SignalResult(signal="HOLD", confidence=latest_adx / self.adx_threshold, price=current_price, reason="Hold position", metadata={"adx": latest_adx, "reason": "weak_trend"})
        
        # 趨勢強度
        trend_strength = min((latest_adx - self.adx_threshold) / (50 - self.adx_threshold), 1.0)
        
        # +DI > -DI = 多頭趨勢
        if latest_plus > latest_minus:
            return SignalResult(
                signal="LONG",
                confidence=trend_strength,
                price=current_price,
                reason="+DI above -DI indicates uptrend",
                metadata={
                    "adx": latest_adx,
                    "plus_di": latest_plus,
                    "minus_di": latest_minus,
                    "reason": "uptrend"
                }
            )
        
        # -DI > +DI = 空頭趨勢
        elif latest_minus > latest_plus:
            return SignalResult(
                signal="SHORT",
                confidence=trend_strength,
                price=current_price,
                reason="-DI above +DI indicates downtrend",
                metadata={
                    "adx": latest_adx,
                    "plus_di": latest_plus,
                    "minus_di": latest_minus,
                    "reason": "downtrend"
                }
            )
        
        return SignalResult(signal="HOLD", confidence=0.0, price=current_price, reason="Hold position", metadata={"adx": latest_adx})
