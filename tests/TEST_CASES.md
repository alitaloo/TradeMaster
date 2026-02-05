# TradeMaster v2.0 測試用例

## 測試股票清單

### 七巨頭 (Magnificent 7)
| 股票代碼 | 公司名稱 | 類別 |
|----------|----------|------|
| AAPL | Apple | 消費電子 |
| MSFT | Microsoft | 軟體/雲端 |
| AMZN | Amazon | 電商/雲端 |
| GOOGL | Alphabet/Google | 網路/AI |
| META | Meta | 社群媒體 |
| NVDA | Nvidia | 晶片/AI |
| TSLA | Tesla | 電動車 |

### 熱門科技股
| 股票代碼 | 公司名稱 | 類別 |
|----------|----------|------|
| AMD | AMD | 晶片 |
| INTC | Intel | 晶片 |
| MU | Micron | 記憶體 |
| TSM | 台積電 | 半導體代工 |
| WDC | Western Digital | 儲存 |
| ORCL | Oracle | 企業軟體 |
| COIN | Coinbase | 加密貨幣 |
| UBER | Uber | 共享經濟 |
| RKLB | Rocket Lab | 航太 |

---

## 測試股票配置

```python
# tests/config/test_symbols.py

TEST_SYMBOLS = {
    # 七巨頭
    "AAPL": {"name": "Apple", "category": "科技巨頭"},
    "MSFT": {"name": "Microsoft", "category": "科技巨頭"},
    "AMZN": {"name": "Amazon", "category": "科技巨頭"},
    "GOOGL": {"name": "Alphabet", "category": "科技巨頭"},
    "META": {"name": "Meta", "category": "科技巨頭"},
    "NVDA": {"name": "Nvidia", "category": "科技巨頭"},
    "TSLA": {"name": "Tesla", "category": "科技巨頭"},
    
    # 晶片/半導體
    "AMD": {"name": "AMD", "category": "半導體"},
    "INTC": {"name": "Intel", "category": "半導體"},
    "MU": {"name": "Micron", "category": "記憶體"},
    "TSM": {"name": "台積電", "category": "晶圓代工"},
    "WDC": {"name": "Western Digital", "category": "儲存設備"},
    
    # 軟體/雲端
    "ORCL": {"name": "Oracle", "category": "企業軟體"},
    
    # 加密貨幣
    "COIN": {"name": "Coinbase", "category": "加密交易所"},
    
    # 共享經濟
    "UBER": {"name": "Uber", "category": "共享經濟"},
    
    # 航太
    "RKLB": {"name": "Rocket Lab", "category": "航太"},
}

# 回測用標的（熱門選擇）
BACKTEST_SYMBOLS = [
    "NVDA",  # 高波動 AI 概念
    "AAPL",  # 穩定藍籌
    "TSLA",  # 高爭議高波動
    "AMD",   # 挑戰者
    "META",  # 反轉案例
]

# 測試期間
TEST_PERIODS = {
    "short": "3mo",           # 快速測試
    "medium": "1y",           # 標準回測
    "long": "2y",             # 長期驗證 (2023-2024)
    "bull": "2023-01-01to2024-12-31",   # 多頭市場
}
```

---

## 測試用例

### 一、Core 模組測試

| 測試 ID | 名稱 | 模組 | 優先級 |
|---------|------|------|--------|
| TC-001 | 指標插件註冊與發現 | PluginRegistry | P0 |
| TC-002 | 策略插件註冊與發現 | PluginRegistry | P0 |
| TC-003 | 風控規則註冊與發現 | PluginRegistry | P1 |
| TC-004 | 獲取插件元數據 | PluginRegistry | P1 |

### 二、Indicators 模組測試

| 測試 ID | 名稱 | 測試標的 | 優先級 |
|---------|------|----------|--------|
| TC-010 | RSI 計算正確性 | AAPL, NVDA (2y) | P0 |
| TC-011 | RSI 超賣信號 | TSLA | P0 |
| TC-012 | RSI 超買信號 | NVDA | P0 |
| TC-013 | RSI 背離檢測 | AMD | P1 |
| TC-020 | EMA 交叉檢測 | AAPL | P0 |
| TC-021 | EMA 多頭排列 | MSFT | P0 |
| TC-030 | MACD 計算 | GOOGL | P0 |
| TC-031 | MACD 金叉死叉 | META | P0 |
| TC-040 | 布林帶位置 | TSLA | P1 |
| TC-050 | ATR 波動率 | NVDA | P1 |
| TC-060 | OBV 量能 | COIN | P2 |

