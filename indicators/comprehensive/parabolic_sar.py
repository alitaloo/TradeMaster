# -*- coding: utf-8 -*-
"""
Parabolic SAR (拋物線指標)

趨勢 + 止損指標:
- SAR: Stop and Reverse

發明人: J. Welles Wilder

計算方法:
- SAR[i] = SAR[i-1] + AF × (EP - SAR[i-1])
- AF: Acceleration Factor (加速因子)
- EP: Extreme Point (極值點)

交易訊號:
- SAR 在價格下方: 多頭趨勢
- SAR 在價格上方: 空頭趨勢
- SAR 穿越價格: 趨勢反轉
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class ParabolicSAR:
    """
    拋物線指標
    
    特點:
    - 內建止損邏輯
    - 趨勢追蹤指標
    - 可作為移動止損使用
    
    參數:
    - acceleration: 加速因子 (預設 0.02)
    - maximum: AF 最大值 (預設 0.20)
    """
    
    def __init__(
        self,
        acceleration: float = 0.02,
        maximum: float = 0.20
    ):
        """
        初始化
        
        Args:
            acceleration: 加速因子 (預設 0.02)
            maximum: AF 最大值 (預設 0.20)
        """
        self.acceleration = acceleration
        self.maximum = maximum
    
    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算拋物線指標
        
        Args:
            high: 最高價序列
            low: 最低價序列
            close: 收盤價序列
        
        Returns:
            Dict 含 sar, ep, af, trend
        """
        n = len(close)
        
        # 初始化
        sar = pd.Series(np.nan, index=close.index)
        af = pd.Series(self.acceleration, index=close.index)
        ep = pd.Series(np.nan, index=close.index)  # 極值點
        
        # 趨勢: 1=多頭, -1=空頭
        trend = pd.Series(0, index=close.index)
        
        # 初始化第一筆
        if close[1] > close[0]:
            trend.iloc[0] = 1
            sar.iloc[0] = low.iloc[0]
            ep.iloc[0] = high.iloc[0]
        else:
            trend.iloc[0] = -1
            sar.iloc[0] = high.iloc[0]
            ep.iloc[0] = low.iloc[0]
        
        # 計算拋物線 SAR
        for i in range(1, n):
            if trend.iloc[i-1] == 1:  # 多頭趨勢
                # SAR 在前一根 K 線的 SAR 和最低價之間
                sar.iloc[i] = min(
                    sar.iloc[i-1],
                    low.iloc[i-1],
                    low.iloc[i-2] if i > 1 else low.iloc[i-1]
                )
                
                # 更新極值點
                if high.iloc[i] > ep.iloc[i-1]:
                    ep.iloc[i] = high.iloc[i]
                    af.iloc[i] = min(
                        af.iloc[i-1] + self.acceleration,
                        self.maximum
                    )
                else:
                    ep.iloc[i] = ep.iloc[i-1]
                    af.iloc[i] = af.iloc[i-1]
                
                # 檢查是否反轉
                if close.iloc[i] < sar.iloc[i]:
                    trend.iloc[i] = -1
                    sar.iloc[i] = ep.iloc[i-1]
                    ep.iloc[i] = low.iloc[i]
                    af.iloc[i] = self.acceleration
                else:
                    trend.iloc[i] = 1
            
            else:  # 空頭趨勢
                # SAR 在前一根 K 線的 SAR 和最高價之間
                sar.iloc[i] = max(
                    sar.iloc[i-1],
                    high.iloc[i-1],
                    high.iloc[i-2] if i > 1 else high.iloc[i-1]
                )
                
                # 更新極值點
                if low.iloc[i] < ep.iloc[i-1]:
                    ep.iloc[i] = low.iloc[i]
                    af.iloc[i] = min(
                        af.iloc[i-1] + self.acceleration,
                        self.maximum
                    )
                else:
                    ep.iloc[i] = ep.iloc[i-1]
                    af.iloc[i] = af.iloc[i-1]
                
                # 檢查是否反轉
                if close.iloc[i] > sar.iloc[i]:
                    trend.iloc[i] = 1
                    sar.iloc[i] = ep.iloc[i-1]
                    ep.iloc[i] = high.iloc[i]
                    af.iloc[i] = self.acceleration
                else:
                    trend.iloc[i] = -1
        
        # SAR 相對價格位置
        sar_position = pd.Series(0, index=close.index)
        sar_position[close > sar] = 1  # SAR 在價格下方 = 多頭
        sar_position[close < sar] = -1  # SAR 在價格上方 = 空頭
        
        # SAR 距離
        sar_distance = (sar - close) / close * 100
        
        return {
            "sar": sar,
            "ep": ep,
            "af": af,
            "trend": trend,
            "sar_position": sar_position,
            "sar_distance": sar_distance
        }
    
    def get_signal(
        self,
        close: pd.Series,
        sar: pd.Series,
        trend: pd.Series
    ) -> pd.Series:
        """
        生成交易訊號
        
        Args:
            close: 收盤價
            sar: SAR 序列
            trend: 趨勢序列
        
        Returns:
            訊號序列: 1=買入, -1=賣出, 0=持有
        """
        signal = pd.Series(0, index=close.index)
        
        # SAR 反轉訊號
        reversal = (trend != trend.shift(1)) & (trend != 0)
        signal[reversal] = trend[reversal]
        
        # SAR 在價格下方 + 價格上漲 = 多頭持有
        # SAR 在價格上方 + 價格下跌 = 空頭持有
        # 這裡只輸出反轉訊號
        
        return signal
    
    def get_trailing_stop(
        self,
        sar: pd.Series,
        trend: pd.Series
    ) -> pd.Series:
        """
        獲取移動止損價位
        
        Returns:
            止損價位序列
        """
        return sar
    
    def get_reversal_count(
        self,
        trend: pd.Series,
        lookback: int = 5
    ) -> pd.Series:
        """
        計算近期反轉次數
        
        Args:
            trend: 趨勢序列
            lookback: 回溯週期
        
        Returns:
            反轉次數序列
        """
        reversal = (trend != trend.shift(1)) & (trend != 0)
        reversal_count = reversal.rolling(window=lookback).sum()
        
        return reversal_count


def calculate_parabolic_sar(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    acceleration: float = 0.02,
    maximum: float = 0.20
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算拋物線指標
    """
    psar = ParabolicSAR(acceleration, maximum)
    return psar.calculate(high, low, close)
