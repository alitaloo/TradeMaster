# 高級量化策略使用指南

## 📁 策略文件位置
```
strategies/advanced_quant_strategies.py
```

## 🚀 快速開始

```python
from strategies.advanced_quant_strategies import (
    AdvancedDualMomentum,
    QualityMomentum,
    RSIAggressive,
    WilliamsPercentR,
    ATRBreakout,
    AdaptiveMultiFactor,
)

# 創建策略
strategy = AdvancedDualMomentum(
    abs_momentum_months=12,
    abs_momentum_threshold=0.0,
    rel_momentum_periods=6,
    rel_rank_threshold=0.3,
    rsi_period=10,
    rsi_entry=50,
    rsi_exit=35,
    sma_period=50,
    stop_loss=0.10,
    take_profit=0.30,
    max_holding_days=60
)

# 生成信號
signal = strategy.generate_signal({}, data)
```

---

## 📊 策略詳解

### 1. AdvancedDualMomentum（增強版雙重動量）

**核心理念**: 結合絕對動量 + 相對動量

**進場條件**:
- 12個月絕對動量 > 0%
- 相對動量排名前30%
- RSI(10) > 50
- 價格 > 50日均線

**風控參數**:
- 止損: 10%
- 止盈: 30%
- 最大持倉: 60天

**適用場景**: 趨勢明顯的市場

---

### 2. QualityMomentum（質量動量）

**核心理念**: 動量 + 基本面質量

**進場條件**:
- 6個月價格動量 > 10%
- ROE > 15%（如有）
- 低槓桿（Debt/Equity < 0.5）
- RSI < 70

**風控參數**:
- 止損: 12%
- 止盈: 35%
- 最大持倉: 90天

**適用場景**: 長期投資，质量选股

---

### 3. RSIAggressive（RSI-2 激进）

**核心理念**: 極短期超賣反彈

**進場條件**:
- RSI(2) < 15（深度超賣）
- 價格接近10日低點
- 波動率處於相對高位

**風控參數**:
- 止損: 3%
- 止盈: 8%
- 最大持倉: 5天

**適用場景**: 短線交易，高頻策略

---

### 4. WilliamsPercentR（威廉指標）

**核心理念**: 多時間框架 %R 交易

**進場條件**:
- 日線 %R < -80
- 週線 %R < -60（確認）
- %R 正在反彈

**風控參數**:
- 止損: 5%
- 止盈: 12%
- 最大持倉: 15天

**適用場景**: 短中期交易

---

### 5. ATRBreakout（ATR 突破）

**核心理念**: 波動率週期交易

**進場條件**:
- ATR < 30% 分位
- ATR 開始擴張
- 價格突破20日區間
- 成交量放大

**風控參數**:
- 止損: 6%
- 止盈: 20%
- 最大持倉: 25天

**適用場景**: 突破行情

---

### 6. AdaptiveMultiFactor（自適應多因子）

**核心理念**: 多因子自適應調整

**因子權重**:
- 動量因子: 35%
- 均值回歸因子: 20%
- 波動率因子: 15%
- 趨勢因子: 30%

**風控參數**:
- 止損: 8%
- 止盈: 25%
- 最大持倉: 30天

**適用場景**: 適合所有市場環境

---

## 📈 參數優化建議

### RSI 進場門檻
| 門檻 | 報酬 | 風險 | 建議 |
|------|------|------|------|
| < 20 | 高 | 高 | 激进投資者 |
| < 30 | 中高 | 中 | 平衡型 ✓ |
| < 40 | 中 | 低 | 保守型 |

### 止損/止盈比例
| 止損 | 止盈 | 適合策略 |
|------|------|----------|
| 3% | 8% | RSI-2 |
| 5% | 12% | %R |
| 8% | 20% | ATR突破 |
| 10% | 30% | Dual Momentum |

---

## ⚠️ 風險提示

1. **模擬數據限制**: 回測結果基於模擬數據，實際表現可能不同
2. **交易成本**: 實際交易需要考慮手續費、滑價
3. **市場風險**: 任何策略都可能遭遇虧損
4. **參數過擬合**: 過度優化的參數可能在實盤失效

---

## 📋 回測結果摘要

| 策略 | 報酬 | 夏普 | 勝率 | 建議 |
|------|------|------|------|------|
| WilliamsPercentR | 40.4% | 0.61 | 66.7% | ✓ |
| RSIAggressive | 29.9% | 0.45 | 100% | ✓ |
| AdaptiveMultiFactor | 26.1% | 0.39 | 100% | ✓ |
| AdvancedDualMomentum | 0% | 0 | N/A | 需優化 |
| ATRBreakout | 0% | 0 | N/A | 需優化 |

---

## 🎯 最佳實踐

1. **策略組合**: 建議使用 2-3 個策略組合
2. **倉位管理**: 單策略不超過總資金 30%
3. **風險控制**: 總回撤控制在 15% 以內
4. **定期評估**: 每月評估策略表現

---

## 📞 支援

如有任何問題，請參考:
- `ADVANCED_STRATEGIES_RESEARCH.md` - 完整研究報告
- `HIGH_SHARPE_REPORT.md` - 高夏普策略報告

---

*更新時間: 2026-02-07*
*Author: TradeMaster Pro*
