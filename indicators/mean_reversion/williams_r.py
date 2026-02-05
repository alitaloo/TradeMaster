# -*- coding: utf-8 -*-
"""
Williams %R (威廉指標)

均值回歸策略指標:
- %R = (Highest High - Close) / (Highest High - Lowest Low) × -100

發明人: Larry Williams

交易訊號:
- 買入: %R < -80 (超賣)
- 賣出: %R > -20 (超買)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class WilliamsR:
    """
    威廉指標
    
    計算方法:
    - %R = -100 × (N 日最高 - 收盤價) / (N 日最高 - N 日最低)
    
    數值範圍: -100 到 0
    - -100: 強烈超賣
    - 0: 強烈超買
    
    交易訊號:
    - 超賣區 (< -80): 可能反彈
    - 超買區 (> -20): 可能回調
    """
    
    def __init__(self, period: int = 14):
        """
        初始化
        
        Args:
            period: 計算週期 (預設 14)
        """
        self.period = period
    
    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算威廉指標
        
        Args:
            high: 最高價序列
            low: 最低價序列
            close: 收盤價序列
        
        Returns:
            Dict 含 williams_r, oversold, overbought
        """
        highest_high = high.rolling(window=self.period).max()
        lowest_low = low.rolling(window=self.period).min()
        
        # 避免除零
        denominator = highest_high - lowest_low + 1e-10
        
        # 計算 %R (乘以 -1 轉換為 0 到 -100)
        williams_r = -100 * (highest_high - close) / denominator
        
        # 價格相對位置
        price_position = (close - lowest_low) / denominator * 100
        
        return {
            "williams_r": williams_r,
            "price_position": price_position,
            "oversold": pd.Series(-80, index=close.index),
            "overbought": pd.Series(-20, index=close.index)
        }
    
    def get_signal(
        self,
        williams_r: pd.Series,
        oversold: float = -80,
        overbought: float = -20
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            williams_r: %R 序列
            oversold: 超賣閾值 (預設 -80)
            overbought: 超買閾值 (預設 -20)
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=williams_r.index)
        
        # 買入訊號: %R 低於超賣閾值 且 開始反彈
        oversold_condition = williams_r < oversold
        recovery_condition = williams_r > williams_r.shift(1)
        
        buy_signal = oversold_condition & recovery_condition
        signal[buy_signal] = 1
        
        # 賣出訊號: %R 高於超買閾值 且 開始回調
        overbought_condition = williams_r > overbought
        decline_condition = williams_r < williams_r.shift(1)
        
        sell_signal = overbought_condition & decline_condition
        signal[sell_signal] = -1
        
        return signal
    
    def get_extreme_signal(
        self,
        williams_r: pd.Series,
        extreme_oversold: float = -95,
        extreme_overbought: float = -5
    ) -> pd.Series:
        """
        生成極端訊號 (更保守)
        
        Returns:
            訊號序列
        """
        signal = pd.Series(0, index=williams_r.index)
        
        # 極端超賣
        signal[williams_r <= extreme_oversold] = 1
        
        # 極端超買
        signal[williams_r >= extreme_overbought] = -1
        
        return signal
    
    def get_divergence(
        self,
        close: pd.Series,
        williams_r: pd.Series,
        lookback: int = 14
    ) -> pd.Series:
        """
        偵測背離
        
        Returns:
            背離訊號: 1=牛市背離, -1=熊市背離, 0=無背離
        """
        divergence = pd.Series(0, index=williams_r.index)
        
        for i in range(lookback, len(williams_r)):
            price_window = close[i-lookback:i+1]
            wr_window = williams_r[i-lookback:i+1]
            
            price_high_idx = price_window.idxmax()
            price_low_idx = price_window.idxmin()
            wr_high_idx = wr_window.idxmax()  # wr 值越大越接近 0
            wr_low_idx = wr_window.idxmin()   # wr 值越小越接近 -100
            
            # 牛市背離
            if (close.iloc[i] < close.iloc[price_low_idx] and
                williams_r.iloc[i] > williams_r.iloc[wr_low_idx]):
                divergence.iloc[i] = 1
            
            # 熊市背離
            elif (close.iloc[i] > close.iloc[price_high_idx] and
                  williams_r.iloc[i] < williams_r.iloc[wr_high_idx]):
                divergence.iloc[i] = -1
        
        return divergence


def calculate_williams_r(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算威廉指標
    """
    wr = WilliamsR(period)
    return wr.calculate(high, low, close)
