#!/usr/bin/env python3
"""
概率計算器 - 根據因素計算預測概率
"""

from typing import Dict, Optional, Literal
from dataclasses import dataclass
from loguru import logger


@dataclass
class PredictionResult:
    """預測結果"""
    symbol: str
    direction: str  # UP/DOWN/VOLATILITY
    threshold: float  # 漲跌幅度百分比
    period_days: int
    probability: float
    confidence: str  # HIGH/MEDIUM/LOW
    factors: Dict[str, float]
    timestamp: str


class ProbabilityCalculator:
    """概率計算器"""
    
    # 默認權重配置
    DEFAULT_WEIGHTS = {
        "alpha": 0.40,   # 技術指標
        "beta": 0.35,    # 動量
        "gamma": 0.25    # 支撐阻力
    }
    
    # 置信度閾值
    CONFIDENCE_THRESHOLDS = {
        "HIGH": 0.70,
        "MEDIUM": 0.50,
        "LOW": 0.30
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        初始化
        
        Args:
            weights: 權重配置 (alpha, beta, gamma)
        """
        self.weights = {**self.DEFAULT_WEIGHTS, **(weights or {})}
        self._validate_weights()
    
    def _validate_weights(self):
        """驗證權重總和為 1"""
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.001:
            logger.warning(f"權重總和 {total} 不為 1，已調整")
            # 自動調整
            for k in self.weights:
                self.weights[k] /= total
    
    def calculate(
        self,
        factors: Dict[str, float],
        direction: Literal["UP", "DOWN", "VOLATILITY"],
        threshold: float,
        period_days: int
    ) -> PredictionResult:
        """
        計算預測概率
        
        Args:
            factors: 因素分數字典
            direction: 預測方向
            threshold: 漲跌幅度百分比
            period_days: 天數
            
        Returns:
            PredictionResult
        """
        try:
            # 提取因素值
            technical = factors.get("technical_score", 0.5)
            momentum_score = factors.get("momentum", 0.5)
            support_resistance = factors.get("support_resistance", 0.5)
            
            # 處理 momentum 可能是字串
            if isinstance(momentum_score, str):
                momentum_score = self._momentum_to_score(momentum_score)
            
            # 基礎概率計算
            base_probability = (
                self.weights["alpha"] * technical +
                self.weights["beta"] * momentum_score +
                self.weights["gamma"] * support_resistance
            )
            
            # 根據方向調整
            if direction == "UP":
                probability = base_probability
            elif direction == "DOWN":
                probability = 1 - base_probability
            else:  # VOLATILITY
                # 波動性預測：遠離 0.5 的概率更高
                distance_from_middle = abs(base_probability - 0.5) * 2
                probability = 0.5 + distance_from_middle * 0.3
            
            # 根據閾值調整置信度
            threshold_factor = self._threshold_adjustment(threshold)
            probability = probability * threshold_factor
            
            # 限制概率範圍
            probability = min(max(probability, 0.01), 0.99)
            
            # 計算置信度
            confidence = self._calculate_confidence(probability)
            
            # 計算各因素貢獻
            factor_details = {
                "technical_score": technical,
                "momentum": momentum_score if isinstance(momentum_score, (int, float)) else 0.5,
                "support_resistance": support_resistance,
                "weights_used": self.weights.copy()
            }
            
            return PredictionResult(
                symbol="",  # 稍後填充
                direction=direction,
                threshold=threshold,
                period_days=period_days,
                probability=round(probability, 3),
                confidence=confidence,
                factors=factor_details,
                timestamp=self._get_timestamp()
            )
            
        except Exception as e:
            logger.error(f"概率計算錯誤: {e}")
            return self._default_result(direction, threshold, period_days)
    
    def _momentum_to_score(self, momentum: str) -> float:
        """將動量標籤轉換為分數"""
        mapping = {
            "POSITIVE": 0.75,
            "NEUTRAL": 0.50,
            "NEGATIVE": 0.25
        }
        return mapping.get(momentum, 0.5)
    
    def _threshold_adjustment(self, threshold: float) -> float:
        """
        根據閾值調整概率
        較大的閾值應該有較低的概率
        """
        if threshold <= 5:
            return 1.0
        elif threshold <= 10:
            return 0.95
        elif threshold <= 20:
            return 0.85
        elif threshold <= 30:
            return 0.70
        else:
            return 0.50
    
    def _calculate_confidence(self, probability: float) -> str:
        """計算置信度等級"""
        # 概率越接近 0 或 1，置信度越高
        distance_from_middle = abs(probability - 0.5) * 2
        
        if distance_from_middle >= 0.4 and probability >= self.CONFIDENCE_THRESHOLDS["HIGH"]:
            return "HIGH"
        elif distance_from_middle >= 0.2 and probability >= self.CONFIDENCE_THRESHOLDS["MEDIUM"]:
            return "MEDIUM"
        else:
            return "LOW"
    
    def _get_timestamp(self) -> str:
        """獲取當前時間戳"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def _default_result(
        self,
        direction: str,
        threshold: float,
        period_days: int
    ) -> PredictionResult:
        """返回默認結果"""
        return PredictionResult(
            symbol="",
            direction=direction,
            threshold=threshold,
            period_days=period_days,
            probability=0.5,
            confidence="LOW",
            factors={
                "technical_score": 0.5,
                "momentum": 0.5,
                "support_resistance": 0.5
            },
            timestamp=self._get_timestamp()
        )
    
    def get_weights_info(self) -> Dict[str, float]:
        """獲取當前權重配置"""
        return self.weights.copy()
