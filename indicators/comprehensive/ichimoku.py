# -*- coding: utf-8 -*-
"""
Ichimoku Kinko Hyo (一目均衡表 / 雲圖)

綜合技術分析指標:
- 5 條線綜合判斷趨勢、支撐阻力

發明人: Goichi Hosoda (細田悟一)

組成線:
1. Tenkan-sen (轉換線): (9日高 + 9日低) / 2
2. Kijun-sen (基準線): (26日高 + 26日低) / 2
3. Senkou Span A (先行帶 A): (轉換線 + 基準線) / 2，提前 26 日繪製
4. Senkou Span B (先行帶 B): (52日高 + 52日低) / 2，提前 26 日繪製
5. Chikou Span (延遲線): 收盤價，提前 26 日繪製

雲帶 (Kumo):
- 先行帶 A > 先行帶 B: 多頭雲 (支撐)
- 先行帶 B > 先行帶 A: 空頭雲 (阻力)

交易訊號:
- 買入: 價格突破雲帶上緣 或 轉換線上穿基準線
- 賣出: 價格跌破雲帶下緣 或 轉換線下穿基準線
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional


class IchimokuCloud:
    """
    一目均衡表
    
    參數 (日線標準參數):
    - tenkan_period: 9 日
    - kijun_period: 26 日
    - senkou_period: 52 日
    - senkou_shift: 26 日 (先行偏移)
    """
    
    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_period: int = 52,
        senkou_shift: int = 26
    ):
        """
        初始化
        
        Args:
            tenkan_period: 轉換線週期 (預設 9)
            kijun_period: 基準線週期 (預設 26)
            senkou_period: 先行帶週期 (預設 52)
            senkou_shift: 先行偏移 (預設 26)
        """
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_period = senkou_period
        self.senkou_shift = senkou_shift
    
    def calculate(
        self,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        計算一目均衡表
        
        Args:
            high: 最高價序列
            low: 最低價序列
            close: 收盤價序列
        
        Returns:
            Dict 含所有一目均衡表線
        """
        # 轉換線 (Tenkan-sen)
        tenkan = (high.rolling(window=self.tenkan_period).max() +
                  low.rolling(window=self.tenkan_period).min()) / 2
        
        # 基準線 (Kijun-sen)
        kijun = (high.rolling(window=self.kijun_period).max() +
                 low.rolling(window=self.kijun_period).min()) / 2
        
        # 先行帶 A (Senkou Span A)
        senkou_span_a = ((tenkan + kijun) / 2).shift(self.senkou_shift)
        
        # 先行帶 B (Senkou Span B)
        senkou_span_b = ((high.rolling(window=self.senkou_period).max() +
                          low.rolling(window=self.senkou_period).min()) / 2).shift(self.senkou_shift)
        
        # 延遲線 (Chikou Span)
        chikou = close.shift(-self.senkou_shift)
        
        # 雲帶狀態
        cloud_bullish = senkou_span_a > senkou_span_b
        cloud_bearish = senkou_span_a < senkou_span_b
        
        # 價格相對雲帶位置
        cloud_top = pd.concat([senkou_span_a, senkou_span_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([senkou_span_a, senkou_span_b], axis=1).min(axis=1)
        
        price_vs_cloud = pd.Series(0, index=close.index)
        price_vs_cloud[close > cloud_top] = 1  # 價格在雲之上
        price_vs_cloud[close < cloud_bottom] = -1  # 價格在雲之下
        
        return {
            "tenkan": tenkan,
            "kijun": kijun,
            "senkou_span_a": senkou_span_a,
            "senkou_span_b": senkou_span_b,
            "chikou": chikou,
            "cloud_top": cloud_top,
            "cloud_bottom": cloud_bottom,
            "cloud_bullish": cloud_bullish,
            "cloud_bearish": cloud_bearish,
            "price_vs_cloud": price_vs_cloud
        }
    
    def get_cross_signal(
        self,
        tenkan: pd.Series,
        kijun: pd.Series
    ) -> pd.Series:
        """
        生成轉換線/基準線交叉訊號
        
        Returns:
            交叉訊號: 1=買入 (TK 金叉), -1=賣出 (TK 死叉), 0=無
        """
        signal = pd.Series(0, index=tenkan.index)
        
        # 買入: 轉換線上穿基準線 (TK 金叉)
        golden_cross = (tenkan > kijun) & (tenkan.shift(1) <= kijun.shift(1))
        signal[golden_cross] = 1
        
        # 賣出: 轉換線下穿基準線 (TK 死叉)
        death_cross = (tenkan < kijun) & (tenkan.shift(1) >= kijun.shift(1))
        signal[death_cross] = -1
        
        return signal
    
    def get_cloud_signal(
        self,
        close: pd.Series,
        senkou_span_a: pd.Series,
        senkou_span_b: pd.Series
    ) -> pd.Series:
        """
        生成雲帶突破訊號
        
        Returns:
            雲帶訊號: 1=突破雲带上緣, -1=跌破雲帶下緣, 0=無
        """
        signal = pd.Series(0, index=close.index)
        
        cloud_top = pd.concat([senkou_span_a, senkou_span_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([senkou_span_a, senkou_span_b], axis=1).min(axis=1)
        
        # 向上突破雲帶
        breakout_up = (close > cloud_top) & (close.shift(1) <= cloud_top.shift(1))
        signal[breakout_up] = 1
        
        # 向下突破雲帶
        breakout_down = (close < cloud_bottom) & (close.shift(1) >= cloud_bottom.shift(1))
        signal[breakout_down] = -1
        
        return signal
    
    def get_trend_signal(
        self,
        close: pd.Series,
        tenkan: pd.Series,
        kijun: pd.Series,
        senkou_span_a: pd.Series,
        senkou_span_b: pd.Series
    ) -> pd.Series:
        """
        生成綜合趨勢訊號
        
        Returns:
            趨勢訊號: 5=強多頭, 4=多頭, 3=中性偏多, 2=中性, 1=中性偏空, 0=中性, -1=中性偏空, -2=空頭, -3=偏空, -4=空頭, -5=強空頭
        """
        signal = pd.Series(2, index=close.index)  # 預設中性
        
        # 雲帶趨勢
        cloud_trend = pd.Series(0, index=close.index)
        cloud_trend[senkou_span_a > senkou_span_b] = 1  # 多頭雲
        cloud_trend[senkou_span_a < senkou_span_b] = -1  # 空頭雲
        
        # TK 交叉
        tk_trend = pd.Series(0, index=close.index)
        tk_trend[tenkan > kijun] = 1
        tk_trend[tenkan < kijun] = -1
        
        # 價格相對雲帶
        price_position = pd.Series(0, index=close.index)
        price_position[close > senkou_span_a] = 1
        price_position[close > senkou_span_b] = 1
        price_position[close < senkou_span_a] = -1
        price_position[close < senkou_span_b] = -1
        
        # 延遲線
        chikou_trend = pd.Series(0, index=close.index)
        chikou_trend[close > close.shift(26)] = 1
        chikou_trend[close < close.shift(26)] = -1
        
        # 綜合評分 (0-10 分)
        score = (
            cloud_trend * 2 +  # 雲帶權重 2
            tk_trend * 2 +     # TK 交叉權重 2
            price_position * 2 +  # 價格位置權重 2
            chikou_trend * 2     # 延遲線權重 2
        ) / 8 * 5  # 轉換為 -5 到 5
        
        return score


def calculate_ichimoku(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    tenkan_period: int = 9,
    kijun_period: int = 26,
    senkou_period: int = 52
) -> Dict[str, pd.Series]:
    """
    便捷函數: 計算一目均衡表
    """
    ichimoku = IchimokuCloud(tenkan_period, kijun_period, senkou_period)
    return ichimoku.calculate(high, low, close)