### 三、Strategies 模組測試

| 測試 ID | 名稱 | 測試標的 | 優先級 |
|---------|------|----------|--------|
| TC-101 | RSI 反轉策略做多 | TSLA, AMD | P0 |
| TC-102 | RSI 反轉策略做空 | NVDA | P0 |
| TC-110 | EMA 交叉黃金交叉 | AAPL | P0 |
| TC-111 | EMA 交叉死亡交叉 | META | P0 |
| TC-120 | MACD 趨勢策略 | GOOGL | P1 |
| TC-130 | 多指標共振 | MSFT | P1 |
| TC-140 | 突破策略 | TSLA | P1 |

### 四、Risk Rules 模組測試

| 測試 ID | 名稱 | 優先級 |
|---------|------|--------|
| TC-201 | 最大倉位限制 | P0 |
| TC-202 | 移動止損觸發 | P0 |
| TC-203 | 固定止損觸發 | P0 |
| TC-204 | 分批止盈 | P1 |
| TC-205 | 每日虧損限制 | P0 |
| TC-206 | 持倉相關性檢查 | P2 |

### 五、Data Engine 測試

| 測試 ID | 名稱 | 測試標的 | 優先級 |
|---------|------|----------|--------|
| TC-301 | 獲取日線數據 | 17 檔全部 | P0 |
| TC-302 | 批量獲取數據 | 前 5 檔 | P0 |
| TC-303 | 數據清洗 | AAPL | P1 |
| TC-304 | 市場狀態檢查 | - | P1 |

### 六、Alert System 測試

| 測試 ID | 名稱 | 優先級 |
|---------|------|--------|
| TC-401 | Telegram 消息格式 | P1 |
| TC-402 | AlertManager 分發 | P1 |

### 七、Security 模組測試

| 測試 ID | 名稱 | 優先級 |
|---------|------|--------|
| TC-501 | 金額限制檢查 | P0 |
| TC-502 | 頻率限制檢查 | P0 |
| TC-503 | 熔斷機制觸發 | P0 |
| TC-504 | 大額訂單確認 | P1 |

---

## 回測方案

### 方案 A：策略 vs Buy & Hold

**測試標的：** NVDA, AAPL, TSLA, AMD, META
**測試期間：** 2y (2023-2024)

### 方案 B：不同市場環境

| 市場環境 | 期間 | 測試標的 |
|----------|------|----------|
| 多頭 | 2023-01 to 2024-12 | NVDA, TSLA |
| 震盪 | 2023-01 to 2024-12 | AAPL, MSFT |

### 方案 C：參數優化

- RSI 閾值：20/25/30/35
- EMA 週期：12/26, 9/21, 5/20
- 止損比例：3%/5%/8%

---

## 預估測試時長

| 測試類別 | 測試用例數 | 預估時長 |
|---------|-----------|----------|
| Core 模組 | 4 | 15 分鐘 |
| Indicators (17 檔) | 11 | 45 分鐘 |
| Strategies | 7 | 35 分鐘 |
| Risk Rules | 6 | 25 分鐘 |
| Data Engine (17 檔) | 4 | 20 分鐘 |
| Alert System | 2 | 10 分鐘 |
| Security | 4 | 20 分鐘 |
| **總計** | **38** | **~2.5 小時** |

---

## 測試環境配置

```python
# tests/conftest.py
import pytest
from data import DataEngine

@pytest.fixture
def data_engine():
    return DataEngine()

@pytest.fixture
def sample_ohlc_data():
    # 使用 NVDA 2024 年數據
    engine = DataEngine()
    return engine.get_daily_data("NVDA", period="1y")

@pytest.fixture
def test_symbols():
    return list(TEST_SYMBOLS.keys())
```

---

## 通過標準

| 等級 | 說明 | 通過率要求 |
|------|------|-----------|
| P0 | 核心功能 | 100% |
| P1 | 重要功能 | 90% |
| P2 | 一般功能 | 70% |
