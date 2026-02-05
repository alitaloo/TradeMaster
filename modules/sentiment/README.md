# 舆情分析模組 - Sentiment Module

用於市場情緒、新聞舆情、社群媒體分析。

## 模組結構

```
sentiment/
├── __init__.py         # 模組入口
├── base.py             # 基礎類和接口定義
├── news.py             # 新聞情緒分析
├── social.py           # 社群媒體情緒分析
└── market.py           # 市場情緒指標
```

## 使用方式

### 基礎情緒分析

```python
from modules.sentiment import NewsSentimentAnalyzer

# 初始化
analyzer = NewsSentimentAnalyzer(api_key="your-newsapi-key")

# 分析單段文本
result = analyzer.analyze_text("Apple reports record profits, stock surges")
print(result.sentiment)  # SentimentType.POSITIVE
print(result.score)      # 0.5
```

### 分析股票情緒

```python
# 分析 AAPL 的新聞情緒
result = analyzer.analyze_symbol("AAPL", from_days_ago=7)
print(f"Sentiment: {result.sentiment.value}")
print(f"Score: {result.score:.2f}")
print(f"Confidence: {result.confidence:.2%}")
```

### 市場情緒指標

```python
from modules.sentiment import MarketSentimentIndex, MarketSentimentConfig

# 自定義配置
config = MarketSentimentConfig(
    symbols=["AAPL", "MSFT", "GOOGL"],
    news_weight=0.5,
    social_weight=0.5
)

# 初始化市場情緒指標
market_sentiment = MarketSentimentIndex(config=config)

# 獲取市場情緒
result = market_sentiment.analyze_market()
print(f"Market Sentiment: {result.sentiment.value}")
print(f"Score: {result.score:.2f}")

# 獲取交易訊號
signal = market_sentiment.get_trading_signal()
print(f"Signal: {signal['signal']}")
print(f"Reason: {signal['reason']}")
```

### 整合進交易系統

```python
from modules.sentiment import MarketSentimentIndex

# 在策略中使用
class SentimentStrategy:
    def __init__(self):
        self.sentiment = MarketSentimentIndex()
    
    def generate_signal(self, indicators, data):
        signal = self.sentiment.get_trading_signal()
        
        # 結合其他指標做決策
        if signal["signal"] == "LONG" and some_other_condition:
            return Signal(signal="LONG", confidence=signal["confidence"])
        ...
```

## 配置

在 `config/settings.yaml` 中添加：

```yaml
sentiment:
  news:
    api_key: "your-newsapi-key"
    language: "en"
    max_articles: 20
  
  social:
    twitter_api_key: "your-twitter-key"
    twitter_api_secret: "your-twitter-secret"
    reddit_client_id: "your-reddit-id"
    reddit_client_secret: "your-reddit-secret"
  
  market:
    symbols:
      - SPY
      - QQQ
      - DIA
    news_weight: 0.4
    social_weight: 0.3
```

## API 金鑰

| 服務 | 獲取方式 |
|------|----------|
| NewsAPI | https://newsapi.org/register |
| Twitter | https://developer.twitter.com |
| Reddit | https://www.reddit.com/prefs/apps |

## 注意事項

- **免費配額**: NewsAPI 免費版有 100 requests/day 限制
- **API 延遲**: 社群媒體 API 可能需要額外配置
- **情緒準確性**: 基於關鍵詞匹配，可擴展為 ML 模型
