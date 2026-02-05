# TradeMaster v2 - 系統優化記錄

**優化日期**: 2026-02-04  
**優化目標**: 針對不同股票特性調整系統參數

---

## 優化背景

### 問題診斷

| 問題 | 影響 | 嚴重性 |
|------|------|--------|
| 沒有波動率濾網 | 高波動股票 (TSLA, COIN) 產生過多假訊號 | 🔴 高 |
| 沒有趨勢強度過濾 | ADX 低時趨勢策略失效 | 🟡 中 |
| 沒有動態止損/倉位 | 所有股票用相同風險參數 | 🟡 中 |
| 沒有行業配置 | 半導體類股過度集中 | 🟡 中 |

---

## 新增模組

### 1. market_regime.py - 市場環境識別

**功能**: 識別牛/熊/震盪市場

```python
from core.market_regime import MarketRegimeDetector, MarketRegime

# 識別當前市場環境
detector = MarketRegimeDetector()
regime, confidence = detector.detect_regime(prices)

# 結果
MarketRegime.BULL    # 牛市
MarketRegime.BEAR    # 熊市  
MarketRegime.NEUTRAL # 震盪
```

**配置參數**:
- `fast_ma_period`: 20 日
- `slow_ma_period`: 50 日
- `adx_threshold`: 25 (趨勢強度閾值)

---

### 2. volatility.py - 波動率分析

**功能**: ATR 計算、動態止損、倉位調整

```python
from core.volatility import VolatilityAnalyzer

analyzer = VolatilityAnalyzer()

# 計算 ATR
atr = analyzer.calculate_atr(high, low, close)

# 計算動態止損
stop_loss = analyzer.calculate_dynamic_stop_loss(entry_price, atr, direction="LONG")

# 計算倉位
size = analyzer.calculate_position_size(capital, atr, entry_price)
```

**配置參數**:
- `atr_period`: 14 日
- `atr_multiplier`: 2.0 (止損倍數)
- `base_risk_pct`: 2% (基礎風險)

---

### 3. sector_config.py - 行業配置

**功能**: 根據行業特性配置不同參數

```python
from core.sector_config import SectorConfigManager, Sector

manager = SectorConfigManager()

# 獲取股票的行業配置
config = manager.get_config("NVDA")  # 半導體

# 獲取推薦策略
strategies = manager.get_recommended_strategies("TSLA")  # ["BollingerBounce"]
```

**支持的行業**:
| 行業 | 股票範例 | 特性 |
|------|----------|------|
| 半導體 | NVDA, AMD, TSM | 高波動，強趨勢 |
| 科技巨頭 | AAPL, MSFT, GOOGL | 穩定 |
| 電動車 | TSLA | 高波動，均值回歸 |
| 加密 | COIN | 極高波動 |
| 儲存 | MU, WDC | 週期性 |

---

## 新增風控規則

### DynamicStopLoss (動態止損)

根據 ATR 自動調整止損距離:

```python
# 正常市場
atr = $5, 止損距離 = $10 (2倍 ATR)

# 高波動市場  
atr = $10, 止損距離 = $20 (2倍 ATR)
```

### VolatilityPositionSizing (波動率倉位)

根據波動率調整倉位大小:

| 波動率 | 倉位係數 |
|--------|----------|
| 高 (>3%) | 0.5x |
| 中 (1.5-3%) | 1.0x |
| 低 (<1.5%) | 1.2x |

---

## 新增策略

### MultiFactorV2 (多因子策略 v2)

在原版基礎上增加:

1. **波動率過濾**: 價格在布林帶極端位置時不交易
2. **趨勢強度確認**: ADX 低於閾值時發出警告

```python
# 配置
MultiFactorV2(
    use_volatility_filter=True,
    bb_percent_low=0.2,
    bb_percent_high=0.8,
    adx_threshold=25
)
```

### SectorAdaptive (行業自適應)

根據行業自動調整參數:

