#!/usr/bin/env python3
"""
市場情緒指標 - Market Sentiment Index
整合多種數據源，計算市場整體情緒指標
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field
import logging

from .base import BaseSentimentAnalyzer, SentimentResult, SentimentType, ConfidenceLevel
from .news import NewsSentimentAnalyzer
from .social import SocialMediaSentiment


logger = logging.getLogger(__name__)


@dataclass
class MarketSentimentConfig:
    """市場情緒配置"""
    news_weight: float = 0.4      # 新聞權重
    social_weight: float = 0.3    # 社群權重
    technical_weight: float = 0.3 # 技術面權重 (預留)
    use_news: bool = True
    use_social: bool = True
    symbols: List[str] = field(default_factory=lambda: ["SPY", "QQQ", "DIA"])


class MarketSentimentIndex(BaseSentimentAnalyzer):
    """市場情緒指標分析器"""
    
    def __init__(
        self,
        config: Optional[MarketSentimentConfig] = None,
        news_analyzer: Optional[NewsSentimentAnalyzer] = None,
        social_analyzer: Optional[SocialMediaSentiment] = None,
        **kwargs
    ):
        """
        初始化市場情緒指標
        
        Args:
            config: 市場情緒配置
            news_analyzer: 新聞分析器實例
            social_analyzer: 社群分析器實例
        """
        super().__init__(name="MarketSentimentIndex", source="market_sentiment")
        
        self.config = config or MarketSentimentConfig()
        
        # 初始化子分析器
        self.news_analyzer = news_analyzer or NewsSentimentAnalyzer()
        self.social_analyzer = social_analyzer or SocialMediaSentiment()
        
        # 緩存
        self._last_update: Optional[datetime] = None
        self._cached_sentiment: Optional[SentimentResult] = None
        self._cache_duration_seconds: int = 300  # 5分鐘緩存
    
    def analyze(self, text: str) -> SentimentResult:
        """
        分析文本 (通用接口)
        
        Note: 市場情緒指標通常不使用單一文本分析，
        而是使用 analyze_market() 方法獲取整體情緒
        """
        return self.analyze_market()
    
    def analyze_market(self) -> SentimentResult:
        """
        分析市場整體情緒
        
        整合新聞、社群媒體等多種數據源
        
        Returns:
            SentimentResult: 市場情緒結果
        """
        # 檢查緩存
        if self._is_cache_valid():
            logger.debug("Using cached sentiment")
            return self._cached_sentiment
        
        results: List[SentimentResult] = []
        weights: List[float] = []
        
        # 新聞情緒
        if self.config.use_news:
            for symbol in self.config.symbols:
                try:
                    news_result = self.news_analyzer.analyze_symbol(symbol)
                    results.append(news_result)
                    weights.append(self.config.news_weight / len(self.config.symbols))
                except Exception as e:
                    logger.error(f"Failed to get news sentiment for {symbol}: {e}")
        
        # 社群媒體情緒
        if self.config.use_social:
            for symbol in self.config.symbols:
                try:
                    social_result = self.social_analyzer.analyze_symbol_social(symbol)
                    results.append(social_result)
                    weights.append(self.config.social_weight / len(self.config.symbols))
                except Exception as e:
                    logger.error(f"Failed to get social sentiment for {symbol}: {e}")
        
        if not results:
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=self.source,
                metadata={"error": "No sentiment data available"}
            )
        
        # 加權平均
        weighted_score = sum(r.score * w for r, w in zip(results, weights))
        weighted_confidence = sum(r.confidence * w for r, w in zip(results, weights))
        
        # 歸一化分數到 (-1, 1)
        score = max(-1.0, min(1.0, weighted_score))
        
        # 判斷情緒
        if score > 0.2:
            sentiment = SentimentType.POSITIVE
        elif score < -0.2:
            sentiment = SentimentType.NEGATIVE
        else:
            sentiment = SentimentType.NEUTRAL
        
        # 置信度等級
        if weighted_confidence > 0.7:
            confidence_level = ConfidenceLevel.HIGH
        elif weighted_confidence > 0.4:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW
        
        # 構建結果
        result = SentimentResult(
            sentiment=sentiment,
            confidence=weighted_confidence,
            confidence_level=confidence_level,
            score=score,
            source=self.source,
            metadata={
                "symbols": self.config.symbols,
                "news_count": len([r for r in results if "news" in r.source]),
                "social_count": len([r for r in results if "social" in r.source]),
                "individual_sentiments": {
                    symbol: self._get_symbol_sentiment(symbol)
                    for symbol in self.config.symbols
                }
            }
        )
        
        # 更新緩存
        self._cached_sentiment = result
        self._last_update = datetime.now()
        
        return result
    
    def _get_symbol_sentiment(self, symbol: str) -> Dict[str, Any]:
        """獲取特定股票的情緒"""
        result = {
            "symbol": symbol,
            "news": None,
            "social": None,
            "combined": None
        }
        
        if self.config.use_news:
            try:
                news = self.news_analyzer.analyze_symbol(symbol)
                result["news"] = {
                    "sentiment": news.sentiment.value,
                    "score": news.score,
                    "confidence": news.confidence
                }
            except Exception as e:
                logger.error(f"Failed to get news for {symbol}: {e}")
        
        if self.config.use_social:
            try:
                social = self.social_analyzer.analyze_symbol_social(symbol)
                result["social"] = {
                    "sentiment": social.sentiment.value,
                    "score": social.score,
                    "confidence": social.confidence
                }
            except Exception as e:
                logger.error(f"Failed to get social for {symbol}: {e}")
        
        # 計算組合分數
        if result["news"] and result["social"]:
            combined_score = (
                result["news"]["score"] * self.config.news_weight +
                result["social"]["score"] * self.config.social_weight
            )
            result["combined"] = {
                "score": combined_score,
                "sentiment": "positive" if combined_score > 0.2 else "negative" if combined_score < -0.2 else "neutral"
            }
        elif result["news"]:
            result["combined"] = result["news"]
        elif result["social"]:
            result["combined"] = result["social"]
        
        return result
    
    def _is_cache_valid(self) -> bool:
        """檢查緩存是否有效"""
        if self._cached_sentiment is None or self._last_update is None:
            return False
        
        elapsed = (datetime.now() - self._last_update).total_seconds()
        return elapsed < self._cache_duration_seconds
    
    def clear_cache(self):
        """清除緩存"""
        self._cached_sentiment = None
        self._last_update = None
        logger.debug("Sentiment cache cleared")
    
    def get_market_regime(self) -> str:
        """
        判斷市場環境
        
        Returns:
            str: bull, bear, 或 neutral
        """
        sentiment = self.analyze_market()
        
        if sentiment.score > 0.3:
            return "bull"
        elif sentiment.score < -0.3:
            return "bear"
        else:
            return "neutral"
    
    def get_trading_signal(self) -> Dict[str, Any]:
        """
        獲取交易訊號
        
        Returns:
            Dict: 包含 signal, confidence, reason 等字段
        """
        sentiment = self.analyze_market()
        regime = self.get_market_regime()
        
        # 基本訊號邏輯
        if sentiment.score > 0.5 and sentiment.confidence > 0.6:
            signal = "LONG"
            reason = f"市場情緒強烈看漲 ({sentiment.score:.2f})"
        elif sentiment.score > 0.2:
            signal = "LONG"
            reason = f"市場情緒溫和看漲 ({sentiment.score:.2f})"
        elif sentiment.score < -0.5 and sentiment.confidence > 0.6:
            signal = "SHORT"
            reason = f"市場情緒強烈看跌 ({sentiment.score:.2f})"
        elif sentiment.score < -0.2:
            signal = "SHORT"
            reason = f"市場情緒溫和看跌 ({sentiment.score:.2f})"
        else:
            signal = "HOLD"
            reason = f"市場情緒中性 ({sentiment.score:.2f})"
        
        return {
            "signal": signal,
            "confidence": sentiment.confidence,
            "score": sentiment.score,
            "market_regime": regime,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_config_schema(self) -> Dict[str, Any]:
        """獲取配置 schema"""
        return {
            "type": "object",
            "properties": {
                "news_weight": {"type": "number", "default": 0.4},
                "social_weight": {"type": "number", "default": 0.3},
                "technical_weight": {"type": "number", "default": 0.3},
                "use_news": {"type": "boolean", "default": True},
                "use_social": {"type": "boolean", "default": True},
                "symbols": {"type": "array", "items": {"type": "string"}}
            }
        }
