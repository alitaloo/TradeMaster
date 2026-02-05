# -*- coding: utf-8 -*-
"""
ATR Breakout (ATR 突破策略)

波動率突破策略:
- ATR 突破時入場
- 波動率擴張時持有

原理: 價格波動率擴張時順勢交易
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class ATRBreakout:
    """
    ATR 突破策略指標
    
    計算方法:
    - ATR: True Range 的移動平均
    - Upper Band: Close + ATR × Multiplier
    - Lower Band: Close - ATR × Multiplier
    
    交易訊號:
    - 買入: Close > Upper Band
    - 賣出: Close < Lower Band
    """
    
    def __init__(
        self,
        atr_period: int = 14,
        atr_multiplier: float = 2.0,
        atr_ma_period: int = 20
    ):
        """
        初始化
        
        Args:
            atr_period: ATR 計算週期 (預設 14)
            atr_multiplier: ATR 倍數 (預設 2.0)
            atr_ma_period: ATR 移動平均週期 (預設 20)
        """
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.atr_ma_period = atr_ma_period
    
    def calculate_true_range(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> pd.Series:
        """
        計算 True Range
        
        TR = max(High - Low, |High - Prev Close|, |Low - Prev Close|)
        """
        prev_close = close.shift(1)
        
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range
    
    def calculate_atr(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> pd.Series:
        """
        計算 ATR (Average True Range)
        """
        true_range = self.calculate_true_range(high, low, close)
        atr = true_range.rolling(window=self.atr_period).mean()
        return atr
    
    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算 ATR 突破指標
        
        Args:
            high: 最高價序列
            low: 最低價序列
            close: 收盤價序列
        
        Returns:
            Dict 含 atr, upper, lower, breakout_upper, breakout_lower
        """
        atr = self.calculate_atr(high, low, close)
        
        # 計算 ATR 移動平均 (判斷波動率狀態)
        atr_ma = atr.rolling(window=self.atr_ma_period).mean()
        
        # 計算 ATR 標準化 (波動率狀態)
        atr_std = atr.rolling(window=self.atr_ma_period).std()
        atr_zscore = (atr - atr_ma) / (atr_std + 1e-10)
        
        # 計算突破通道
        upper = close + atr * self.atr_multiplier
        lower = close - atr * self.atr_multiplier
        
        # 波動率狀態
        volatility_regime = pd.Series("normal", index=close.index)
        volatility_regime[atr_zscore > 1.0] = "high"
        volatility_regime[atr_zscore < -1.0] = "low"
        
        return {
            "atr": atr,
            "atr_ma": atr_ma,
            "atr_zscore": atr_zscore,
            "upper": upper,
            "lower": lower,
            "volatility_regime": volatility_regime,
            "true_range": self.calculate_true_range(high, low, close)
        }
    
    def get_signal(
        self,
        close: pd.Series,
        atr: pd.Series,
        upper: pd.Series,
        lower: pd.Series,
        volatility_regime: pd.Series = None
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            close: 收盤價序列
            atr: ATR 序列
            upper: 上軌序列
            lower: 下軌序列
            volatility_regime: 波動率狀態
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=close.index)
        
        # 買入訊號: 價格突破上軌 + 波動率擴張
        buy_condition = close > upper
        
        if volatility_regime is not None:
            # 波動率擴張時才買入
            buy_condition = buy_condition & (volatility_regime.isin(["high", "normal"]))
        
        signal[buy_condition] = 1
        
        # 賣出訊號: 價格跌破下軌
        sell_condition = close < lower
        signal[sell_condition] = -1
        
        return signal
    
    def get_trailing_stop(
        self,
        close: pd.Series,
        atr: pd.Series,
        direction: int,
        atr_multiplier: float = 2.0
    ) -> pd.Series:
        """
        計算移動止損
        
        Args:
            close: 收盤價
            atr: ATR
            direction: 方向 (1=多頭, -1=空頭)
            atr_multiplier: ATR 倍數
        
        Returns:
            止損價格序列
        """
        trailing_stop = pd.Series(np.nan, index=close.index)
        
        if direction == 1:  # 多頭
            trailing_stop = close - atr * atr_multiplier
        elif direction == -1:  # 空頭
            trailing_stop = close + atr * atr_multiplier
        
        return trailing_stop


def calculate_atr_breakout(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int = 14,
    atr_multiplier: float = 2.0
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算 ATR 突破指標
    
    Args:
        high: 最高價
        low: 最低價
        close: 收盤價
        atr_period: ATR 週期
        atr_multiplier: ATR 倍數
    
    Returns:
        Dict 含 atr, upper, lower 等
    """
    atrb = ATRBreakout(atr_period, atr_multiplier)
    return atrb.calculate(high, low, close)
