# -*- coding: utf-8 -*-
"""
Commodity Channel Index (CCI / 商品通道指數)

震盪指標:
- CCI = (典型價格 - 移動平均) / (0.015 × 平均偏差)

發明人: Donald Lambert

交易訊號:
- CCI > 100: 可能超買
- CCI < -100: 可能超賣
- CCI 穿越 0: 趨勢轉換
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class CCI:
    """
    商品通道指數
    
    計算方法:
    1. Typical Price (TP) = (High + Low + Close) / 3
    2. SMA of TP
    3. Mean Deviation = mean(|TP - SMA|)
    4. CCI = (TP - SMA) / (0.015 × Mean Deviation)
    
    數值範圍: 無限制，通常在 -200 到 +200 之間
    
    交易訊號:
    - CCI > 100: 強勢，可能回調
    - CCI < -100: 弱勢，可能反彈
    - CCI 穿越 +100: 趨勢開始
    - CCI 穿越 -100: 趨勢結束
    """
    
    def __init__(self, period: int = 20):
        """
        初始化
        
        Args:
            period: 計算週期 (預設 20)
        """
        self.period = period
    
    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算 CCI
        
        Args:
            high: 最高價序列
            low: 最低價序列
            close: 收盤價序列
        
        Returns:
            Dict 含 cci, tp, sma, mean_deviation
        """
        # 計算典型價格
        tp = (high + low + close) / 3
        
        # 計算 TP 的移動平均
        tp_sma = tp.rolling(window=self.period).mean()
        
        # 計算平均偏差
        mean_deviation = tp.rolling(window=self.period).apply(
            lambda x: np.abs(x - x.mean()).mean(),
            raw=True
        )
        
        # 避免除零
        denominator = 0.015 * (mean_deviation + 1e-10)
        
        # 計算 CCI
        cci = (tp - tp_sma) / denominator
        
        return {
            "cci": cci,
            "tp": tp,
            "tp_sma": tp_sma,
            "mean_deviation": mean_deviation,
            "oversold": pd.Series(-100, index=close.index),
            "overbought": pd.Series(100, index=close.index)
        }
    
    def get_signal(
        self,
        cci: pd.Series,
        oversold: float = -100,
        overbought: float = 100
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            cci: CCI 序列
            oversold: 超賣閾值 (預設 -100)
            overbought: 超買閾值 (預設 100)
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=cci.index)
        
        # 買入訊號: CCI 從超賣區反彈
        oversold_condition = (cci < oversold) & (cci.shift(1) <= oversold)
        recovery_condition = cci > cci.shift(1)
        
        buy_signal = oversold_condition & recovery_condition
        signal[buy_signal] = 1
        
        # 賣出訊號: CCI 從超買區回落
        overbought_condition = (cci > overbought) & (cci.shift(1) >= overbought)
        decline_condition = cci < cci.shift(1)
        
        sell_signal = overbought_condition & decline_condition
        signal[sell_signal] = -1
        
        return signal
    
    def get_trend_signal(
        self,
        cci: pd.Series,
        threshold: float = 0
    ) -> pd.Series:
        """
        生成趨勢訊號
        
        Args:
            cci: CCI 序列
            threshold: 閾值 (預設 0)
        
        Returns:
            趨勢訊號: 1=多頭趨勢, -1=空頭趨勢, 0=無趨勢
        """
        trend = pd.Series(0, index=cci.index)
        
        # 多頭趨勢: CCI > threshold
        trend[cci > threshold] = 1
        
        # 空頭趨勢: CCI < -threshold
        trend[cci < -threshold] = -1
        
        return trend
    
    def get_zero_cross_signal(
        self,
        cci: pd.Series
    ) -> pd.Series:
        """
        生成 CCI 穿越 0 軸訊號
        
        Returns:
            穿越訊號: 1=向上穿越, -1=向下穿越, 0=無穿越
        """
        signal = pd.Series(0, index=cci.index)
        
        # 向上穿越
        crossover_up = (cci > 0) & (cci.shift(1) <= 0)
        signal[crossover_up] = 1
        
        # 向下穿越
        crossover_down = (cci < 0) & (cci.shift(1) >= 0)
        signal[crossover_down] = -1
        
        return signal
    
    def get_divergence(
        self,
        close: pd.Series,
        cci: pd.Series,
        lookback: int = 20
    ) -> pd.Series:
        """
        偵測背離
        
        Returns:
            背離訊號: 1=牛市背離, -1=熊市背離, 0=無背離
        """
        divergence = pd.Series(0, index=cci.index)
        
        for i in range(lookback, len(cci)):
            price_window = close[i-lookback:i+1]
            cci_window = cci[i-lookback:i+1]
            
            price_high_idx = price_window.idxmax()
            price_low_idx = price_window.idxmin()
            cci_high_idx = cci_window.idxmax()
            cci_low_idx = cci_window.idxmin()
            
            # 牛市背離
            if (close.iloc[i] < close.iloc[price_low_idx] and
                cci.iloc[i] > cci.iloc[cci_low_idx]):
                divergence.iloc[i] = 1
            
            # 熊市背離
            elif (close.iloc[i] > close.iloc[price_high_idx] and
                  cci.iloc[i] < cci.iloc[cci_high_idx]):
                divergence.iloc[i] = -1
        
        return divergence


def calculate_cci(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 20
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算 CCI
    """
    cci_indicator = CCI(period)
    return cci_indicator.calculate(high, low, close)
