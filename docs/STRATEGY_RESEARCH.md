# TradeMaster v2 - 策略庫擴充研究報告

**研究日期**: 2026-02-04  
**目標**: 評估並推薦新策略，擴充策略庫

---

## 📊 現有策略庫

### 當前 8 個策略

| # | 策略 | 類型 | 說明 |
|---|------|------|------|
| 1 | MultiFactorV2 | 多因子 | RSI + ADX + 布林帶 + 波動率過濾 |
| 2 | MACDTrend | 趨勢 | MACD 交叉 + 柱狀圖確認 |
| 3 | ADXTrend | 趨勢 | ADX 趨勢強度過濾 |
| 4 | BollingerBounce | 均值回歸 | 布林帶上下軌反轉 |
| 5 | RSI_Reversal | 均值回歸 | RSI 超買超賣反轉 |
| 6 | MomentumCombo | 動量 | 多週期動量組合 |
| 7 | SectorAdaptive | 行業自適應 | 根據行業調整參數 |
| 8 | TrendFollower | 趨勢 | 均線交叉 (MA) |

---

## 🎯 策略類型分類

```
趨勢策略 (Trend-Following)
├── MACDTrend ✓
├── ADXTrend ✓
├── TrendFollower ✓
└── MomentumCombo ✓

均值回歸策略 (Mean-Reversion)
├── BollingerBounce ✓
├── RSI_Reversal ✓
└── [待補充] Donchian Channel

多因子策略 (Multi-Factor)
├── MultiFactorV2 ✓
└── [待補充]基本面因子

事件驅動 (Event-Driven)
├── [待補充] 財報策略
├── [待補充] 併購套利
└── [待補充] 股息策略

波動率策略 (Volatility)
├── [待補充] ATR 突破
├── [待補充] 波動率收縮
└── [待補充] 期權策略

時間序列策略 (Time-Based)
├── [待補充] 月效應
├── [待補充] 日內策略
└── [待補充] 季節性
```

---

## 📈 待評估新策略

### 1. Donchian Channel (唐奇安通道)

| 項目 | 內容 |
|------|------|
| **類型** | 趨勢追蹤 |
| **原理** | 價格突破 N 日高點買入，跌破 N 日低點賣出 |
| **發明人** | Richard Donchian |
| **適合市場** | 趨勢明確的市場 |
| **優點** | 簡單、客觀、順勢而為 |
| **缺點** | 震盪市頻繁假訊號 |
| **實現難度** | ⭐ 簡單 |

### 2. Aroon Indicator (阿隆指標)

| 項目 | 內容 |
|------|------|
| **類型** | 趨勢強度 |
| **原理** | 測量新高/新低之間的時間距離 |
| **發明人** | Tushar Chande |
| **適合市場** | 趨勢市場 |
| **優點** | 能識別趨勢開始和結束 |
| **缺點** | 在橫向市場表現不佳 |
| **實現難度** | ⭐ 簡單 |

### 3. Stochastic Oscillator (隨機指標)

| 項目 | 內容 |
|------|------|
| **類型** | 均值回歸 |
| **原理** | (收盤價 - N 日最低) / (N 日最高 - 最低) |
| **發明人** | George Lane |
| **適合市場** | 震盪市場 |
| **優點** | 領先指標，能捕捉轉折 |
| **缺點** | 需要配合其他過濾 |
| **實現難度** | ⭐ 簡單 |

### 4. Ichimoku Kinko Hyo (一目均衡表)

| 項目 | 內容 |
|------|------|
| **類型** | 綜合技術分析 |
| **原理** | 5 條線綜合判斷趨勢、支撐阻力 |
| **發明人** | Goichi Hosoda |
| **適合市場** | 所有市場 |
| **優點** | 多維度分析，視覺化直觀 |
| **缺點** | 參數多，需要時間學習 |
| **實現難度** | ⭐⭐⭐ 中等 |

### 5. Volume-Weighted Average Price (VWAP)

| 項目 | 內容 |
|------|------|
| **類型** | 成交量加權均價 |
| **原理** | 價格 × 成交量 / 累積成交量 |
| **適合市場** | 日內交易 |
| **優點** | 考慮成交量，機構常用 |
| **缺點** | 需要日內數據 |
| **實現難度** | ⭐⭐ 中等 |

### 6. Parabolic SAR (拋物線指標)

| 項目 | 內容 |
|------|------|
| **類型** | 趨勢 + 止損 |
| **原理** | 根據價格和時間計算止損轉向點 |
| **發明人** | J. Welles Wilder |
| **適合市場** | 趨勢市場 |
| **優點** | 內建止損邏輯 |
| **缺點** | 震盪市頻繁轉向 |
| **實現難度** | ⭐⭐ 中等 |

