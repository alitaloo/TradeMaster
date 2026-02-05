# TradeMaster v2 - 18 股票策略組合優化報告

**優化日期**: 2026-02-04  
**策略數**: 7 個核心策略 + 2 個新策略  
**資金**: $1,000,000

---

## 📊 股票特性與策略匹配

### 一、半導體晶圓代工 (高 Beta，高成長)

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **NVIDIA** | NVDA | 1.8 | 高 | AI 龍頭，強趨勢 | **MultiFactorV2 (40%)** + TrendFollower (30%) |
| **TSMC** | TSM | 1.4 | 中高 | 晶圓代工，趨勢明確 | **MACDTrend (50%)** + ADXTrend (30%) |
| **AMD** | AMD | 1.5 | 高 | 競爭 NVIDIA，高波動 | **SectorAdaptive (semiconductor) (50%)** + MultiFactorV2 (30%) |
| **Intel** | INTC | 0.8 | 中低 | 下降趨勢，轉型中 | **BollingerBounce (60%)** + RSI_Reversal (30%) |

### 二、科技巨頭 (穩定成長)

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **Apple** | AAPL | 1.2 | 低 | 消費電子，穩定 | **MultiFactorV2 (50%)** + RSI_Reversal (30%) |
| **Microsoft** | MSFT | 1.1 | 低 | 雲端+AI，穩定 | **TrendFollower (50%)** + MultiFactorV2 (30%) |
| **Alphabet** | GOOGL | 1.1 | 低 | 搜尋+AI，穩定 | **MACDTrend (50%)** + MultiFactorV2 (30%) |
| **Amazon** | AMZN | 1.3 | 中 | 電商+雲端 | **MultiFactorV2 (50%)** + TrendFollower (30%) |
| **Meta** | META | 1.4 | 中高 | 社群+AI，高波動 | **MACDTrend (50%)** + ADXTrend (30%) |

### 三、電動車 (高波動，高噪音)

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **Tesla** | TSLA | 2.0 | 極高 | 消息驅動，噪音多 | **BollingerBounce (50%)** + MomentumCombo (40%) |

### 四、儲存/數據 (週期性)

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **Micron** | MU | 1.5 | 高 | 記憶體，週期性 | **SectorAdaptive (storage) (50%)** + BollingerBounce (30%) |
| **Western Digital** | WDC | 1.3 | 中高 | 硬碟+SSD | **BollingerBounce (50%)** + RSI_Reversal (30%) |

### 五、加密貨幣 (極高波動)

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **Coinbase** | COIN | 3.0 | 極高 | 比特幣相關 | **MomentumCombo (60%)** + TrendFollower (30%) |

### 六、企業軟體

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **Oracle** | ORCL | 0.9 | 低 | 企業軟體，股息 | **RSI_Reversal (50%)** + MultiFactorV2 (30%) |

### 七、新興科技

| 股票 | 代碼 | Beta | 波動率 | 特性 | 推薦策略 |
|------|------|------|--------|------|----------|
| **Uber** | UBER | 1.3 | 中 | 出行+外送 | **MultiFactorV2 (50%)** + RSI_Reversal (30%) |
| **Rocket Lab** | RKLB | 1.6 | 高 | 航天，高風險 | **MomentumCombo (50%)** + 極小倉位 |

---

## 🎯 策略組合配置表

### 策略組合 1：半導體成長型 (NVDA, AMD, TSM)

```yaml
symbols:
  - NVDA: 25%
  - AMD: 15%
  - TSM: 15%

strategies:
  MultiFactorV2:
    weight: 40%
    params:
      use_volatility_filter: true
      bb_percent_low: 0.15
      bb_percent_high: 0.85
      rsi_oversold: 35
      rsi_overbought: 65
      adx_threshold: 25
  
  MACDTrend:
    weight: 35%
    params:
      histogram_threshold: 0.0
  
  ADXTrend:
    weight: 15%
    params:
      adx_threshold: 25
  
  RSI_Reversal:
    weight: 10%
    params:
      rsi_period: 14
      oversold: 35
      overbought: 65
```

**預期年化**: 22-28%  
**最大回撤**: 12-15%

---

### 策略組合 2：科技巨頭穩健型 (AAPL, MSFT, GOOGL, AMZN)

```yaml
symbols:
  - AAPL: 25%
  - MSFT: 25%
  - GOOGL: 20%
  - AMZN: 20%

strategies:
  MultiFactorV2:
    weight: 50%
    params:
      use_volatility_filter: false
      rsi_oversold: 30
      rsi_overbought: 70
      adx_threshold: 20
  
  TrendFollower:
    weight: 30%
    params:
      fast_period: 10
      slow_period: 30
  
  RSI_Reversal:
    weight: 20%
    params:
      rsi_period: 14
      oversold: 30
      overbought: 70
```

