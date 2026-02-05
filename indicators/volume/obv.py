# -*- coding: utf-8 -*-
"""
On-Balance Volume (OBV / 能量潮)

成交量指標:
- 上漲日: OBV += Volume
- 下跌日: OBV -= Volume
- 平盤日: OBV 不變

發明人: Joseph Granville

交易訊號:
- OBV 上漲 + 價格上漲: 確認多頭
- OBV 下跌 + 價格上漲: 背離 (可能回調)
- OBV 下跌 + 價格下跌: 確認空頭
- OBV 上漲 + 價格下跌: 背離 (可能反彈)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class OBV:
    """
    能量潮
    
    計算方法:
    - 若 Close[i] > Close[i-1]: OBV[i] = OBV[i-1] + Volume[i]
    - 若 Close[i] < Close[i-1]: OBV[i] = OBV[i-1] - Volume[i]
    - 若 Close[i] = Close[i-1]: OBV[i] = OBV[i-1]
    
    交易訊號:
    - 價格上漲 + OBV 上漲: 確認
    - 價格上漲 + OBV 下跌: 負背離 (可能回調)
    - 價格下跌 + OBV 下跌: 確認
    - 價格上漲 + OBV 下跌: 正背離 (可能反彈)
    """
    
    def __init__(self):
        """初始化"""
        pass
    
    def calculate(
        self,
        close: pd.Series,
        volume: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算 OBV
        
        Args:
            close: 收盤價序列
            volume: 成交量序列
        
        Returns:
            Dict 含 obv, obv_ma, obv_slope
        """
        obv = pd.Series(0.0, index=close.index)
        
        # 計算 OBV
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        
        # OBV 移動平均
        obv_ma = obv.rolling(window=20).mean()
        
        # OBV 斜率
        obv_slope = obv.diff() / close.diff()
        
        # OBV 標準化
        obv_normalized = (obv - obv_ma) / (obv.std() + 1e-10)
        
        return {
            "obv": obv,
            "obv_ma": obv_ma,
            "obv_slope": obv_slope,
            "obv_normalized": obv_normalized
        }
    
    def get_confirmed_signal(
        self,
        close: pd.Series,
        obv: pd.Series
    ) -> pd.Series:
        """
        生成確認訊號
        
        Args:
            close: 收盤價
            obv: OBV 序列
        
        Returns:
            確認訊號: 1=多頭確認, -1=空頭確認, 0=無確認
        """
        signal = pd.Series(0, index=close.index)
        
        close_change = close.diff()
        obv_change = obv.diff()
        
        # 多頭確認: 價格上漲 + OBV 上漲
        bull_confirmed = (close_change > 0) & (obv_change > 0)
        signal[bull_confirmed] = 1
        
        # 空頭確認: 價格下跌 + OBV 下跌
        bear_confirmed = (close_change < 0) & (obv_change < 0)
        signal[bear_confirmed] = -1
        
        return signal
    
    def get_divergence_signal(
        self,
        close: pd.Series,
        obv: pd.Series,
        lookback: int = 20
    ) -> pd.Series:
        """
        生成背離訊號
        
        Args:
            close: 收盤價
            obv: OBV 序列
            lookback: 回溯週期
        
        Returns:
            背離訊號: 1=正背離, -1=負背離, 0=無背離
        """
        signal = pd.Series(0, index=close.index)
        
        close_change = close.diff()
        obv_change = obv.diff()
        
        # 正背離: 價格下跌但 OBV 上漲
        positive_divergence = (close_change < 0) & (obv_change > 0)
        signal[positive_divergence] = 1
        
        # 負背離: 價格上漲但 OBV 下跌
        negative_divergence = (close_change > 0) & (obv_change < 0)
        signal[negative_divergence] = -1
        
        return signal
    
    def get_trend_signal(
        self,
        obv: pd.Series,
        obv_ma: pd.Series
    ) -> pd.Series:
        """
        生成 OBV 趨勢訊號
        
        Returns:
            趨勢訊號: 1=OBV 在 MA 之上, -1=OBV 在 MA 之下, 0=無趨勢
        """
        signal = pd.Series(0, index=obv.index)
        
        signal[obv > obv_ma] = 1
        signal[obv < obv_ma] = -1
        
        return signal


def calculate_obv(
    close: pd.Series,
    volume: pd.Series
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算 OBV
    """
    obv_indicator = OBV()
    return obv_indicator.calculate(close, volume)