### 7. Rate of Change (ROC / 變動率)

| 項目 | 內容 |
|------|------|
| **類型** | 動量 |
| **原理** | (當前價格 - N 日前價格) / N 日前價格 |
| **適合市場** | 動量市場 |
| **優點** | 簡單直接 |
| **缺點** | 需要配合其他指標 |
| **實現難度** | ⭐ 簡單 |

### 8. Williams %R (威廉指標)

| 項目 | 內容 |
|------|------|
| **類型** | 均值回歸 |
| **原理** | 類似隨機指標，但是反向 |
| **發明人** | Larry Williams |
| **適合市場** | 震盪市場 |
| **優點** | 領先指標 |
| **缺點** | 訊號過於頻繁 |
| **實現難度** | ⭐ 簡單 |

### 9. Commodity Channel Index (CCI)

| 項目 | 內容 |
|------|------|
| **類型** | 趨勢/震盪 |
| **原理** | (典型價格 - 移動平均) / (0.015 × 平均偏差) |
| **發明人** | Donald Lambert |
| **適合市場** | 商品和股票 |
| **優點** | 能在趨勢和震盪中使用 |
| **缺點** | 需要調整參數 |
| **實現難度** | ⭐⭐ 中等 |

### 10. On-Balance Volume (OBV / 能量潮)

| 項目 | 內容 |
|------|------|
| **類型** | 成交量指標 |
| **原理** | 價格上漲加成交量，下跌減成交量 |
| **發明人** | Joseph Granville |
| **適合市場** | 需要成交量確認的市場 |
| **優點** | 簡單有效的量價配合 |
| **缺點** | 需要成交量數據 |
| **實現難度** | ⭐ 簡單 |

### 11. Absolute Price Oscillator (APO)

| 項目 | 內容 |
|------|------|
| **類型** | 趨勢 |
| **原理** | 兩條 EMA 的差值 |
| **適合市場** | 趨勢市場 |
| **優點** | 類似 MACD 但更簡單 |
| **缺點** | 需要參數調整 |
| **實現難度** | ⭐ 簡單 |

### 12. Elder-Ray Index (艾爾多指標)

| 項目 | 內容 |
|------|------|
| **類型** | 趨勢 + 動量 |
| **原理** | 牛市力量 + 熊市力量 |
| **發明人** | Alexander Elder |
| **適合市場** | 所有市場 |
| **優點** | 結合力度和方向 |
| **缺點** | 需要配合其他指標 |
| **實現難度** | ⭐⭐ 中等 |

### 13. Pairs Trading (配對交易)

| 項目 | 內容 |
|------|------|
| **類型** | 統計套利 |
| **原理** | 兩支相關股票的價差交易 |
| **適合市場** | 相關性高的股票 |
| **優點** | 市場中性，對沖風險 |
| **缺點** | 需要找到合適的配對 |
| **實現難度** | ⭐⭐⭐ 複雜 |

### 14. Mean Reversion with Volatility (波動率均值回歸)

| 項目 | 內容 |
|------|------|
| **類型** | 均值回歸 |
| **原理** | 波動率突破後價格回歸 |
| **適合市場** | 所有市場 |
| **優點** | 考慮波動率因素 |
| **缺點** | 需要準確的波動率估計 |
| **實現難度** | ⭐⭐ 中等 |

### 15. Machine Learning Strategies (機器學習策略)

| 項目 | 內容 |
|------|------|
| **類型** | AI/ML |
| **原理** | 使用 ML 模型預測價格 |
| **適合市場** | 所有市場 |
| **優點** | 能處理複雜模式 |
| **缺點** | 需要大量數據和計算資源 |
| **實現難度** | ⭐⭐⭐⭐ 困難 |

---

## 🏆 推薦新增策略

### 🥇 第一優先 (立即實現)

| 策略 | 類型 | 實現難度 | 補充原因 |
|------|------|----------|----------|
| **Donchian Channel** | 趨勢追蹤 | ⭐ | 經典趨勢策略，彌補突破策略缺口 |
| **Stochastic** | 均值回歸 | ⭐ | 與 RSI 互補，增加反轉訊號 |
| **ATR Breakout** | 波動率突破 | ⭐⭐ | 波動率策略是系統缺口 |

### 🥈 第二優先 (短期實現)

