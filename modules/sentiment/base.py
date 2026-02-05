#!/usr/bin/env python3
"""
基礎情緒分析器 - Base Sentiment Analyzer
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime


class SentimentType(Enum):
    """情緒類型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class ConfidenceLevel(Enum):
    """置信度等級"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SentimentResult:
    """情緒分析結果"""
    sentiment: SentimentType
    confidence: float  # 0.0 - 1.0
    confidence_level: ConfidenceLevel
    score: float       # -1.0 (negative) to 1.0 (positive)
    source: str        # 數據來源
    text_sample: Optional[str] = None  # 範例文本
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return {
            "sentiment": self.sentiment.value,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "score": self.score,
            "source": self.source,
            "text_sample": self.text_sample,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class BaseSentimentAnalyzer:
    """基礎情緒分析器 (抽象類)"""
    
    def __init__(self, name: str, source: str):
        """
        初始化
        
        Args:
            name: 分析器名稱
            source: 數據來源標識
        """
        self.name = name
        self.source = source
    
    def analyze(self, text: str) -> SentimentResult:
        """
        分析單段文本的情緒
        
        Args:
            text: 待分析的文本
            
        Returns:
            SentimentResult: 情緒分析結果
        """
        raise NotImplementedError("Subclasses must implement analyze()")
    
    def batch_analyze(self, texts: list) -> list:
        """
        批量分析多段文本
        
        Args:
            texts: 文本列表
            
        Returns:
            list[SentimentResult]: 結果列表
        """
        return [self.analyze(text) for text in texts]
    
    def aggregate_results(self, results: list) -> SentimentResult:
        """
        聚合多個分析結果
        
        Args:
            results: SentimentResult 列表
            
        Returns:
            SentimentResult: 聚合後的結果
        """
        if not results:
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=self.source,
                metadata={"error": "No results to aggregate"}
            )
        
        # 計算平均分數
        avg_score = sum(r.score for r in results) / len(results)
        
        # 計算平均置信度
        avg_confidence = sum(r.confidence for r in results) / len(results)
        
        # 判斷整體情緒
        if avg_score > 0.2:
            sentiment = SentimentType.POSITIVE
        elif avg_score < -0.2:
            sentiment = SentimentType.NEGATIVE
        else:
            sentiment = SentimentType.NEUTRAL
        
        # 置信度等級
        if avg_confidence > 0.7:
            confidence_level = ConfidenceLevel.HIGH
        elif avg_confidence > 0.4:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW
        
        return SentimentResult(
            sentiment=sentiment,
            confidence=avg_confidence,
            confidence_level=confidence_level,
            score=avg_score,
            source=self.source,
            metadata={
                "count": len(results),
                "individual_results": [r.to_dict() for r in results[:5]]  # 只保留前5個
            }
        )
    
    def get_config_schema(self) -> Dict[str, Any]:
        """
        獲取配置 schema (用於配置文件)
        
        Returns:
            Dict: 配置 schema
        """
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "分析器名稱"},
                "source": {"type": "string", "description": "數據來源"}
            },
            "required": ["name", "source"]
        }
