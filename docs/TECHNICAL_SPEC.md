# TradeMaster v2.0 技術方案

## 一、系統架構

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TradeMaster v2.0                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐     │
│  │  定時任務引擎     │───→│           核心處理管線               │     │
│  │  (每5分鐘)      │    │  ┌─────────┐  ┌─────────┐         │     │
│  └─────────────────┘    │  │ 數據獲取  │→│ 指標計算 │         │     │
│                          │  └─────────┘  └─────────┘         │     │
│  ┌─────────────────┐    │       │              │              │     │
│  │  指令輸入引擎     │───→│       ▼              ▼              │     │
│  │  (預測指令)      │    │  ┌─────────────────────────────────┐│     │
│  └─────────────────┘    │  │         策略引擎                  ││     │
│                          │  │  (多策略插件 + 風險控制)          ││     │
│  ┌─────────────────┐    │  └─────────────────────────────────┘│     │
│  │  新聞/輿情引擎    │───→│               │                    │     │
│  │  (每30分鐘)      │    │               ▼                    │     │
│  └─────────────────┘    │  ┌─────────────────────────────────┐│     │
│                          │  │         安全閘道                   ││     │
│                          │  │  (金額/頻率/熔斷檢查)              ││     │
│                          │  └─────────────────────────────────┘│     │
│                          │               │                    │     │
│                          └───────────────┼──────────────────┘     │
│                                      │                              │
│                                      ▼                              │
│                    ┌─────────────────────────────────┐            │
│                    │           通知系統               │            │
│                    │  (Telegram/Email/Logs)         │            │
│                    └─────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

## 二、模組設計

### 2.1 價格預測模組 (Prediction Module)

**功能：** 根據指令計算價格變動概率

**輸入格式：** `代碼/方向/幅度/時間`

| 參數 | 說明 | 範例 |
|------|------|------|
| 代碼 | 股票代號 | TSLA, AAPL |
| 方向 | 📈 上漲 / 📉 下跌 / 📊 波動 | 📈 |
| 幅度 | 百分比 | 10, 5, 15 |
| 時間 | 天數 | 5天, 1天, 30天 |

**輸出格式：**
```json
{
  "symbol": "TSLA",
  "direction": "UP",
  "threshold": 10,
  "period_days": 5,
  "probability": 0.68,
  "confidence": "HIGH",
  "factors": {
    "technical_score": 0.72,
    "momentum": "POSITIVE",
    "support_resistance": 0.65
  },
  "timestamp": "2026-02-04T00:00:00Z"
}
```

**計算方法：**
```
概率 = α × 技術指標分數 + β × 動量分數 + γ × 支撐阻力分數
其中 α=0.4, β=0.35, γ=0.25
```

### 2.2 新聞/輿情模組 (Sentiment Module)

**功能：** 獲取新聞並計算情緒分數

**配置：**
```yaml
sentiment:
  enabled: false    # 預設關閉
  update_interval: 1800  # 1800秒 = 30分鐘
  sources:
    news_api: true   # NewsAPI.org (免費)
    google_trends: false  # Google Trends
  cache_ttl: 3600   # 緩存1小時
```

**數據來源：**
| 來源 | 類型 | 限制 |
|------|------|------|
| NewsAPI.org | 新聞標題/摘要 | 免費100條/天 |
| Google Trends | 熱門關鍵詞 | 無限制 |

**輸出格式：**
```json
{
  "symbol": "TSLA",
  "sentiment_score": 0.65,
  "sentiment_label": "POSITIVE",
  "articles": [
    {
      "title": "Tesla announces new AI chip",
      "source": "TechCrunch",
      "published_at": "2026-02-03T10:00:00Z",
      "url": "https://..."
    }
  ],
  "keywords": ["AI", "autonomous", "EV"],
  "confidence": 0.72,
  "cached": false,
  "next_update": "2026-02-04T00:30:00Z"
}
```

**情緒分數計算：**
```
sentiment_score = (positive_count - negative_count) / total_count
範圍: -1 (極度負面) 到 +1 (極度正面)
```

### 2.3 整合架構