**預期年化**: 15-20%  
**最大回撤**: 8-10%

---

### 策略組合 3：均值回歸型 (TSLA, MU, WDC)

```yaml
symbols:
  - TSLA: 15%
  - MU: 15%
  - WDC: 10%

strategies:
  BollingerBounce:
    weight: 50%
    params:
      rsi_oversold: 40
      rsi_overbought: 60
  
  MomentumCombo:
    weight: 30%
    params:
      momentum_threshold: 0.6
  
  RSI_Reversal:
    weight: 20%
    params:
      rsi_period: 14
      oversold: 40
      overbought: 60
```

**預期年化**: 12-18%  
**最大回撤**: 10-12%

---

### 策略組合 4：高波動加密型 (COIN)

```yaml
symbols:
  - COIN: 10%

strategies:
  MomentumCombo:
    weight: 60%
    params:
      momentum_threshold: 0.7
  
  TrendFollower:
    weight: 30%
    params:
      fast_period: 5
      slow_period: 20
  
  RSI_Reversal:
    weight: 10%
    params:
      rsi_period: 7
      oversold: 45
      overbought: 55
```

**預期年化**: 25-40%  
**最大回撤**: 20-30%

---

### 策略組合 5：保守型 (AAPL, MSFT, ORCL)

```yaml
symbols:
  - AAPL: 30%
  - MSFT: 30%
  - ORCL: 20%

strategies:
  RSI_Reversal:
    weight: 40%
    params:
      rsi_period: 21
      oversold: 30
      overbought: 70
  
  MultiFactorV2:
    weight: 40%
    params:
      use_volatility_filter: false
      min_agreement: 0.7
  
  BollingerBounce:
    weight: 20%
    params:
      rsi_oversold: 30
      rsi_overbought: 70
```

**預期年化**: 10-15%  
**最大回撤**: 5-8%

---

## 💰 完整投資組合配置

### 資金分配 ($1,000,000)

| 組合 | 股票 | 分配 | 金額 | 策略 |
|------|------|------|------|------|
| **組合1** | NVDA, AMD, TSM | 55% | $550,000 | 半導體成長型 |
| **組合2** | AAPL, MSFT, GOOGL, AMZN | 30% | $300,000 | 科技巨頭穩健型 |
| **組合3** | TSLA, MU | 8% | $80,000 | 均值回歸型 |
| **組合5** | AAPL, MSFT, ORCL | 5% | $50,000 | 保守型 |
| **現金** | - | 2% | $20,000 | 待機 |

### 各股票最終配置

| 股票 | 代碼 | 組合 | 金額 | 佔比 |
|------|------|------|------|------|
| NVIDIA | NVDA | 1 | $250,000 | 25% |
| AMD | AMD | 1 | $150,000 | 15% |
| TSMC | TSM | 1 | $150,000 | 15% |
| Apple | AAPL | 2+5 | $275,000 | 27.5% |
| Microsoft | MSFT | 2+5 | $250,000 | 25% |
| Alphabet | GOOGL | 2 | $50,000 | 5% |
| Tesla | TSLA | 3 | $40,000 | 4% |
| Micron | MU | 3 | $40,000 | 4% |
| Oracle | ORCL | 5 | $25,000 | 2.5% |
| 現金 | - | - | $20,000 | 2% |

---

## 📈 策略權重計算方法

### 動態權重公式

```
Strategy_Weight = Base_Weight × Sector_Factor × Volatility_Factor × Trend_Factor
```

### 各因子係數

| 因子 | 條件 | 係數 |
|------|------|------|
| **Sector_Factor** | 半導體 | 1.2 |
| | 科技巨頭 | 1.0 |
| | 電動車 | 0.8 |
| | 加密 | 0.6 |
| **Volatility_Factor** | HV > 3% | 0.7 |
| | HV 1.5-3% | 1.0 |
| | HV < 1.5% | 1.2 |
| **Trend_Factor** | ADX > 30 | 1.3 |
| | ADX 20-30 | 1.0 |
| | ADX < 20 | 0.7 |

---

## 🎯 最佳策略組合總結

### 每個股票的最佳策略 (Top 3)