| 行業 | RSI | ADX 閾值 | 波動率過濾 |
|------|-----|----------|------------|
| 半導體 | 35/65 | 25 | 是 |
| 科技巨頭 | 30/70 | 20 | 否 |
| 電動車 | 40/60 | 30 | 是 |
| 加密 | 45/55 | 35 | 是 |

---

## 股票最佳策略對照表

更新後的推薦策略:

| 股票 | 代碼 | 最佳策略 | 說明 |
|------|------|----------|------|
| NVIDIA | NVDA | MultiFactorV2 | 強趨勢，高波動 |
| 台積電 | TSM | TrendFollower | 趨勢明確 |
| AMD | AMD | SectorAdaptive(semiconductor) | 半導體專用 |
| Meta | META | MACDTrend | 趨勢追蹤 |
| Apple | AAPL | MultiFactorV2 | 穩定，多因子 |
| Tesla | TSLA | BollingerBounce | 均值回歸 |
| 美光 | MU | SectorAdaptive(storage) | 儲存行業 |
| Coinbase | COIN | MomentumCombo | 高波動專用 |
| Intel | INTC | BollingerBounce | 下降趨勢避免 |
| Rocket Lab | RKLB | 極小倉位 | 高風險 |

---

## 策略參數優化

### 針對 TSLA 的優化

| 參數 | 原值 | 優化值 | 原因 |
|------|------|--------|------|
| 止損 | 5% | 10% | 波動大，5% 太近 |
| RSI 閾值 | 30/70 | 40/60 | 避免假突破 |
| ADX 閾值 | 25 | 30 | 只在強趨勢時交易 |
| 倉位 | 25% | 15% | 降低風險 |

### 針對 NVDA 的優化

| 參數 | 原值 | 優化值 | 原因 |
|------|------|--------|------|
| 止損 | 5% | 8% | 趨勢性強，可承受更大回撤 |
| RSI 閾值 | 30/70 | 35/65 | 適應高波動 |
| 倉位 | 25% | 20% | 避免過度集中 |

---

## 風控規則更新

### 新增規則

| 規則 | 功能 | 參數 |
|------|------|------|
| DynamicStopLoss | ATR 動態止損 | atr_multiplier=2.0 |
| VolatilityPositionSizing | 波動率倉位調整 | base_risk_pct=2% |

### 修改規則

| 規則 | 修改內容 |
|------|----------|
| FixedStopLoss | 半導體: 8%, EV: 10%, Crypto: 15% |
| MaxPositionLimit | 半導體類股總曝險上限 40% |
| DailyLossLimit | Crypto 標的額外限制 1% |

---

## 使用方式

### 完整配置範例

```python
from core.market_regime import MarketRegimeDetector
from core.volatility import VolatilityAnalyzer
from core.sector_config import SectorConfigManager

# 初始化
regime_detector = MarketRegimeDetector()
volatility_analyzer = VolatilityAnalyzer()
sector_manager = SectorConfigManager()

# 1. 識別市場環境
regime, confidence = regime_detector.detect_regime(prices)

# 2. 計算波動率
atr = volatility_analyzer.calculate_atr(high, low, close)

# 3. 獲取行業配置
config = sector_manager.get_config("NVDA")

# 4. 計算動態止損
stop = volatility_analyzer.calculate_dynamic_stop_loss(
    entry_price=100, 
    atr=atr, 
    direction="LONG"
)

# 5. 計算倉位
size = volatility_analyzer.calculate_position_size(
    capital=1000000,
    atr=atr,
    entry_price=100,
    volatility_regime="high" if atr > 10 else "low"
)
```

---

## 優化效果預估

| 指標 | 優化前 | 優化後 | 改善 |
|------|--------|--------|------|
| TSLA 假訊號 | 高 | 中 | -30% |
| NVDA 回撤控制 | 8% | 6% | -25% |
| 半導體類股曝險 | 60% | 40% | -33% |
| 整體夏普比率 | 1.1 | 1.4 | +27% |

---

## 下一步

1. [ ] 針對每個股票進行參數微調
2. [ ] 重新運行回測
3. [ ] 比較優化前後效果
4. [ ] 部署到實盤

---

*記錄時間: 2026-02-04 09:30 GMT+8*
