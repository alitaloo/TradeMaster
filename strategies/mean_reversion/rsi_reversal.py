# RSI 反轉策略 v2 - Mean Reversion with Trend Filter
# 當 RSI 進入超賣區域反彈時做多，超買區域回落時做空
# 2026-02-12: 添加 SMA 200 確認和 ADX > 25 趨勢濾網

from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult
import pandas as pd
import numpy as np


def _get_current_price(data):
    """獲取當前價格"""
    close = data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0


@strategy(
    name="RSI_Reversal_v2",
    type="mean_reversion",
    indicators=["RSI", "SMA", "ADX"],
    signals=["LONG", "SHORT", "HOLD", "CLOSE"],
    market_regimes=["neutral", "bull"]
)
class RSIReversalStrategy(BaseStrategy):
    """
    RSI 反轉策略 v2 - 帶趨勢濾網
    
    優化點（2026-02-12）：
    1. 添加 SMA 200 確認（價格必須在 SMA 200 上方）
    2. 添加 ADX > 25 趨勢強度過濾
    3. 只在上升趨勢中執行 RSI 均值回歸
    """
    
    def __init__(self, 
                 period: int = 14, 
                 oversold: float = 30.0, 
                 overbought: float = 70.0,
                 sma_period: int = 200,
                 adx_period: int = 14,
                 adx_threshold: float = 25.0,
                 use_trend_filter: bool = False):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.sma_period = sma_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.use_trend_filter = use_trend_filter
    
    def generate_signal(self, indicators: dict, data) -> SignalResult:
        """生成交易信號"""
        rsi = indicators.get("RSI", {}).get("rsi", data["Close"] * 0 + 50)
        current_price = _get_current_price(data)
        
        if len(rsi) < self.period:
            return SignalResult(signal="HOLD", confidence=0.0, price=_get_current_price(data), reason="Hold position", metadata={})
        
        latest_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else latest_rsi
        
        # 獲取趨勢指標
        sma = indicators.get("SMA", {}).get("sma", pd.Series([current_price] * len(data)))
        adx = indicators.get("ADX", {}).get("adx", pd.Series([50] * len(data)))
        
        current_sma = sma.iloc[-1] if hasattr(sma.iloc[-1], '__float__') else current_price
        price_above_sma = current_price > current_sma
        latest_adx = adx.iloc[-1] if hasattr(adx.iloc[-1], '__float__') else 50
        
        # === 趨勢濾網 ===
        trend_bull = True
        if self.use_trend_filter:
            trend_bull = price_above_sma and latest_adx > self.adx_threshold
        
        # === 反轉信號 ===
        if latest_rsi < self.oversold and prev_rsi <= latest_rsi:
            # 超賣 + 反彈
            if trend_bull:
                # 上升趨勢中，信心增加
                confidence = min((self.oversold - latest_rsi) / self.oversold, 1.0)
                if price_above_sma:
                    confidence = min(confidence * 1.1, 1.0)  # 價格在均線上，信心加成
                return SignalResult(
                    signal="LONG",
                    confidence=confidence,
                    price=_get_current_price(data),
                    reason="RSI oversold + uptrend confirmed (SMA>0, ADX>25)",
                    metadata={"rsi": latest_rsi, "trend": "BULL", "sma": current_sma, "adx": latest_adx}
                )
            else:
                return SignalResult(
                    signal="HOLD",
                    confidence=0.0,
                    price=_get_current_price(data),
                    reason="RSI oversold but trend filter failed (price<SMA or ADX<25)",
                    metadata={"rsi": latest_rsi, "trend_filter_passed": False, "adx": latest_adx}
                )
        
        elif latest_rsi > self.overbought and prev_rsi >= latest_rsi:
            # 超買 + 回落
            confidence = min((latest_rsi - self.overbought) / (100 - self.overbought), 1.0)
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=_get_current_price(data),
                reason="RSI overbought with reversal signal",
                metadata={"rsi": latest_rsi}
            )
        
        return SignalResult(signal="HOLD", confidence=0.0, price=_get_current_price(data), reason="Hold position", metadata={"rsi": latest_rsi, "trend_bull": trend_bull})
