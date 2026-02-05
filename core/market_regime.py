#!/usr/bin/env python3
"""
市場環境識別模組 - Market Regime Detector
識別：牛市、熊市、震盪市場
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum
from datetime import datetime
import pandas as pd
import numpy as np


class MarketRegime(Enum):
    """市場環境"""
    BULL = "bull"      # 牛市
    BEAR = "bear"      # 熊市
    NEUTRAL = "neutral"  # 震盪
    UNKNOWN = "unknown"


@dataclass
class RegimeConfig:
    """環境配置"""
    # 移動平均確認
    fast_ma_period: int = 20      # 快速均線
    slow_ma_period: int = 50     # 慢速均線
    
    # ADX 確認
    adx_period: int = 14
    adx_threshold: float = 25.0  # ADX > 25 表示有趨勢
    
    # 回撤確認
    max_drawdown_threshold: float = 0.10  # 10% 以上回撤可能是熊市
    
    # 週期確認
    confirmation_periods: int = 5  # 連續 N 根確認


class MarketRegimeDetector:
    """市場環境識別器"""
    
    def __init__(self, config: RegimeConfig = None):
        self.config = config or RegimeConfig()
        self._regime_history = []
    
    def detect_regime(
        self,
        prices: pd.Series,
        adx_value: float = None
    ) -> Tuple[MarketRegime, float]:
        """
        識別市場環境
        
        Returns:
            (regime, confidence)
        """
        if len(prices) < self.config.slow_ma_period + 10:
            return MarketRegime.UNKNOWN, 0.0
        
        # 計算移動平均
        fast_ma = prices.rolling(self.config.fast_ma_period).mean()
        slow_ma = prices.rolling(self.config.slow_ma_period).mean()
        
        # 計算趨勢強度
        trend_strength = self._calculate_trend_strength(prices, fast_ma, slow_ma)
        
        # 計算 ADX (如果沒有提供)
        if adx_value is None:
            adx_value = self._calculate_adx(prices)
        
        # 判斷環境
        if adx_value >= self.config.adx_threshold:
            # 有趨勢
            if trend_strength > 0:
                regime = MarketRegime.BULL
                confidence = min(abs(trend_strength), 1.0) * (adx_value / 50)
            else:
                regime = MarketRegime.BEAR
                confidence = min(abs(trend_strength), 1.0) * (adx_value / 50)
        else:
            # 無明顯趨勢
            regime = MarketRegime.NEUTRAL
            confidence = 1.0 - (adx_value / 50)
        
        # 記錄歷史
        self._regime_history.append({
            "date": prices.index[-1] if hasattr(prices.index[-1], 'strftime') else datetime.now(),
            "regime": regime,
            "confidence": confidence
        })
        
        return regime, confidence
    
    def detect_regime_multi_timeframe(
        self,
        daily_prices: pd.Series,
        weekly_prices: pd.Series = None,
        monthly_prices: pd.Series = None
    ) -> Dict[str, Tuple[MarketRegime, float]]:
        """
        多時間週期環境識別
        
        Returns:
            {"daily": (regime, confidence), "weekly": ..., "monthly": ...}
        """
        result = {}
        
        # 日線
        result["daily"] = self.detect_regime(daily_prices)
        
        # 周線 (如果提供)
        if weekly_prices is not None:
            result["weekly"] = self.detect_regime(weekly_prices)
        
        # 月線 (如果提供)
        if monthly_prices is not None:
            result["monthly"] = self.detect_regime(monthly_prices)
        
        return result
    
    def get_consensus_regime(
        self,
        regime_results: Dict[str, Tuple[MarketRegime, float]]
    ) -> Tuple[MarketRegime, float]:
        """
        取得共識環境
        
        多時間週期 majority vote
        """
        if not regime_results:
            return MarketRegime.UNKNOWN, 0.0
        
        # 統計各環境數量
        regime_counts = {}
        total_confidence = 0.0
        
        for timeframe, (regime, confidence) in regime_results.items():
            regime_counts[regime] = regime_counts.get(regime, 0) + 1
            total_confidence += confidence
        
        # 取得最多票的環境
        consensus = max(regime_counts, key=regime_counts.get)
        
        # 計算信心度 (基於票數和平均信心)
        avg_confidence = total_confidence / len(regime_results)
        vote_confidence = regime_counts[consensus] / len(regime_results)
        final_confidence = (avg_confidence + vote_confidence) / 2
        
        return consensus, final_confidence
    
    def _calculate_trend_strength(
        self,
        prices: pd.Series,
        fast_ma: pd.Series,
        slow_ma: pd.Series
    ) -> float:
        """計算趨勢強度 (-1 到 1)"""
        if len(fast_ma) < 2 or pd.isna(fast_ma.iloc[-1]) or pd.isna(slow_ma.iloc[-1]):
            return 0.0
        
        # 均線位置
        ma_position = (fast_ma.iloc[-1] - slow_ma.iloc[-1]) / slow_ma.iloc[-1]
        
        # 均線斜率
        if len(fast_ma) >= 10:
            fast_slope = (fast_ma.iloc[-1] - fast_ma.iloc[-10]) / fast_ma.iloc[-10]
            slow_slope = (slow_ma.iloc[-1] - slow_ma.iloc[-10]) / slow_ma.iloc[-10]
            slope_confirm = 1 if fast_slope > 0 and slow_slope > 0 else -1 if fast_slope < 0 and slow_slope < 0 else 0
        else:
            slope_confirm = 0
        
        # 結合
        strength = (ma_position * 2 + slope_confirm * 0.5) / 2.5
        
        return max(-1.0, min(1.0, strength))
    
    def _calculate_adx(self, prices: pd.Series, period: int = None) -> float:
        """計算 ADX (簡化版)"""
        period = period or self.config.adx_period
        
        if len(prices) < period + 1:
            return 0.0
        
        high = prices * 1.02  # 模擬
        low = prices * 0.98   # 模擬
        
        # +DI 和 -DI
        high_diff = high.diff()
        low_diff = -low.diff()
        
        plus_di = 100 * high_diff.rolling(period).mean() / prices.rolling(period).std()
        minus_di = 100 * low_diff.rolling(period).mean() / prices.rolling(period).std()
        
        # ADX
        dx = abs(plus_di - minus_di) / (plus_di + minus_di + 0.0001) * 100
        adx = dx.rolling(period).mean()
        
        return adx.iloc[-1] if len(adx) > 0 else 0.0
    
    def is_trending_market(self, regime: MarketRegime) -> bool:
        """是否是趨勢市場"""
        return regime in [MarketRegime.BULL, MarketRegime.BEAR]
    
    def is_bull_market(self, regime: MarketRegime) -> bool:
        """是否是牛市"""
        return regime == MarketRegime.BULL
    
    def get_regime_for_strategy(self, strategy_type: str) -> Dict[MarketRegime, float]:
        """
        根據策略類型，返回適合的環境權重
        
        例如:
        - 趨勢策略: BULL=1.0, BEAR=0.5, NEUTRAL=0.2
        - 均值回歸: NEUTRAL=1.0, BULL=0.3, BEAR=0.3
        """
        if strategy_type == "trend":
            return {
                MarketRegime.BULL: 1.0,
                MarketRegime.BEAR: 0.5,
                MarketRegime.NEUTRAL: 0.2,
                MarketRegime.UNKNOWN: 0.5
            }
        elif strategy_type == "mean_reversion":
            return {
                MarketRegime.BULL: 0.3,
                MarketRegime.BEAR: 0.3,
                MarketRegime.NEUTRAL: 1.0,
                MarketRegime.UNKNOWN: 0.5
            }
        elif strategy_type == "momentum":
            return {
                MarketRegime.BULL: 1.0,
                MarketRegime.BEAR: 0.8,
                MarketRegime.NEUTRAL: 0.5,
                MarketRegime.UNKNOWN: 0.5
            }
        else:
            return {
                MarketRegime.BULL: 0.7,
                MarketRegime.BEAR: 0.7,
                MarketRegime.NEUTRAL: 0.7,
                MarketRegime.UNKNOWN: 0.5
            }
    
    def get_history(self, n: int = 10) -> list:
        """獲取最近的環境歷史"""
        return self._regime_history[-n:]
    
    def clear_history(self):
        """清除歷史"""
        self._regime_history = []


# 便捷函數
def detect_market_regime(
    prices: pd.Series,
    adx_value: float = None
) -> Tuple[MarketRegime, float]:
    """快速識別市場環境"""
    detector = MarketRegimeDetector()
    return detector.detect_regime(prices, adx_value)
