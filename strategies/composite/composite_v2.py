#!/usr/bin/env python3
"""
複合策略 v2 - Composite/Multi-Factor Strategies v2
結合多種指標的信號 + 波動率過濾 + 市場環境識別
"""

import pandas as pd
from typing import Dict, List, Optional
from core.decorators import strategy
from core.base_classes import BaseStrategy, SignalResult


def _get_current_price(price_data):
    """獲取當前價格"""
    close = price_data["Close"]
    return close.iloc[-1] if len(close) > 0 else 0.0

@strategy(
    name="MultiFactorV2",
    type="composite",
    indicators=["RSI", "MACD", "ADX", "SMA", "BollingerBands"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile"],
    parameters={
        "rsi_oversold": {"type": float, "default": 30.0},
        "rsi_overbought": {"type": float, "default": 70.0},
        "adx_threshold": {"type": float, "default": 25.0},
        "min_agreement": {"type": float, "default": 0.6},
        "use_volatility_filter": {"type": bool, "default": True},
        "bb_percent_low": {"type": float, "default": 0.2},
        "bb_percent_high": {"type": float, "default": 0.8},
        "min_confidence": {"type": float, "default": 0.5}
    },
    tags=["composite", "multi_factor", "volatility_filter", "v2"]
)
class MultiFactorStrategyV2(BaseStrategy):
    """多因子複合策略 v2 - 結合 RSI, MACD, ADX + 波動率過濾"""
    
    def __init__(
        self,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        adx_threshold: float = 25.0,
        min_agreement: float = 0.6,
        use_volatility_filter: bool = True,
        bb_percent_low: float = 0.2,
        bb_percent_high: float = 0.8,
        min_confidence: float = 0.5,
        **kwargs
    ):
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.adx_threshold = adx_threshold
        self.min_agreement = min_agreement
        self.use_volatility_filter = use_volatility_filter
        self.bb_percent_low = bb_percent_low
        self.bb_percent_high = bb_percent_high
        self.min_confidence = min_confidence
    
    def generate_signal(
        self,
        indicator_values: Dict,
        price_data: pd.DataFrame
    ) -> SignalResult:
        current_price = price_data["Close"].iloc[-1]
        
        # ===== 波動率過濾 =====
        volatility_filtered = False
        bb_percent = 0.5
        
        if self.use_volatility_filter:
            bb_data = indicator_values.get("BollingerBands")
            if bb_data:
                bb_percent = bb_data.get("percent", pd.Series([0.5])).iloc[-1]
                # 價格在布林帶中間區域才交易
                if bb_percent > self.bb_percent_high or bb_percent < self.bb_percent_low:
                    volatility_filtered = True
        
        factors = {
            "bullish": [],
            "bearish": [],
            "warnings": []
        }
        
        # ===== RSI 分析 =====
        rsi_data = indicator_values.get("RSI")
        if rsi_data:
            rsi = rsi_data.get("rsi", pd.Series([50])).iloc[-1]
            if rsi < self.rsi_oversold:
                factors["bullish"].append(f"RSI({rsi:.1f}) oversold")
            elif rsi > self.rsi_overbought:
                factors["bearish"].append(f"RSI({rsi:.1f}) overbought")
        
        # ===== MACD 分析 =====
        macd_data = indicator_values.get("MACD")
        if macd_data:
            histogram = macd_data.get("histogram", pd.Series([0])).iloc[-1]
            if histogram > 0:
                factors["bullish"].append("MACD histogram positive")
            elif histogram < 0:
                factors["bearish"].append("MACD histogram negative")
        
        # ===== ADX 趨勢強度 =====
        adx_data = indicator_values.get("ADX")
        adx_value = 0
        if adx_data:
            adx_value = adx_data.get("adx", pd.Series([0])).iloc[-1]
            plus_di = adx_data.get("plus_di", pd.Series([0])).iloc[-1]
            minus_di = adx_data.get("minus_di", pd.Series([0])).iloc[-1]
            
            if adx_value >= self.adx_threshold:
                if plus_di > minus_di:
                    factors["bullish"].append(f"ADX({adx_value:.1f}) strong uptrend")
                elif minus_di > plus_di:
                    factors["bearish"].append(f"ADX({adx_value:.1f}) strong downtrend")
            else:
                factors["warnings"].append(f"ADX({adx_value:.1f}) weak trend")
        
        # ===== SMA 分析 =====
        sma_data = indicator_values.get("SMA")
        if sma_data:
            sma = sma_data.get("sma", pd.Series([current_price])).iloc[-1]
            price_vs_sma = sma_data.get("price_vs_sma", pd.Series([0])).iloc[-1]
            
            if price_vs_sma > 0.02:
                factors["bullish"].append(f"Price above SMA ({price_vs_sma:.1%})")
            elif price_vs_sma < -0.02:
                factors["bearish"].append(f"Price below SMA ({price_vs_sma:.1%})")
        
        # ===== 計算共識 =====
        total_factors = len(factors["bullish"]) + len(factors["bearish"])
        
        if total_factors == 0:
            return SignalResult(
                signal="HOLD",
                confidence=self.min_confidence,
                price=_get_current_price(price_data),
                reason="Insufficient data for analysis",
                metadata={"volatility_filtered": volatility_filtered}
            )
        
        bullish_pct = len(factors["bullish"]) / total_factors
        bearish_pct = len(factors["bearish"]) / total_factors
        
        # ===== 生成信號 =====
        reason_parts = []
        if volatility_filtered:
            reason_parts.append(f"Volatility extreme (BB%={bb_percent:.2f})")
        
        if bullish_pct >= self.min_agreement:
            confidence = bullish_pct
            reason_parts.extend(factors["bullish"][-3:])
            return SignalResult(
                signal="LONG",
                confidence=confidence,
                price=_get_current_price(price_data),
                reason="; ".join(reason_parts) if reason_parts else "LONG signal",
                indicators={
                    "bullish_count": len(factors["bullish"]),
                    "bearish_count": len(factors["bearish"]),
                    "adx": adx_value,
                    "volatility_filtered": volatility_filtered
                },
                metadata={"volatility_filtered": volatility_filtered}
            )
        
        elif bearish_pct >= self.min_agreement:
            confidence = bearish_pct
            reason_parts.extend(factors["bearish"][-3:])
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=_get_current_price(price_data),
                reason="; ".join(reason_parts) if reason_parts else "SHORT signal",
                indicators={
                    "bullish_count": len(factors["bullish"]),
                    "bearish_count": len(factors["bearish"]),
                    "adx": adx_value,
                    "volatility_filtered": volatility_filtered
                },
                metadata={"volatility_filtered": volatility_filtered}
            )
        
        # HOLD
        if factors["warnings"]:
            reason_parts.extend(factors["warnings"][:2])
        
        return SignalResult(
            signal="HOLD",
            confidence=0.5,
            price=_get_current_price(price_data),
            reason="No consensus: bullish={}, bearish={}".format(
                len(factors["bullish"]), len(factors["bearish"])
            ),
            indicators={
                "bullish_count": len(factors["bullish"]),
                "bearish_count": len(factors["bearish"]),
                "adx": adx_value,
                "volatility_filtered": volatility_filtered
            },
            metadata={"volatility_filtered": volatility_filtered}
        )