| 策略 | 類型 | 實現難度 | 補充原因 |
|------|------|----------|----------|
| **Ichimoku** | 綜合分析 | ⭐⭐⭐ | 日本最流行的技術分析 |
| **Parabolic SAR** | 趨勢+止損 | ⭐⭐ | 內建止損邏輯 |
| **OBV** | 成交量 | ⭐ | 增加量價配合策略 |

### 🥉 第三優先 (中期實現)

| 策略 | 類型 | 實現難度 | 補充原因 |
|------|------|----------|----------|
| **CCI** | 震盪/趨勢 | ⭐⭐ | 商品和股票都適用 |
| **Pairs Trading** | 統計套利 | ⭐⭐⭐ | 市場中性策略 |
| **Momentum Rotation** | 動量輪動 | ⭐⭐ | 動量因子組合 |

### 📋 長期目標 (6-12月)

| 策略 | 類型 | 實現難度 | 補充原因 |
|------|------|----------|----------|
| **ML-based** | 機器學習 | ⭐⭐⭐⭐ | 未來趨勢 |
| **Options-based** | 期權策略 | ⭐⭐⭐⭐ | 避險和增強收益 |

---

## 📊 策略覆蓋分析

### 當前覆蓋

| 維度 | 覆蓋情況 |
|------|----------|
| 趨勢策略 | ✅ 3 個 (MACD, ADX, MA) |
| 均值回歸 | ✅ 2 個 (BB, RSI) |
| 動量策略 | ✅ 1 個 (Momentum) |
| 行業策略 | ✅ 1 個 (Sector) |
| 多因子 | ✅ 1 個 (MultiFactor) |

### 需要覆蓋

| 維度 | 缺口 | 推薦策略 |
|------|------|----------|
| 突破策略 | ❌ | Donchian Channel, ATR Breakout |
| 成交量策略 | ❌ | OBV, VWAP |
| 綜合指標 | ❌ | Ichimoku, CCI |
| 統計套利 | ❌ | Pairs Trading |
| 止損策略 | ❌ | Parabolic SAR |

---

## 🎯 實現優先順序

### 第一階段 (1-2 週)

#### 1. Donchian Channel (唐奇安通道)

```python
# 策略邏輯
def donchian_channel(prices, period=20):
    upper = prices.rolling(period).max()   # N 日高點
    lower = prices.rolling(period).min()    # N 日低點
    middle = (upper + lower) / 2           # 中軌
    
    # 買入訊號: 價格突破上軌
    # 賣出訊號: 價格跌破下軌
    return upper, middle, lower
```

**參數**:
- Period: 20 日 (可調整 10-30)

---

#### 2. Stochastic Oscillator (隨機指標)

```python
# 策略邏輯
def stochastic(high, low, close, period=14, smooth_k=3, smooth_d=3):
    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    
    %K = 100 * (close - lowest_low) / (highest_high - lowest_low)
    %D = %K.rolling(smooth_d).mean()
    
    # 買入: %K < 20 且 %K 上穿 %D
    # 賣出: %K > 80 且 %K 下穿 %D
    return %K, %D
```

**參數**:
- Period: 14 日
- Smooth K: 3
- Smooth D: 3

---

#### 3. ATR Breakout (ATR 突破)

```python
# 策略邏輯
def atr_breakout(prices, atr_period=14, atr_multiplier=2.0):
    atr = calculate_atr(high, low, close, atr_period)
    
    upper = prices + atr * atr_multiplier
    lower = prices - atr * atr_multiplier
    
    # 買入: 價格突破 upper
    # 賣出: 價格跌破 lower
    return atr, upper, lower
```

**參數**:
- ATR Period: 14 日
- ATR Multiplier: 2.0

---

### 第二階段 (2-4 週)

#### 4. Ichimoku Kinko Hyo (一目均衡表)

```python
# 策略邏輯
def ichimoku(high, low, close, 
             tenkan=9, kijun=26, senkou_span_b=52):
    
    # 轉換線 (Tenkan-sen)
    tenkan = (high.rolling(tenkan).max() + high.rolling(tenkan).min()) / 2
    
    # 基準線 (Kijun-sen)
    kijun = (high.rolling(kijun).max() + high.rolling(kijun).min()) / 2
    
    # 先行帶 A (Senkou Span A)
    senkou_span_a = ((tenkan + kijun) / 2).shift(26)
    
    # 先行帶 B (Senkou Span B)
    senkou_span_b = ((high.rolling(senkou_span_b).max() + 
                      high.rolling(senkou_span_b).min()) / 2).shift(26)
    
    # 雲帶: senkou_span_a vs senkou_span_b
    
    return tenkan, kijun, senkou_span_a, senkou_span_b
```