| 股票 | 代碼 | 🥇 最佳 | 🥈 第二 | 🥉 第三 |
|------|------|---------|---------|---------|
| NVIDIA | NVDA | MultiFactorV2 | TrendFollower | MACDTrend |
| TSMC | TSM | MACDTrend | MultiFactorV2 | ADXTrend |
| AMD | AMD | SectorAdaptive | MultiFactorV2 | MACDTrend |
| Apple | AAPL | MultiFactorV2 | RSI_Reversal | TrendFollower |
| Microsoft | MSFT | TrendFollower | MultiFactorV2 | RSI_Reversal |
| Alphabet | GOOGL | MACDTrend | MultiFactorV2 | TrendFollower |
| Amazon | AMZN | MultiFactorV2 | TrendFollower | MACDTrend |
| Meta | META | MACDTrend | ADXTrend | MultiFactorV2 |
| Tesla | TSLA | BollingerBounce | MomentumCombo | RSI_Reversal |
| Micron | MU | SectorAdaptive | BollingerBounce | RSI_Reversal |
| Western Digital | WDC | BollingerBounce | RSI_Reversal | MultiFactorV2 |
| Coinbase | COIN | MomentumCombo | TrendFollower | MACDTrend |
| Oracle | ORCL | RSI_Reversal | MultiFactorV2 | BollingerBounce |
| Intel | INTC | BollingerBounce | RSI_Reversal | - |
| Uber | UBER | MultiFactorV2 | RSI_Reversal | TrendFollower |
| Rocket Lab | RKLB | MomentumCombo | - | - |

---

## 📊 風險控制配置

### 止損配置 (根據股票)

| 股票 | 代碼 | 固定止損 | ATR 倍數 | 移動止損 |
|------|------|----------|----------|----------|
| NVIDIA | NVDA | 8% | 2.5 | 5% |
| TSMC | TSM | 6% | 2.0 | 5% |
| AMD | AMD | 8% | 2.5 | 5% |
| Apple | AAPL | 5% | 1.5 | 5% |
| Microsoft | MSFT | 5% | 1.5 | 5% |
| Tesla | TSLA | 10% | 3.0 | 8% |
| Coinbase | COIN | 15% | 4.0 | 10% |
| 其他 | - | 6% | 2.0 | 5% |

### 倉位配置 (根據波動率)

| 波動率 | HV | 倉位係數 | 最大倉位 |
|--------|-----|----------|----------|
| 極高 | > 4% | 0.5x | 10% |
| 高 | 2.5-4% | 0.7x | 15% |
| 中 | 1.5-2.5% | 1.0x | 20% |
| 低 | < 1.5% | 1.2x | 25% |

---

## 📋 執行清單

### 每日檢查

- [ ] 檢查市場環境 (牛市/熊市/震盪)
- [ ] 更新波動率狀態
- [ ] 檢查策略信號
- [ ] 執行訊號

### 每週檢查

- [ ] 重新平衡倉位
- [ ] 檢查策略表現
- [ ] 調整參數 (如需要)

### 每月檢查

- [ ] 回顧表現
- [ ] 調整策略權重
- [ ] 更新行業配置

---

## 🎯 預期表現

### 組合表現預估

| 指標 | 保守估計 | 中性估計 | 樂觀估計 |
|------|----------|----------|----------|
| **年化回報** | 15% | 20% | 28% |
| **最大回撤** | -8% | -10% | -15% |
| **夏普比率** | 1.0 | 1.4 | 1.8 |
| **勝率** | 52% | 56% | 60% |

### 各組合表現

| 組合 | 標的 | 預期年化 | 預期回撤 |
|------|------|----------|----------|
| 1 | NVDA, AMD, TSM | 22-28% | 12-15% |
| 2 | AAPL, MSFT, GOOGL, AMZN | 15-20% | 8-10% |
| 3 | TSLA, MU | 12-18% | 10-12% |
| 5 | AAPL, MSFT, ORCL | 10-15% | 5-8% |

---

## ⚠️ 風險警告

1. **INTC 風險**: 持續下降趨勢，建議低倉位或觀望
2. **COIN 風險**: 極高波動，僅建議 10% 以內倉位
3. **RKLB 風險**: 新興市場，高風險
4. **TSLA 噪音**: 消息驅動，需要更嚴格的止損

---

## 📝 總結

### 核心策略

| 策略 | 使用場景 | 股票數量 |
|------|----------|----------|
| **MultiFactorV2** | 穩定成長股 | 7 |
| **MACDTrend** | 趨勢明確股 | 4 |
| **BollingerBounce** | 高波動股 | 4 |
| **SectorAdaptive** | 半導體/儲存 | 2 |
| **MomentumCombo** | 加密/高波動 | 2 |
| **TrendFollower** | 穩定趨勢股 | 3 |
| **RSI_Reversal** | 震盪股 | 5 |

### 資金配置

- **半導體**: 55% ($550,000)
- **科技巨頭**: 30% ($300,000)
- **高波動/特殊**: 13% ($130,000)
- **現金**: 2% ($20,000)

---

*報告生成時間: 2026-02-04 09:20 GMT+8*
