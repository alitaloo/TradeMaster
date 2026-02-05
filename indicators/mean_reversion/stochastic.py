# -*- coding: utf-8 -*-
"""
Stochastic Oscillator (隨機指標)

均值回歸策略指標:
- %K: (Close - Lowest Low) / (Highest High - Lowest Low) × 100
- %D: %K 的移動平均

發明人: George Lane

交易訊號:
- 買入: %K < 20 且 %K 上穿 %D
- 賣出: %K > 80 且 %K 下穿 %D
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class Stochastic:
    """
    隨機指標
    
    計算方法:
    - %K = 100 × (Close - N 日最低) / (N 日最高 - N 日最低)
    - %D = %K 的 M 日移動平均
    
    交易訊號:
    - 超賣 (< 20): 可能反彈
    - 超買 (> 80): 可能回調
    """
    
    def __init__(
        self,
        period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3
    ):
        """
        初始化
        
        Args:
            period: %K 計算週期 (預設 14)
            smooth_k: %K 平滑週期 (預設 3)
            smooth_d: %D 平滑週期 (預設 3)
        """
        self.period = period
        self.smooth_k = smooth_k
        self.smooth_d = smooth_d
    
    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算隨機指標
        
        Args:
            high: 最高價序列
            low: 最低價序列
            close: 收盤價序列
        
        Returns:
            Dict 含 %K, %D, oversold, overbought
        """
        # 計算 %K
        lowest_low = low.rolling(window=self.period).min()
        highest_high = high.rolling(window=self.period).max()
        
        # 避免除零
        denominator = highest_high - lowest_low + 1e-10
        
        percent_k = 100 * (close - lowest_low) / denominator
        
        # 平滑 %K
        if self.smooth_k > 1:
            percent_k = percent_k.rolling(window=self.smooth_k).mean()
        
        # 計算 %D
        percent_d = percent_k.rolling(window=self.smooth_d).mean()
        
        # 價格相對位置 (類似 %K 但不使用平滑)
        price_position = 100 * (close - lowest_low) / denominator
        
        return {
            "k": percent_k,
            "d": percent_d,
            "price_position": price_position,
            "oversold": pd.Series(20, index=close.index),
            "overbought": pd.Series(80, index=close.index)
        }
    
    def get_signal(
        self,
        k: pd.Series,
        d: pd.Series,
        oversold: float = 20,
        overbought: float = 80
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            k: %K 序列
            d: %D 序列
            oversold: 超賣閾值 (預設 20)
            overbought: 超買閾值 (預設 80)
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=k.index)
        
        # 買入訊號: %K < oversold 且 %K 上穿 %D
        oversold_condition = (k < oversold) & (k.shift(1) <= oversold)
        crossover_bull = (k > d) & (k.shift(1) <= d.shift(1))
        
        buy_signal = oversold_condition & crossover_bull
        signal[buy_signal] = 1
        
        # 賣出訊號: %K > overbought 且 %K 下穿 %D
        overbought_condition = (k > overbought) & (k.shift(1) >= overbought)
        crossover_bear = (k < d) & (k.shift(1) >= d.shift(1))
        
        sell_signal = overbought_condition & crossover_bear
        signal[sell_signal] = -1
        
        return signal
    
    def get_divergence(
        self,
        close: pd.Series,
        k: pd.Series,
        lookback: int = 14
    ) -> pd.Series:
        """
        偵測背離
        
        Args:
            close: 收盤價
            k: %K 序列
            lookback: 回溯週期
        
        Returns:
            背離訊號: 1=牛市背離, -1=熊市背離, 0=無背離
        """
        divergence = pd.Series(0, index=k.index)
        
        for i in range(lookback, len(k)):
            # 找到近期高點/低點
            price_window = close[i-lookback:i+1]
            k_window = k[i-lookback:i+1]
            
            price_high_idx = price_window.idxmax()
            price_low_idx = price_window.idxmin()
            k_high_idx = k_window.idxmax()
            k_low_idx = k_window.idxmin()
            
            # 牛市背離: 價格新低但 %K 沒有新低
            if (close.iloc[i] < close.iloc[price_low_idx] and
                k.iloc[i] > k.iloc[k_low_idx]):
                divergence.iloc[i] = 1
            
            # 熊市背離: 價格新高但 %K 沒有新高
            elif (close.iloc[i] > close.iloc[price_high_idx] and
                  k.iloc[i] < k.iloc[k_high_idx]):
                divergence.iloc[i] = -1
        
        return divergence


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
    smooth_k: int = 3,
    smooth_d: int = 3
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算隨機指標
    """
    stoch = Stochastic(period, smooth_k, smooth_d)
    return stoch.calculate(high, low, close)
