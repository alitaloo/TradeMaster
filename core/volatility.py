#!/usr/bin/env python3
"""
波動率分析模組 - Volatility Analyzer
計算 ATR、歷史波動率、動態止損/倉位
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime
import pandas as pd
import numpy as np


@dataclass
class VolatilityConfig:
    """波動率配置"""
    atr_period: int = 14           # ATR 週期
    atr_multiplier: float = 2.0    # ATR 倍數 (止損用)
    volatility_lookback: int = 20   # 波動率回顧期
    volatility_threshold_high: float = 0.03   # 高波動率閾值 (3%)
    volatility_threshold_low: float = 0.01    # 低波動率閾值 (1%)
    position_size_base: float = 0.02  # 基礎倉位 (2% 風險)


class VolatilityAnalyzer:
    """波動率分析器"""
    
    def __init__(self, config: VolatilityConfig = None):
        self.config = config or VolatilityConfig()
    
    def calculate_atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = None
    ) -> pd.Series:
        """
        計算 Average True Range
        
        ATR = MA(True Range)
        True Range = max(High-Low, |High-PrevClose|, |Low-PrevClose|)
        """
        period = period or self.config.atr_period
        
        # True Range
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR
        atr = tr.rolling(period).mean()
        
        return atr
    
    def calculate_atr_percent(
        self,
        atr: pd.Series,
        price: pd.Series
    ) -> pd.Series:
        """
        計算 ATR 佔價格的百分比
        
        ATR% = ATR / Close * 100
        """
        atr_percent = (atr / price) * 100
        return atr_percent
    
    def calculate_historical_volatility(
        self,
        close: pd.Series,
        period: int = None,
        annualized: bool = True
    ) -> pd.Series:
        """
        計算歷史波動率
        
        HV = StdDev(returns) * sqrt(252) * 100
        """
        period = period or self.config.volatility_lookback
        
        # 日收益率
        returns = close.pct_change()
        
        # 波動率
        hv = returns.rolling(period).std()
        
        if annualized:
            hv = hv * np.sqrt(252) * 100  # 年化
        
        return hv
    
    def get_volatility_regime(
        self,
        hv: pd.Series
    ) -> str:
        """
        判斷波動率環境
        
        Returns: "high", "medium", "low"
        """
        if hv.iloc[-1] > self.config.volatility_threshold_high:
            return "high"
        elif hv.iloc[-1] < self.config.volatility_threshold_low:
            return "low"
        else:
            return "medium"
    
    def calculate_dynamic_stop_loss(
        self,
        entry_price: float,
        atr: float,
        atr_multiplier: float = None,
        direction: str = "LONG"
    ) -> float:
        """
        計算動態止損價位
        
        Stop Loss = Entry ± ATR * Multiplier
        """
        atr_multiplier = atr_multiplier or self.config.atr_multiplier
        
        if direction == "LONG":
            stop_loss = entry_price - atr * atr_multiplier
        else:  # SHORT
            stop_loss = entry_price + atr * atr_multiplier
        
        return stop_loss
    
    def calculate_position_size(
        self,
        capital: float,
        atr: float,
        entry_price: float,
        base_risk_pct: float = None,
        volatility Regime: str = None
    ) -> float:
        """
        計算倉位大小
        
        Position Size = (Capital * Risk%) / ATR$
        
        根據波動率調整:
        - 高波動: 減少倉位
        - 低波動: 增加倉位
        """
        base_risk_pct = base_risk_pct or self.config.position_size_base
        
        # ATR 佔價格比例
        atr_pct = atr / entry_price
        
        # 基礎倉位 (風險金額)
        risk_amount = capital * base_risk_pct
        
        # 倉位數量
        position_size = risk_amount / atr
        
        # 根據波動率調整
        if volatility_regime == "high":
            position_size *= 0.5  # 高波動減半
        elif volatility_regime == "low":
            position_size *= 1.2  # 低波動增加 20%
        
        # 限制最大倉位 (不超過資本的 25%)
        max_size = capital * 0.25 / entry_price
        position_size = min(position_size, max_size)
        
        return int(position_size)
    
    def calculate_volatility_adjusted_return(
        self,
        returns: pd.Series,
        hv: pd.Series
    ) -> pd.Series:
        """
        計算波動率調整後回報
        
        Risk-Adjusted Return = Return / HV
        """
        # 避免除零
        hv_safe = hv.replace(0, np.nan)
        
        # 夏普比率-like 指標
        sharpe_like = returns / hv_safe * np.sqrt(252)
        
        return sharpe_like
    
    def get_volatility_summary(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict:
        """
        獲取波動率摘要
        """
        atr = self.calculate_atr(high, low, close)
        atr_pct = self.calculate_atr_percent(atr, close)
        hv = self.calculate_historical_volatility(close)
        regime = self.get_volatility_regime(hv)
        
        return {
            "atr": atr.iloc[-1] if len(atr) > 0 else None,
            "atr_percent": atr_pct.iloc[-1] if len(atr_pct) > 0 else None,
            "hv": hv.iloc[-1] if len(hv) > 0 else None,
            "hv_daily": hv.iloc[-1] / np.sqrt(252) if len(hv) > 0 and hv.iloc[-1] else None,
            "volatility_regime": regime,
            "atr_ma": atr.rolling(20).mean().iloc[-1] if len(atr) > 20 else atr.iloc[-1],
            "hv_ma": hv.rolling(20).mean().iloc[-1] if len(hv) > 20 else hv.iloc[-1]
        }
    
    def is_high_volatility(self, hv: pd.Series) -> bool:
        """是否高波動率"""
        return self.get_volatility_regime(hv) == "high"
    
    def is_low_volatility(self, hv: pd.Series) -> bool:
        """是否低波動率"""
        return self.get_volatility_regime(hv) == "low"


# 便捷函數
def calculate_atr(high, low, close, period: int = 14) -> pd.Series:
    """快速計算 ATR"""
    analyzer = VolatilityAnalyzer()
    return analyzer.calculate_atr(high, low, close, period)


def calculate_position_size(capital, atr, entry_price, risk_pct: float = 0.02) -> float:
    """快速計算倉位"""
    analyzer = VolatilityAnalyzer()
    return analyzer.calculate_position_size(capital, atr, entry_price, risk_pct)