```
┌─────────────────────────────────────────────────────────────────────┐
│                        策略引擎整合                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐         ┌──────────────────┐                 │
│  │   技術指標模組     │         │    輿情指標模組    │                 │
│  │ RSI/EMA/MACD... │         │ sentiment_score  │                 │
│  └────────┬─────────┘         └────────┬─────────┘                 │
│           │                              │                          │
│           └──────────┬─────────────────┘                          │
│                      │                                              │
│                      ▼                                              │
│           ┌─────────────────────┐                                 │
│           │   策略信號生成器      │                                 │
│           │   (可配置權重)       │                                 │
│           │                      │                                 │
│           │ confidence =         │                                 │
│           │   w1×RSI +          │                                 │
│           │   w2×EMA +           │                                 │
│           │   w3×MACD +         │                                 │
│           │   w4×sentiment      │                                 │
│           └─────────────────────┘                                 │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 三、數據庫結構

### 3.1 預測結果表
```sql
CREATE TABLE predictions (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,  -- UP/DOWN
    threshold REAL NOT NULL,   -- 漲跌幅度百分比
    period_days INTEGER NOT NULL,
    probability REAL NOT NULL,
    confidence TEXT,          -- HIGH/MEDIUM/LOW
    factors TEXT,             -- JSON
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE INDEX idx_predictions_symbol ON predictions(symbol);
CREATE INDEX idx_predictions_created ON predictions(created_at);
```

### 3.2 輿情數據表
```sql
CREATE TABLE sentiment_data (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    score REAL NOT NULL,
    label TEXT NOT NULL,      -- POSITIVE/NEGATIVE/NEUTRAL
    articles TEXT,             -- JSON array
    keywords TEXT,             -- JSON array
    confidence REAL,
    cached INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_sentiment_symbol ON sentiment_data(symbol);
CREATE INDEX idx_sentiment_created ON sentiment_data(created_at);
```

### 3.3 配置表
```sql
CREATE TABLE module_config (
    module_name TEXT PRIMARY KEY,
    config TEXT NOT NULL,     -- JSON
    enabled INTEGER DEFAULT 1,
    updated_at TEXT NOT NULL
);
```

## 四、API 設計

### 4.1 預測 API

```
POST /api/v1/prediction
{
    "symbol": "TSLA",
    "direction": "UP",      -- UP/DOWN/VOLATILITY
    "threshold": 10,         -- 百分比
    "period_days": 5
}

Response 200:
{
    "success": true,
    "data": {
        "symbol": "TSLA",
        "direction": "UP",
        "probability": 0.68,
        "confidence": "HIGH",
        "factors": {...}
    }
}
```

### 4.2 輿情 API

```
GET /api/v1/sentiment/{symbol}

Response 200:
{
    "success": true,
    "data": {
        "symbol": "TSLA",
        "score": 0.65,
        "label": "POSITIVE",
        "confidence": 0.72,
        "articles": [...],
        "keywords": [...]
    }
}
```

### 4.3 配置 API

```
GET /api/v1/config/modules

POST /api/v1/config/modules
{
    "sentiment": {
        "enabled": true,
        "update_interval": 1800
    }
}

Response 200:
{
    "success": true,
    "message": "Configuration updated"
}
```

## 五、代碼結構

```
trade_master_v2/
├── main.py                    # 主入口
├── api/
│   ├── __init__.py
│   ├── prediction.py         # 預測 API
│   ├── sentiment.py           # 輿情 API
│   └── config.py             # 配置 API
├── modules/
│   ├── prediction/
│   │   ├── __init__.py
│   │   ├── engine.py         # 預測引擎
│   │   ├── calculator.py      # 概率計算
│   │   └── factors.py         # 因素分析
│   └── sentiment/
│       ├── __init__.py
│       ├── fetcher.py        # 新聞獲取
│       ├── analyzer.py       # 情緒分析
│       ├── cache.py          # 緩存管理
│       └── scheduler.py      # 30分鐘調度
├── config/
│   ├── __init__.py
│   ├── settings.py           # 配置管理
│   └── modules.yaml         # 模組配置
├── data/
│   ├── __init__.py
│   ├── database.py          # SQLite 管理
│   └── models.py            # 數據模型
├── tests/
│   ├── test_prediction.py
│   └── test_sentiment.py
└── requirements.txt
```

## 六、時序圖

### 6.1 預測指令處理

```
用戶     指令解析     預測引擎      指標計算      數據庫
  │         │           │             │            │
  │──TSLA/📈/10/5──→│             │            │
  │         │           │             │            │
  │         │──解析────→│             │            │
  │         │           │             │            │
  │         │           │──計算指標───→│            │
  │         │           │             │            │
  │         │           │←──返回指標───│            │
  │         │           │             │            │
  │         │           │──計算概率───→│            │
  │         │           │             │            │
  │         │           │←──結果──────│            │
  │         │           │             │            │
  │←────結果────────────│             │            │
```

### 6.2 輿情更新（30分鐘週期）

```
調度器     緩存檢查     新聞API      情緒分析     數據庫
   │          │           │            │           │
   │──觸發───→│           │            │           │
   │          │──檢查────→│            │           │
   │          │←過期──────│            │           │
   │          │           │            │           │
   │          │──獲取────→│            │           │
   │          │←返回──────│            │           │
   │          │           │            │           │
   │          │           │──分析──────→│           │
   │          │           │←返回分數────│           │
   │          │           │            │           │
   │          │──保存────→│            │           │
   │          │           │            │──→存入─────│
   │          │           │            │           │
   │──完成────→│           │            │           │
```

## 七、配置示例

```yaml
# modules.yaml

# 預測模組
prediction:
  enabled: true
  default_direction: "UP"
  default_threshold: 10
  default_period_days: 5
  weights:
    technical: 0.40
    momentum: 0.35
    support_resistance: 0.25

# 輿情模組
sentiment:
  enabled: false  # 預設關閉
  update_interval: 1800  # 秒
  cache_ttl: 3600  # 秒
  sources:
    news_api:
      enabled: true
      api_key: "${NEWS_API_KEY}"
      max_articles: 10
    google_trends:
      enabled: false
  sentiment_weights:
    positive: 0.3
    negative: -0.3
    neutral: 0.0

# 調度配置
scheduler:
  prediction_check: 300     # 5分鐘
  sentiment_update: 1800     # 30分鐘
  data_cleanup: 86400        # 1天
  cleanup_retention_days: 30

# 數據庫配置
database:
  path: "data/trademaster.db"
  max_size_mb: 100
  backup_interval: 86400
```

## 八、依賴清單

```txt
# 新增依賴
newsapi-python>=0.2.6
google-trends-api>=0.1.0
python-dateutil>=2.8.2
schedule>=1.2.0

# 現有依賴
yfinance>=0.2.36
pandas>=2.0.0
numpy>=1.24.0
requests>=2.31.0
pyyaml>=6.0
loguru>=0.7.0
pytest>=7.4.0
```

## 九、開發時程

| 階段 | 功能 | 預估時長 |
|------|------|----------|
| 1 | 預測引擎 (engine + calculator) | 2小時 |
| 2 | 輿情模組 (fetcher + analyzer) | 3小時 |
| 3 | 30分鐘調度器 + 緩存 | 1小時 |
| 4 | API 介面 + 配置管理 | 1小時 |
| 5 | 單元測試 | 2小時 |
| 6 | 集成測試 | 2小時 |

**總計：約 11 小時**

## 十、風險與緩解

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| NewsAPI 免費版限額 | 每日100條可能不足 | 添加本地緩存、輪詢多來源 |
| 情緒分析準確度 | 低質量預測 | 設置信心度閾值、不足時降低權重 |
| API 延遲 | 預測結果延遲 | 異步處理、預先計算熱門股票 |
| 數據膨脹 | 數據庫過大 | 自動清理30天前數據 |

## 十一、測試策略

### 11.1 單元測試
- 預測概率計算邏輯
- 情緒分數計算
- 緩存機制
- 配置載入

### 11.2 集成測試
- 端到端預測流程
- 輿情更新流程
- API 響應格式
- 配置開關控制

### 11.3 回測驗證
- 使用歷史數據驗證預測準確率
- 比較開關輿情前后的策略表現
