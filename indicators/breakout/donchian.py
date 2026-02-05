# -*- coding: utf-8 -*-
"""
Donchian Channel (唐奇安通道)

突破策略指標:
- 價格突破 N 日高點買入
- 價格跌破 N 日低點賣出

發明人: Richard Donchian
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class DonchianChannel:
    """
    唐奇安通道指標
    
    計算方法:
    - Upper Band: N 日最高價
    - Lower Band: N 日最低價
    - Middle Band: (Upper + Lower) / 2
    
    交易訊號:
    - 買入: 價格突破 Upper Band
    - 賣出: 價格跌破 Lower Band
    """
    
    def __init__(self, period: int = 20):
        """
        初始化
        
        Args:
            period: 計算週期 (預設 20 日)
        """
        self.period = period
    
    def calculate(self, high: pd.Series, low: pd.Series) -> Dict[str, pd.Series]:
        """
        計算唐奇安通道
        
        Args:
            high: 最高價序列
            low: 最低價序列
        
        Returns:
            Dict 含 upper, middle, lower
        """
        upper = high.rolling(window=self.period).max()
        lower = low.rolling(window=self.period).min()
        middle = (upper + lower) / 2
        
        # 價格相對位置
        price_position = (high - lower) / (upper - lower + 1e-10)
        
        # 通道寬度
        channel_width = (upper - lower) / middle * 100
        
        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "price_position": price_position,
            "channel_width": channel_width
        }
    
    def get_signal(
        self,
        close: pd.Series,
        upper: pd.Series,
        lower: pd.Series
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            close: 收盤價序列
            upper: 上軌
            lower: 下軌
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=close.index)
        
        # 買入訊號: 價格突破上軌
        buy_signal = (close > upper) & (close.shift(1) <= upper.shift(1))
        signal[buy_signal] = 1
        
        # 賣出訊號: 價格跌破下軌
        sell_signal = (close < lower) & (close.shift(1) >= lower.shift(1))
        signal[sell_signal] = -1
        
        return signal
    
    def get_breakout_direction(
        self,
        close: pd.Series,
        upper: pd.Series,
        lower: pd.Series
    ) -> pd.Series:
        """
        判斷突破方向
        
        Returns:
            1=向上突破, -1=向下突破, 0=無突破
        """
        direction = pd.Series(0, index=close.index)
        
        # 向上突破
        upper_breakout = (close > upper) & (close.shift(1) <= upper.shift(1))
        direction[upper_breakout] = 1
        
        # 向下突破
        lower_breakout = (close < lower) & (close.shift(1) >= lower.shift(1))
        direction[lower_breakout] = -1
        
        return direction
    
    def calculate_adx_for_donchian(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        donchian_period: int = None
    ) -> pd.Series:
        """
        計算 Donchian ADX (趨勢強度)
        
        使用唐奇安通道寬度代替傳統 ADX
        """
        if donchian_period is None:
            donchian_period = self.period
        
        dc = self.calculate(high, low)
        channel_width = dc["channel_width"]
        
        # 標準化通道寬度
        width_ma = channel_width.rolling(window=20).mean()
        width_std = channel_width.rolling(window=20).std()
        
        donchian_adx = (channel_width - width_ma) / (width_std + 1e-10)
        
        return donchian_adx


def calculate_donchian(
    high: pd.Series,
    low: pd.Series,
    period: int = 20
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算唐奇安通道
    
    Args:
        high: 最高價
        low: 最低價
        period: 週期
    
    Returns:
        Dict 含 upper, middle, lower
    """
    dc = DonchianChannel(period)
    return dc.calculate(high, low)
