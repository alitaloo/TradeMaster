#!/usr/bin/env python3
"""
因素分析器 - 技術指標分析
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from loguru import logger


class FactorAnalyzer:
    """技術因素分析器"""
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化
        
        Args:
            weights: 因素權重 (默認: technical=0.4, momentum=0.35, support_resistance=0.25)
        """
        self.weights = weights or {
            "technical": 0.40,
            "momentum": 0.35,
            "support_resistance": 0.25
        }
    
    def analyze(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        分析所有因素
        
        Args:
            df: 價格數據 (包含 High, Low, Close, Volume)
            
        Returns:
            因素分數字典
        """
        if df is None or len(df) < 20:
            logger.warning("數據不足，無法進行因素分析")
            return self._default_factors()
        
        return {
            "technical_score": self._technical_score(df),
            "momentum": self._momentum_score(df),
            "support_resistance": self._support_resistance_score(df)
        }
    
    def _technical_score(self, df: pd.DataFrame) -> float:
        """計算技術指標分數"""
        try:
            # RSI
            rsi = self._calculate_rsi(df["Close"])
            rsi_score = rsi / 100 if rsi else 0.5
            
            # 移動平均線位置
            ma_position = self._ma_position(df)
            
            # MACD
            macd_score = self._macd_score(df)
            
            # 綜合技術分數
            tech_score = (rsi_score * 0.4 + ma_position * 0.3 + macd_score * 0.3)
            
            return round(tech_score, 3)
            
        except Exception as e:
            logger.error(f"技術分數計算錯誤: {e}")
            return 0.5
    
    def _momentum_score(self, df: pd.DataFrame) -> float:
        """計算動量分數"""
        try:
            # 價格動量
            returns = df["Close"].pct_change(periods=14)
            momentum = returns.iloc[-1] if len(returns) > 0 else 0
            
            # 成交量動量
            volume_ma = df["Volume"].rolling(14).mean()
            volume_ratio = df["Volume"].iloc[-1] / volume_ma.iloc[-1] if volume_ma.iloc[-1] > 0 else 1
            
            # 動量方向
            if momentum > 0.02:  # >2%
                momentum_label = "POSITIVE"
            elif momentum < -0.02:  # <-2%
                momentum_label = "NEGATIVE"
            else:
                momentum_label = "NEUTRAL"
            
            # 轉換為分數
            momentum_score = min(max(momentum * 10 + 0.5, 0), 1)
            momentum_score = momentum_score * volume_ratio * 0.5 + 0.25
            
            return round(momentum_score, 3)
            
        except Exception as e:
            logger.error(f"動量分數計算錯誤: {e}")
            return 0.5
    
    def _support_resistance_score(self, df: pd.DataFrame) -> float:
        """計算支撐阻力分數"""
        try:
            close = df["Close"].iloc[-1]
            high_20 = df["High"].rolling(20).max().iloc[-1]
            low_20 = df["Low"].rolling(20).min().iloc[-1]
            
            if high_20 == low_20:
                return 0.5
            
            # 價格在區間中的位置
            position = (close - low_20) / (high_20 - low_20)
            
            # 靠近支撐較好
            if position < 0.3:
                return round(0.7 - position * 0.3, 3)  # 靠近支撐
            elif position > 0.7:
                return round(0.3 + (1 - position) * 0.3, 3)  # 靠近阻力
            else:
                return round(0.5, 3)  # 中間位置
                
        except Exception as e:
            logger.error(f"支撐阻力分數計算錯誤: {e}")
            return 0.5
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """計算 RSI"""
        try:
            delta = prices.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            
            rs = gain / loss if loss.iloc[-1] != 0 else 0
            rsi = 100 - (100 / (1 + rs))
            
            return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
            
        except Exception:
            return 50
    
    def _ma_position(self, df: pd.DataFrame) -> float:
        """計算價格相對於均線的位置"""
        try:
            close = df["Close"].iloc[-1]
            sma_20 = df["Close"].rolling(20).mean().iloc[-1]
            sma_50 = df["Close"].rolling(50).mean().iloc[-1]
            
            if pd.isna(sma_20) or pd.isna(sma_50):
                return 0.5
            
            # 價格 > 短均線 > 長均線 = 上升趨勢
            if close > sma_20 > sma_50:
                return 0.8
            elif close < sma_20 < sma_50:
                return 0.2
            elif close > sma_20:
                return 0.6
            else:
                return 0.4
                
        except Exception:
            return 0.5
    
    def _macd_score(self, df: pd.DataFrame) -> float:
        """計算 MACD 信號"""
        try:
            exp1 = df["Close"].ewm(span=12, adjust=False).mean()
            exp2 = df["Close"].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            histogram = macd - signal
            
            # MACD > Signal 為看漲
            if histogram.iloc[-1] > 0:
                score = min(0.5 + abs(histogram.iloc[-1]) / histogram.abs().max() * 0.5, 0.9)
            else:
                score = max(0.5 - abs(histogram.iloc[-1]) / histogram.abs().max() * 0.5, 0.1)
            
            return round(score, 3)
            
        except Exception:
            return 0.5
    
    def _default_factors(self) -> Dict[str, float]:
        """返回默認因素分數"""
        return {
            "technical_score": 0.5,
            "momentum": "NEUTRAL",
            "support_resistance": 0.5
        }
