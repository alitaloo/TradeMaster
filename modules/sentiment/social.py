#!/usr/bin/env python3
"""
社群媒體情緒分析器 - Social Media Sentiment Analyzer
支援 Twitter/X, Reddit 等平台
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from .base import BaseSentimentAnalyzer, SentimentResult, SentimentType, ConfidenceLevel


logger = logging.getLogger(__name__)


class SocialMediaSentiment(BaseSentimentAnalyzer):
    """社群媒體情緒分析器"""
    
    # Twitter/X 特定的情緒詞彙
    TWITTER_POSITIVE = {
        "moon", "to the moon", "bullish", "long", "buy", "call",
        "gain", "profit", "winner", "breakout", "rally", "hodl"
    }
    
    TWITTER_NEGATIVE = {
        "bearish", "short", "put", "loss", "rip", "dump", "scam",
        "rug", "fail", "crash", "rekt", "fud", "dead"
    }
    
    # Reddit 特定的情緒詞彙
    REDDIT_POSITIVE = {
        " DD ", "dd", "bullish", "upvote", "helpful", "insight",
        "great", "excellent", "based", "chad", "moon", "green"
    }
    
    REDDIT_NEGATIVE = {
        "fud", "fud", "shill", "downvote", "bad", "terrible",
        "overvalued", "bubble", "crash", "dump", "sell"
    }
    
    def __init__(
        self,
        twitter_api_key: Optional[str] = None,
        twitter_api_secret: Optional[str] = None,
        reddit_client_id: Optional[str] = None,
        reddit_client_secret: Optional[str] = None,
        platform: str = "twitter",
        **kwargs
    ):
        """
        初始化社群媒體情緒分析器
        
        Args:
            twitter_api_key: Twitter API Key
            twitter_api_secret: Twitter API Secret
            reddit_client_id: Reddit Client ID
            reddit_client_secret: Reddit Client Secret
            platform: 平台 (twitter, reddit, all)
        """
        super().__init__(name="SocialMediaSentiment", source="social_media")
        
        self.twitter_api_key = twitter_api_key
        self.twitter_api_secret = twitter_api_secret
        self.reddit_client_id = reddit_client_id
        self.reddit_client_secret = reddit_client_secret
        self.platform = platform
    
    def analyze_tweet(self, text: str) -> SentimentResult:
        """分析 Twitter 推文情緒"""
        text_lower = text.lower()
        words = set(text_lower.split())
        
        # Twitter 特有分析
        positive_count = len(words & self.TWITTER_POSITIVE)
        negative_count = len(words & self.TWITTER_NEGATIVE)
        
        # 考慮 $ 標記的股票代碼 (通常表示關注，非情緒)
        # 考慮 # 主題標籤 (通常表示討論熱度)
        
        return self._compute_sentiment(
            text, positive_count, negative_count, "twitter"
        )
    
    def analyze_reddit_post(self, text: str) -> SentimentResult:
        """分析 Reddit 貼文情緒"""
        text_lower = text.lower()
        
        positive_count = sum(1 for word in self.REDDIT_POSITIVE if word in text_lower)
        negative_count = sum(1 for word in self.REDDIT_NEGATIVE if word in text_lower)
        
        return self._compute_sentiment(
            text, positive_count, negative_count, "reddit"
        )
    
    def _compute_sentiment(
        self,
        text: str,
        positive_count: int,
        negative_count: int,
        source_detail: str
    ) -> SentimentResult:
        """計算情緒分數"""
        total = positive_count + negative_count
        
        if total == 0:
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.2,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=f"{self.source}_{source_detail}",
                text_sample=text[:100]
            )
        
        score = (positive_count - negative_count) / total
        confidence = min(total / 5, 1.0)
        
        if score > 0.2:
            sentiment = SentimentType.POSITIVE
        elif score < -0.2:
            sentiment = SentimentType.NEGATIVE
        else:
            sentiment = SentimentType.MIXED
        
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
            source=f"{self.source}_{source_detail}",
            text_sample=text[:100],
            metadata={"positive_count": positive_count, "negative_count": negative_count}
        )
    
    def analyze(self, text: str) -> SentimentResult:
        """分析文本情緒 (通用接口)"""
        # 簡單的通用分析
        return self.analyze_tweet(text)
    
    def fetch_tweets(
        self,
        query: str,
        max_results: int = 100
    ) -> List[Dict[str, Any]]:
        """
        獲取 Twitter 推文 (需要 API Key)
        
        Args:
            query: 搜尋關鍵詞
            max_results: 最大結果數量
            
        Returns:
            List[Dict]: 推文列表
        """
        if not self.twitter_api_key:
            logger.warning("Twitter API key not configured")
            return []
        
        # TODO: 實現 Twitter API 調用
        # 使用 tweepy 或直接調用 Twitter API v2
        logger.info("Twitter API integration not yet implemented")
        return []
    
    def fetch_reddit_posts(
        self,
        subreddit: str,
        query: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        獲取 Reddit 貼文
        
        Args:
            subreddit: Subreddit 名稱
            query: 搜尋關鍵詞
            limit: 最大結果數量
            
        Returns:
            List[Dict]: 貼文列表
        """
        if not self.reddit_client_id:
            logger.warning("Reddit API credentials not configured")
            return []
        
        # TODO: 實現 Reddit API 調用
        # 使用 praw (Python Reddit API Wrapper)
        logger.info("Reddit API integration not yet implemented")
        return []
    
    def analyze_symbol_social(
        self,
        symbol: str,
        platforms: List[str] = None
    ) -> SentimentResult:
        """
        分析特定股票在社群媒體的情緒
        
        Args:
            symbol: 股票代碼
            platforms: 平台列表
            
        Returns:
            SentimentResult: 聚合情緒結果
        """
        platforms = platforms or ["twitter"]
        
        all_results = []
        
        for platform in platforms:
            if platform == "twitter":
                tweets = self.fetch_tweets(f"${symbol}")
                results = [self.analyze_tweet(t.get("text", "")) for t in tweets]
                all_results.extend(results)
            elif platform == "reddit":
                posts = self.fetch_reddit_posts("wallstreetbets", symbol)
                results = [self.analyze_reddit_post(p.get("title", "")) for p in posts]
                all_results.extend(results)
        
        if not all_results:
            return SentimentResult(
                sentiment=SentimentType.NEUTRAL,
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                score=0.0,
                source=self.source,
                metadata={"error": "No social media data available"}
            )
        
        aggregated = self.aggregate_results(all_results)
        aggregated.metadata = aggregated.metadata or {}
        aggregated.metadata["symbol"] = symbol
        aggregated.metadata["platforms"] = platforms
        
        return aggregated
    
    def get_config_schema(self) -> Dict[str, Any]:
        """獲取配置 schema"""
        schema = super().get_config_schema()
        schema["properties"].update({
            "twitter_api_key": {"type": "string"},
            "twitter_api_secret": {"type": "string"},
            "reddit_client_id": {"type": "string"},
            "reddit_client_secret": {"type": "string"},
            "platform": {"type": "string", "default": "twitter"}
        })
        return schema