@strategy(
    name="SectorAdaptive",
    type="composite",
    indicators=["RSI", "MACD", "ADX", "SMA", "BollingerBands"],
    signals=["LONG", "SHORT", "HOLD"],
    market_regimes=["trending", "volatile", "neutral"],
    parameters={
        "sector_type": {"type": str, "default": "tech"},
        "use_adaptive_params": {"type": bool, "default": True}
    },
    tags=["composite", "adaptive", "sector_aware"]
)
class SectorAdaptiveStrategy(BaseStrategy):
    """行業自適應策略 - 根據行業特性自動調整參數"""
    
    # 行業特定參數
    SECTOR_PARAMS = {
        "semiconductor": {
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "adx_threshold": 25,
            "min_agreement": 0.6,
            "volatility_filter": True,
            "bb_range": (0.15, 0.85)
        },
        "tech_giant": {
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "adx_threshold": 20,
            "min_agreement": 0.5,
            "volatility_filter": False,
            "bb_range": (0.2, 0.8)
        },
        "ev_automobile": {
            "rsi_oversold": 40,
            "rsi_overbought": 60,
            "adx_threshold": 30,
            "min_agreement": 0.7,
            "volatility_filter": True,
            "bb_range": (0.1, 0.9)
        },
        "crypto": {
            "rsi_oversold": 45,
            "rsi_overbought": 55,
            "adx_threshold": 35,
            "min_agreement": 0.7,
            "volatility_filter": True,
            "bb_range": (0.1, 0.9)
        },
        "storage": {
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "adx_threshold": 25,
            "min_agreement": 0.6,
            "volatility_filter": True,
            "bb_range": (0.15, 0.85)
        },
        "default": {
            "rsi_oversold": 30,
            "rsi_overbought": 70,
            "adx_threshold": 25,
            "min_agreement": 0.6,
            "volatility_filter": False,
            "bb_range": (0.2, 0.8)
        }
    }
    
    def __init__(
        self,
        sector_type: str = "tech",
        use_adaptive_params: bool = True,
        **kwargs
    ):
        self.sector_type = sector_type
        self.use_adaptive_params = use_adaptive_params
        
        # 獲取行業參數
        params = self.SECTOR_PARAMS.get(sector_type, self.SECTOR_PARAMS["default"])
        self.rsi_oversold = params["rsi_oversold"]
        self.rsi_overbought = params["rsi_overbought"]
        self.adx_threshold = params["adx_threshold"]
        self.min_agreement = params["min_agreement"]
        self.volatility_filter = params["volatility_filter"]
        self.bb_low = params["bb_range"][0]
        self.bb_high = params["bb_range"][1]
    
    def generate_signal(
        self,
        indicator_values: Dict,
        price_data: pd.DataFrame
    ) -> SignalResult:
        current_price = price_data["Close"].iloc[-1]
        
        # 波動率過濾
        volatility_filtered = False
        if self.volatility_filter:
            bb_data = indicator_values.get("BollingerBands")
            if bb_data:
                bb_percent = bb_data.get("percent", pd.Series([0.5])).iloc[-1]
                if bb_percent > self.bb_high or bb_percent < self.bb_low:
                    volatility_filtered = True
        
        factors = {"bullish": [], "bearish": []}
        adx_value = 0
        
        # RSI
        rsi_data = indicator_values.get("RSI")
        if rsi_data:
            rsi = rsi_data.get("rsi", pd.Series([50])).iloc[-1]
            if rsi < self.rsi_oversold:
                factors["bullish"].append(f"RSI({rsi:.1f})")
            elif rsi > self.rsi_overbought:
                factors["bearish"].append(f"RSI({rsi:.1f})")
        
        # MACD
        macd_data = indicator_values.get("MACD")
        if macd_data:
            histogram = macd_data.get("histogram", pd.Series([0])).iloc[-1]
            if histogram > 0:
                factors["bullish"].append("MACD+")
            elif histogram < 0:
                factors["bearish"].append("MACD-")
        
        # ADX
        adx_data = indicator_values.get("ADX")
        if adx_data:
            adx_value = adx_data.get("adx", pd.Series([0])).iloc[-1]
            plus_di = adx_data.get("plus_di", pd.Series([0])).iloc[-1]
            minus_di = adx_data.get("minus_di", pd.Series([0])).iloc[-1]
            
            if adx_value >= self.adx_threshold:
                if plus_di > minus_di:
                    factors["bullish"].append(f"ADX({adx_value:.0f})")
                else:
                    factors["bearish"].append(f"ADX({adx_value:.0f})")
        
        # SMA
        sma_data = indicator_values.get("SMA")
        if sma_data:
            price_vs_sma = sma_data.get("price_vs_sma", pd.Series([0])).iloc[-1]
            if price_vs_sma > 0.02:
                factors["bullish"].append("Price>SMA")
            elif price_vs_sma < -0.02:
                factors["bearish"].append("Price<SMA")
        
        # 計算共識
        total = len(factors["bullish"]) + len(factors["bearish"])
        if total == 0:
            return SignalResult(
                signal="HOLD", confidence=0.5, price=_get_current_price(price_data),
                reason="No data", metadata={"sector": self.sector_type}
            )
        
        bullish_pct = len(factors["bullish"]) / total
        bearish_pct = len(factors["bearish"]) / total
        
        # 生成信號
        if bullish_pct >= self.min_agreement:
            return SignalResult(
                signal="LONG", confidence=bullish_pct, price=_get_current_price(price_data),
                reason="LONG: " + ",".join(factors["bullish"]),
                indicators={"sector": self.sector_type, "adx": adx_value}
            )
        elif bearish_pct >= self.min_agreement:
            return SignalResult(
                signal="SHORT", confidence=bearish_pct, price=_get_current_price(price_data),
                reason="SHORT: " + ",".join(factors["bearish"]),
                indicators={"sector": self.sector_type, "adx": adx_value}
            )
        
        return SignalResult(
            signal="HOLD", confidence=0.5, price=_get_current_price(price_data),
            reason=f"No consensus ({self.sector_type})",
            indicators={"sector": self.sector_type, "adx": adx_value}
        )