---

#### 5. Parabolic SAR (拋物線指標)

```python
# 策略邏輯
def parabolic_sar(high, low, close, 
                  acceleration=0.02, maximum=0.20):
    # SAR = 前期 SAR + AF × (EP - 前期 SAR)
    # AF: 加速因子
    # EP: 極值點
    return sar
```

---

#### 6. OBV (能量潮)

```python
# 策略邏輯
def obv(close, volume):
    obv = [0]
    for i in range(1, len(close)):
        if close[i] > close[i-1]:
            obv.append(obv[-1] + volume[i])
        elif close[i] < close[i-1]:
            obv.append(obv[-1] - volume[i])
        else:
            obv.append(obv[-1])
    
    # 買入: OBV 上漲 + 價格上漲
    # 賣出: OBV 下跌 + 價格下跌
    return pd.Series(obv, index=close.index)
```

---

## 📊 新策略與現有策略的互補性

| 新策略 | 互補現有策略 | 互補原因 |
|--------|-------------|----------|
| Donchian | TrendFollower | 突破 vs 均線 |
| Stochastic | RSI_Reversal | %K/%D vs RSI |
| ATR Breakout | MultiFactorV2 | 波動率因子 |
| Ichimoku | MACDTrend | 多線索 vs 單一指標 |
| Parabolic SAR | ADXTrend | 止損 vs 趨勢強度 |
| OBV | MomentumCombo | 成交量 vs 價格動量 |

---

## 🎯 最終推薦

### 立即實現 (本週)

| # | 策略 | 代號 | 類型 | 預估時間 |
|---|------|------|------|----------|
| 1 | Donchian Channel | DC | 趨勢突破 | 2 小時 |
| 2 | Stochastic | STO | 均值回歸 | 2 小時 |
| 3 | ATR Breakout | ATRB | 波動率突破 | 2 小時 |

### 短期實現 (2 週內)

| # | 策略 | 代號 | 類型 | 預估時間 |
|---|------|------|------|----------|
| 4 | Ichimoku Cloud | ICH | 綜合分析 | 4 小時 |
| 5 | Parabolic SAR | PSAR | 趨勢止損 | 3 小時 |
| 6 | OBV | OBV | 成交量 | 2 小時 |

### 中期實現 (1 月內)

| # | 策略 | 代號 | 類型 | 預估時間 |
|---|------|------|------|----------|
| 7 | CCI | CCI | 震盪指標 | 3 小時 |
| 8 | Williams %R | WPR | 均值回歸 | 2 小時 |
| 9 | Rate of Change | ROC | 動量 | 2 小時 |

---

## 📈 擴充後策略庫

### 擴充後 17 個策略

| # | 策略 | 代號 | 類型 |
|---|------|------|------|
| 1 | MultiFactorV2 | MF | 多因子 |
| 2 | MACDTrend | MA | 趨勢 |
| 3 | ADXTrend | AD | 趨勢 |
| 4 | BollingerBounce | BB | 均值回歸 |
| 5 | RSI_Reversal | RS | 均值回歸 |
| 6 | MomentumCombo | MO | 動量 |
| 7 | SectorAdaptive | SA | 行業 |
| 8 | TrendFollower | TF | 趨勢 |
| **9** | **Donchian** | **DC** | **突破** |
| **10** | **Stochastic** | **STO** | **均值回歸** |
| **11** | **ATR Breakout** | **ATRB** | **波動率** |
| **12** | **Ichimoku** | **ICH** | **綜合** |
| **13** | **Parabolic SAR** | **PSAR** | **止損** |
| **14** | **OBV** | **OBV** | **成交量** |
| **15** | **CCI** | **CCI** | **震盪** |
| **16** | **Williams %R** | **WPR** | **均值回歸** |
| **17** | **ROC** | **ROC** | **動量** |

---

## 📝 結論

### 研究發現

1. **策略缺口**: 
   - 突破策略 (Donchian, ATR)
   - 成交量策略 (OBV)
   - 止損策略 (Parabolic SAR)

2. **實現順序**: 
   - 先補缺口策略
   - 再增加互補策略
   - 最後實現複雜策略

3. **預期效果**: 
   - 策略覆蓋率提升 100%
   - 組合多樣性增加
   - 系統穩健性提升

### 下一步

1. ✅ Z 確認後開始實現
2. 新增 3 個核心策略
3. 重新運行 18 股票回測
4. 評估策略組合效果

---

*報告生成時間: 2026-02-04*
