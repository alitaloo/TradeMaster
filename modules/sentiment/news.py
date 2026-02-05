#!/usr/bin/env python3
"""
新聞情緒分析器 - News Sentiment Analyzer
從 NewsAPI 或 RSS 獲取新聞並分析情緒
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import requests
import logging

from .base import BaseSentimentAnalyzer, SentimentResult, SentimentType, ConfidenceLevel


logger = logging.getLogger(__name__)


class NewsSentimentAnalyzer(BaseSentimentAnalyzer):
    """新聞情緒分析器"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        language: str = "en",
        max_articles: int = 20,
        **kwargs
    ):
        """
        初始化新聞情緒分析器
        
        Args:
            api_key: NewsAPI 金鑰
            language: 語言 (預設 en)
            max_articles: 最大獲取文章數量
        """
        super().__init__(name="NewsSentimentAnalyzer", source="news_api")
        
        self.api_key = api_key
        self.language = language
        self.max_articles = max_articles
        
        # 簡單情緒字典 (可擴展為使用 NLP 模型)
        self._positive_words = {
            "bullish", "growth", "profit", "surge", "rally", "gain",
            "upbeat", "optimistic", "strong", "beat", "exceeded",
            "revenue", "dividend", "buyback", "upgrade", "breakthrough"
        }
        
        self._negative_words = {
            "bearish", "decline", "loss", "plunge", "crash", "fall",
            "downbeat", "pessimistic", "weak", "miss", "missed",
            "cut", "downgrade", "lawsuit", "investigation", "scandal"
        }
    
    def analyze_text(self, text: str) -> SentimentResult:
        """
        分析單段文本的情緒
        
        Args:
            text: 待分析的文本
            
        Returns:
            SentimentResult: 情緒分析結果
        """
        if not text:
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=self.source,
                metadata={"error": "Empty text"}
            )
        
        text_lower = text.lower()
        words = set(text_lower.split())
        
        # 計算情緒分數
        positive_count = len(words & self._positive_words)
        negative_count = len(words & self._negative_words)
        
        total_sentiment_words = positive_count + negative_count
        
        if total_sentiment_words == 0:
            # 無情緒詞，返回中性
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.3,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=self.source,
                text_sample=text[:100]
            )
        
        # 計算分數: (-1, 1) 範圍
        score = (positive_count - negative_count) / total_sentiment_words
        
        # 置信度基於情緒詞密度
        confidence = min(total_sentiment_words / 10, 1.0)
        
        # 判斷情緒類型
        if score > 0.2:
            sentiment = SentimentType.POSITIVE
        elif score < -0.2:
            sentiment = SentimentType.NEGATIVE
        else:
            sentiment = SentimentType.MIXED
        
        # 置信度等級
        if confidence > 0.7:
            confidence_level = ConfidenceLevel.HIGH
        elif confidence > 0.4:
            confidence_level = ConfidenceLevel.MEDIUM
        else:
            confidence_level = ConfidenceLevel.LOW
        
        return SentimentResult(
            sentiment=sentiment,
            confidence=confidence,
            confidence_level=confidence_level,
            score=score,
            source=self.source,
            text_sample=text[:100],
            metadata={
                "positive_count": positive_count,
                "negative_count": negative_count
            }
        )
    
    def analyze(self, text: str) -> SentimentResult:
        """分析文本 (接口統一)"""
        return self.analyze_text(text)
    
    def fetch_news(
        self,
        query: str = "stock market",
        from_date: Optional[str] = None,
        sort_by: str = "publishedAt"
    ) -> List[Dict[str, Any]]:
        """
        從 NewsAPI 獲取新聞
        
        Args:
            query: 搜尋關鍵詞
            from_date: 起始日期 (ISO format)
            sort_by: 排序方式 (publishedAt, relevancy, popularity)
            
        Returns:
            List[Dict]: 新聞文章列表
        """
        if not self.api_key:
            logger.warning("No NewsAPI key configured")
            return []
        
        url = "https://newsapi.org/v2/everything"
        
        params = {
            "q": query,
            "language": self.language,
            "sortBy": sort_by,
            "pageSize": self.max_articles,
            "apiKey": self.api_key
        }
        
        if from_date:
            params["from"] = from_date
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("status") == "ok":
                return data.get("articles", [])
            else:
                logger.error(f"NewsAPI error: {data.get('message')}")
                return []
                
        except requests.RequestException as e:
            logger.error(f"Failed to fetch news: {e}")
            return []
    
    def analyze_symbol(
        self,
        symbol: str,
        from_days_ago: int = 7
    ) -> SentimentResult:
        """
        分析特定股票的情緒
        
        Args:
            symbol: 股票代碼 (如 AAPL)
            from_days_ago: 往前幾天的新聞
            
        Returns:
            SentimentResult: 聚合情緒結果
        """
        from_date = (datetime.now() - timedelta(days=from_days_ago)).strftime("%Y-%m-%d")
        
        # 獲取新聞
        articles = self.fetch_news(
            query=symbol,
            from_date=from_date
        )
        
        if not articles:
            # 無新聞，返回中性結果
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=self.source,
                metadata={"error": "No news found"}
            )
        
        # 提取標題和描述
        texts = []
        for article in articles:
            title = article.get("title", "")
            description = article.get("description", "")
            
            if title:
                texts.append(title)
            if description:
                texts.append(description)
        
        # 批量分析
        results = [self.analyze_text(text) for text in texts[: self.max_articles * 2]]
        
        # 聚合結果
        aggregated = self.aggregate_results(results)
        aggregated.metadata = aggregated.metadata or {}
        aggregated.metadata["symbol"] = symbol
        aggregated.metadata["articles_count"] = len(articles)
        
        return aggregated
    
    def get_config_schema(self) -> Dict[str, Any]:
        """獲取配置 schema"""
        schema = super().get_config_schema()
        schema["properties"].update({
            "api_key": {"type": "string", "description": "NewsAPI key"},
            "language": {"type": "string", "default": "en"},
            "max_articles": {"type": "integer", "default": 20}
        })
        return schema
