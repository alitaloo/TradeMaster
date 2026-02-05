# -*- coding: utf-8 -*-
"""
Rate of Change (ROC / 變動率)

動量指標:
- ROC = (Current Price - Price N Periods Ago) / Price N Periods Ago × 100

交易訊號:
- ROC > 0: 動量向上
- ROC < 0: 動量向下
- ROC 穿越 0: 趨勢轉換
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class RateOfChange:
    """
    變動率
    
    計算方法:
    - ROC = (Close[i] - Close[i-n]) / Close[i-n] × 100
    
    交易訊號:
    - ROC > 0: 多頭動量
    - ROC < 0: 空頭動量
    - ROC 穿越 0: 趨勢轉換
    - ROC 極端值: 可能超買/超賣
    """
    
    def __init__(self, period: int = 14):
        """
        初始化
        
        Args:
            period: 回溯週期 (預設 14)
        """
        self.period = period
    
    def calculate(
        self,
        close: pd.Series,
        percentage: bool = True
    ) -> Dict[str, pd.Series]:
        """
        計算 ROC
        
        Args:
            close: 收盤價序列
            percentage: 是否返回百分比 (預設 True)
        
        Returns:
            Dict 含 roc, roc_ma, roc_histogram
        """
        prev_close = close.shift(self.period)
        
        # 計算 ROC
        roc = (close - prev_close) / (prev_close + 1e-10)
        
        if percentage:
            roc = roc * 100
        
        # ROC 移動平均
        roc_ma = roc.rolling(window=self.period).mean()
        
        # ROC 柱狀圖
        roc_histogram = roc - roc_ma
        
        # ROC 標準化
        roc_normalized = (roc - roc.mean()) / (roc.std() + 1e-10)
        
        return {
            "roc": roc,
            "roc_ma": roc_ma,
            "roc_histogram": roc_histogram,
            "roc_normalized": roc_normalized
        }
    
    def get_signal(
        self,
        roc: pd.Series,
        roc_ma: pd.Series,
        zero_threshold: float = 0
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            roc: ROC 序列
            roc_ma: ROC 移動平均
            zero_threshold: 零軸閾值
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=roc.index)
        
        # 買入訊號: ROC 上穿零軸
        buy_signal = (roc > zero_threshold) & (roc.shift(1) <= zero_threshold)
        signal[buy_signal] = 1
        
        # 賣出訊號: ROC 下穿零軸
        sell_signal = (roc < zero_threshold) & (roc.shift(1) >= zero_threshold)
        signal[sell_signal] = -1
        
        return signal
    
    def get_momentum_signal(
        self,
        roc: pd.Series,
        positive_threshold: float = 5,
        negative_threshold: float = -5
    ) -> pd.Series:
        """
        生成動量訊號
        
        Args:
            roc: ROC 序列
            positive_threshold: 正向動量閾值
            negative_threshold: 負向動量閾值
        
        Returns:
            動量訊號: 1=強多頭, 0.5=多頭, -0.5=空頭, -1=強空頭
        """
        signal = pd.Series(0, index=roc.index)
        
        # 強多頭
        signal[roc > positive_threshold * 2] = 1
        
        # 多頭
        signal[(roc > positive_threshold) & (roc <= positive_threshold * 2)] = 0.5
        
        # 空頭
        signal[(roc < negative_threshold) & (roc >= negative_threshold * 2)] = -0.5
        
        # 強空頭
        signal[roc < negative_threshold * 2] = -1
        
        return signal
    
    def get_histogram_signal(
        self,
        roc: pd.Series,
        roc_ma: pd.Series
    ) -> pd.Series:
        """
        生成柱狀圖訊號
        
        Args:
            roc: ROC 序列
            roc_ma: ROC 移動平均
        
        Returns:
            柱狀圖訊號: 1=柱狀圖上漲, -1=柱狀圖下跌
        """
        histogram = roc - roc_ma
        
        signal = pd.Series(0, index=roc.index)
        
        # 上漲
        signal[histogram > histogram.shift(1)] = 1
        
        # 下跌
        signal[histogram < histogram.shift(1)] = -1
        
        return signal


def calculate_roc(
    close: pd.Series,
    period: int = 14,
    percentage: bool = True
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算 ROC
    """
    roc_indicator = RateOfChange(period)
    return roc_indicator.calculate(close, percentage)
