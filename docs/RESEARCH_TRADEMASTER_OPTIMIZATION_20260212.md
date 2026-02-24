# TradeMaster v2 完整優化方案研究報告

**研究日期**：2026-02-12  
**研究者**：Fox（Research Agent）  
**目標**：找出 Sharpe > 1.5、報酬率 > 20%、最大回撤 < 30% 的可交易策略

---

## 一、現狀診斷分析

### 1.1 系統架構總覽

TradeMaster v2 採用插件化架構設計，核心模組包括：

| 模組 | 功能 | 狀態 |
|------|------|------|
| 核心引擎（core/） | 基類、註冊表、裝飾器 | ✅ 完善 |
| 市場環境識別（market_regime.py） | 牛/熊/震盪市場偵測 | ✅ 已實現 |
| 波動率分析（volatility.py） | ATR、動態止損、倉位計算 | ✅ 已實現 |
| 行業配置（sector_config.py） | 按行業特性調整參數 | ✅ 已實現 |
| 回測引擎（backtest.py） | 凱利公式、成本模型 | ✅ 完善 |
| 策略模組（strategies/） | 均值回歸、動量、趨勢 | ⚠️ 單一 |

### 1.2 回測結果分析

根據 2026-02-07 正式回測報告（15 隻股票，10 個策略）：

#### 表現最佳股票

| 排名 | 股票 | Sharpe | 年化報酬 | 最大回撤 | 問題 |
|------|------|--------|---------|----------|------|
| 1 | TSM | 5.55 | 11.6% | **34.2%** | 回撤超標 |
| 2 | DELL | 5.06 | 18.1% | **57.1%** | 回撤過大 |
| 3 | AMZN | 4.38 | 18.7% | **72.5%** | 回撤過大 |
| 4 | UBER | 4.18 | 19.4% | **49.3%** | 回撤過大 |
| 5 | META | 3.95 | 12.0% | **73.4%** | 回撤過大 |

#### 核心問題診斷

```
問題嚴重性評估：

🔴 高優先級：
  ├─ 最大回撤普遍過高（30%-80%）
  ├─ 沒有策略達標（Sharpe > 1.5, Return > 20%, MaxDD < 30%）
  └─ TSLA 表現極差（均值回歸策略在高波動股票上失效）

🟡 中優先級：
  ├─ 策略類型單一（過度依賴 RSI 均值回歸）
  ├─ 沒有時間週期優化（不同市場需要不同週期）
  └─ 止損機制不夠靈活（固定百分比 vs 動態 ATR）

🟢 低優先級：
  ├─ 倉位管理可進一步優化
  ├─ 可加入更多因子（基本面、成交量確認）
  └─ 組合相關性控制待加強
```

### 1.3 策略失效原因分析

#### RSI 均值回歸策略的局限性

| 市場環境 | 表現 | 原因 |
|----------|------|------|
| 趨勢市場（TSLA 暴漲暴跌） | ❌ 失效 | 逆勢交易被趨勢碾壓 |
| 高波動市場 | ❌ 頻繁假信號 | RSI 超買超賣區間頻繁觸發 |
| 震盪市場 | ✅ 有效 | 價格來回擺動，策略發揮作用 |
| 低波動市場 | ⚠️ 效果有限 | 信號稀少，獲利空間小 |

#### 根本問題

```
1. 沒有趨勢濾網
   ├─ 在下跌趨勢中買入 RSI 超賣 = 接飛刀
   └─ 缺乏「只在上升趨勢中做多」的保護

2. 沒有波動率適配
   ├─ 高波動股票（TSLA）使用相同止損參數
   ├─ 結果：止損太近被震出，或止損太遠回撤失控
   └─ 需要 ATR 動態止損而非固定百分比

3. 沒有倉位差異化
   ├─ 高波動股票應該用更小倉位
   ├─ 低波動股票可以用較大倉位
   └─ 目前所有股票使用相同風險敞口
```

---

## 二、業界最佳實踐研究

### 2.1 頂級量化機構的策略原則

| 原則 | 說明 | TradeMaster 現狀 |
|------|------|-----------------|
| **多因子確認** | 不依賴單一指標，使用多個獨立信號 | ⚠️ 只有 RSI |
| **趨勢優先** | 只在趨勢方向交易，避免逆勢 | ❌ 沒有趨勢濾網 |
| **波動率適配** | 根據市場波動性調整參數 | ⚠️ 有模組未整合 |
| **風險第一** | 永遠把損失控制放在獲利之前 | ⚠️ 止損機制簡單 |
| **分散投資** | 多策略、多標的、多時間週期 | ❌ 策略過於單一 |

### 2.2 經典策略類型對比

| 策略類型 | 適合市場 | Sharpe 範圍 | 最大回撤 | TradeMaster 實現 |
|----------|----------|-------------|----------|-----------------|
| **趨勢追蹤** | 趨勢明確 | 1.0-2.5 | 20-40% | ⚠️ 弱 |
| **均值回歸** | 震盪市場 | 0.8-1.8 | 15-30% | ✅ 主要策略 |
| **動量策略** | 強勢市場 | 1.0-2.0 | 25-45% | ⚠️ 部分實現 |
| **多策略組合** | 所有市場 | 1.5-3.0 | 10-20% | ❌ 沒有 |

### 2.3 改善關鍵路徑

```
業界共識：單一策略無法應對所有市場環境

解決方案：
┌─────────────────────────────────────────────────────────────┐
│                    多策略自适应系统                           │
│                                                              │
│   市場環境判斷 → 選擇合適策略 → 風險控制 → 信號生成            │
│                                                              │
│   ┌─────────────┐                                            │
│   │ 趨勢市場     │→ 趨勢追蹤策略（MACD、ADX）                  │
│   │             │  特點：高止盈、寬止損、順勢交易              │
│   └─────────────┘                                            │
│                                                              │
│   ┌─────────────┐                                            │
│   │ 震盪市場     │→ 均值回歸策略（RSI、布林帶）                │
│   │             │  特點：低止盈、窄止損、高頻交易              │
│   └─────────────┘                                            │
│                                                              │
│   ┌─────────────┐                                            │
│   │ 高波動市場   │→ 降低倉位、擴大止損、減少交易               │
│   │             │  特點：保守參數、嚴格風控                    │
│   └─────────────┘                                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、完整優化方案

### 3.1 策略層面優化

#### 3.1.1 新增「趨勢濾網」模組

```python
# 策略邏輯修改
class TrendFilteredRSI(BaseStrategy):
    """
    趨勢濾網 RSI 策略

    新增規則：
    1. 價格必須在 200 日均線上方（確認長期趨勢向上）
    2. 50 日均線必須在 200 日均線上方（確認中期趨勢向上）
    3. ADX > 25 表示有趨勢，避免在震盪市場交易

    只在「上升趨勢」中執行 RSI 均值回歸
    """

    def __init__(self,
                 rsi_period=14,
                 rsi_oversold=30,
                 rsi_overbought=70,
                 sma_fast=50,
                 sma_slow=200,
                 adx_period=14,
                 adx_threshold=25):

        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.sma_fast = sma_fast
        self.sma_slow = sma_slow
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold

    def generate_signal(self, ind, data):
        # 獲取指標
        rsi = ind["RSI"]["rsi"].iloc[-1]
        sma_fast = ind["SMA"]["sma"].iloc[-1]
        sma_slow = ind["SMA"]["sma200"]
        adx = ind["ADX"]["adx"].iloc[-1]

        current_price = data["Close"].iloc[-1]

        # === 趨勢濾網 ===
        trend_bull = (
            current_price > sma_slow and
            sma_fast > sma_slow and
            adx > self.adx_threshold
        )

        # === RSI 信號 ===
        if rsi < self.rsi_oversold and trend_bull:
            return SignalResult(
                signal="LONG",
                confidence=0.8,
                price=current_price,
                reason="RSI oversold + uptrend confirmed",
                metadata={"trend": "BULL", "rsi": rsi}
            )

        elif rsi > self.rsi_overbought:
            return SignalResult(
                signal="SHORT",
                confidence=0.6,
                price=current_price,
                reason="RSI overbought",
                metadata={"trend": "NEUTRAL", "rsi": rsi}
            )

        return SignalResult(
            signal="HOLD",
            confidence=0.0,
            price=current_price,
            reason="No clear signal or downtrend",
            metadata={"trend_bull": trend_bull}
        )
```

#### 3.1.2 新增「ATR 動態止損」模組

```python
# volatility.py 已經有這個模組，需要整合到回測引擎

class ATRDynamicStopLoss:
    """
    ATR 動態止損

    優勢：
    - 根據市場波動性自動調整止損距離
    - 高波動市場：止損更寬，避免被震出
    - 低波動市場：止損更窄，控制風險
    """

    def __init__(self, atr_multiplier=2.0):
        self.atr_multiplier = atr_multiplier

    def calculate_stop_loss(self, entry_price, atr, direction="LONG"):
        """
        計算止損價位

        LONG: Entry - ATR * Multiplier
        SHORT: Entry + ATR * Multiplier
        """
        if direction == "LONG":
            return entry_price - (atr * self.atr_multiplier)
        else:
            return entry_price + (atr * self.atr_multiplier)

    def calculate_position_size(self, capital, atr, entry_price, risk_pct=0.02):
        """
        根據波動率計算倉位

        Position Size = (Capital * Risk%) / (ATR$)
        """
        risk_amount = capital * risk_pct
        atr_dollar = atr

        shares = int(risk_amount / atr_dollar)
        return shares
```

#### 3.1.3 新增「多週期確認」機制

```python
class MultiTimeframeConfirmation:
    """
    多週期確認機制

    理念：
    - 大週期：確認趨勢方向（日線）
    - 中週期：找進場時機（小時線/30分鐘線）
    - 小週期：精確入場點（5分鐘線）

    優勢：
    - 避免在錯誤的週期級別逆勢交易
    - 提高信號質量，減少假突破
    """

    def __init__(self,
                 major_timeframe="daily",
                 minor_timeframe="60min",
                 entry_timeframe="15min"):

        self.major_tf = major_timeframe
        self.minor_tf = minor_timeframe
        self.entry_tf = entry_timeframe

    def get_consensus_signal(self, major_signal, minor_signal, entry_signal):
        """
        取得共識信號

        規則：
        1. 大週期必須是偏多（才能做多）
        2. 中週期給出具體方向
        3. 小週期確認入場時機
        """
        if major_signal == "BEAR":
            return "HOLD"

        if major_signal == "NEUTRAL":
            if minor_signal != major_signal:
                return "HOLD"

        if minor_signal == major_signal:
            return entry_signal

        return "HOLD"
```

### 3.2 風控層面優化

#### 3.2.1 動態倉位管理規則

```python
class DynamicPositionSizing:
    """
    動態倉位管理

    根據以下因素調整倉位：
    1. 波動率（高波動 → 小倉位）
    2. 趨勢強度（強趨勢 → 大倉位）
    3. 近期表現（連續虧損 → 降低倉位）
    """

    def __init__(self, base_risk=0.02):
        self.base_risk = base_risk
        self.consecutive_losses = 0

    def calculate_position_size(self,
                               capital,
                               atr,
                               volatility_regime="medium",
                               trend_strength=0.5,
                               recent_pnl=0):
        """
        計算最終倉位

        倉位 = 基礎倉位 × 波動率調整 × 趨勢調整 × 連續虧損調整
        """
        risk_amount = capital * self.base_risk
        atr_size = risk_amount / atr

        vol_multiplier = {
            "high": 0.5,
            "medium": 1.0,
            "low": 1.2
        }.get(volatility_regime, 1.0)

        trend_multiplier = 0.5 + trend_strength

        if recent_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        loss_multiplier = max(0.5, 1.0 - 0.25 * self.consecutive_losses)

        final_size = atr_size * vol_multiplier * trend_multiplier * loss_multiplier

        max_size = capital * 0.25 / (atr * 10)
        final_size = min(final_size, max_size)

        return int(final_size)
```

#### 3.2.2 組合風險控制規則

```python
class PortfolioRiskControl:
    """
    組合風險控制

    控制整體風險曝險：
    1. 單一股票最大倉位
    2. 單一行業最大曝險
    3. 每日最大損失限制
    4. 相關性控制
    """

    def __init__(self,
                 max_single_position=0.20,
                 max_sector_exposure=0.40,
                 max_daily_loss=0.05,
                 max_correlation=0.7):

        self.max_single = max_single_position
        self.max_sector = max_sector_exposure
        self.max_daily = max_daily_loss
        self.max_corr = max_correlation

    def check_portfolio_risk(self, portfolio, sector_exposure, daily_pnl):
        """
        檢查組合風險

        Returns: (passed: bool, violations: list)
        """
        violations = []

        for symbol, weight in portfolio.items():
            if weight > self.max_single:
                violations.append({
                    "type": "MAX_POSITION",
                    "symbol": symbol,
                    "current": weight,
                    "limit": self.max_single
                })

        for sector, exposure in sector_exposure.items():
            if exposure > self.max_sector:
                violations.append({
                    "type": "SECTOR_EXPOSURE",
                    "sector": sector,
                    "current": exposure,
                    "limit": self.max_sector
                })

        if daily_pnl < -self.max_daily:
            violations.append({
                "type": "DAILY_LOSS_LIMIT",
                "current": daily_pnl,
                "limit": -self.max_daily,
                "action": "STOP_TRADING"
            })

        return len(violations) == 0, violations
```

### 3.3 股票池優化

#### 3.3.1 問題股票處理

| 股票 | 問題 | 建議處理 |
|------|------|----------|
| **TSLA** | 高波動、均值回歸失效 | 剔除或使用專門策略 |
| **INTC** | 下降趨勢、長期弱勢 | 剔除 |
| **RKLB** | 小型股、流動性差 | 剔除或極小倉位 |

#### 3.3.2 推薦股票池

| 股票 | 類型 | 預期策略 | 原因 |
|------|------|----------|------|
| **AAPL** | 科技巨頭 | RSI + 趨勢濾網 | 穩定、流動性好 |
| **MSFT** | 科技巨頭 | 多因子策略 | 穩定、趨勢明確 |
| **NVDA** | 半導體 | 趨勢追蹤 | 強趨勢、高動能 |
| **TSM** | 半導體 | 趨勢追蹤 | 最佳 Sharpe |
| **AMZN** | 網路 | 動量策略 | 表現穩定 |
| **META** | 網路 | 趨勢追蹤 | 復甦趨勢 |
| **UBER** | 出行 | 均值回歸 | 波動適中 |
| **MU** | 儲存 | 均值回歸 | 週期性行業 |
| **AMD** | 半導體 | 趨勢追蹤 | 跟隨 NVDA |
| **ORCL** | 企業軟體 | 多因子策略 | 穩定成長 |

### 3.4 參數分組優化

#### 3.4.1 按波動率分組

| 組別 | 股票範例 | 波動率特徵 | RSI 參數 | 止損 | 倉位 |
|------|----------|------------|----------|------|------|
| **低波動** | AAPL, MSFT, ORCL | HV < 25% | 30/70 | 5% | 25% |
| **中波動** | AMZN, META, UBER | HV 25-40% | 35/65 | 8% | 20% |
| **高波動** | NVDA, AMD, TSM | HV 40-60% | 35/65 | 10% | 15% |
| **極高波動** | MU, COIN | HV > 60% | 40/60 | 15% | 10% |

### 3.5 新策略開發建議

#### 3.5.1 推薦新增策略清單

| 優先順序 | 策略名稱 | 類型 | 適合市場 | 預期效果 |
|----------|----------|------|----------|----------|
| **P0** | Trend Filtered RSI | 均值回歸 + 趨勢濾網 | 所有市場 | 提高信號質量 |
| **P0** | ATR Dynamic Stop | 風控模組 | 所有市場 | 控制回撤 |
| **P1** | MACD Trend Following | 趨勢追蹤 | 趨勢市場 | 填補策略空白 |
| **P1** | Volume Confirmed RSI | 均值回歸 + 成交量 | 震盪市場 | 過濾假突破 |
| **P2** | Multi-Timeframe System | 多週期組合 | 所有市場 | 提高穩定性 |
| **P2** | Sector Rotation | 行業輪動 | 中長線 | 增強 Alpha |

---

## 四、實施路線圖

### 4.1 短期優化（1-2 週）

#### 優先任務 P0

```
任務 1：添加趨勢濾網到現有 RSI 策略
├─ 修改 strategies/mean_reversion/rsi_reversal.py
├─ 添加 SMA 200 確認
├─ 添加 ADX 閾值過濾
└─ 重新運行回測

任務 2：實現 ATR 動態止損
├─ 修改 backtest.py 的止損邏輯
├─ 整合 volatility.py 的 ATR 計算
├─ 測試不同 ATR 倍數（1.5x, 2.0x, 2.5x）
└─ 重新運行回測

任務 3：優化股票池
├─ 剔除 TSLA、INTC、RKLB
├─ 專注於 AAPL、MSFT、NVDA、TSM、AMZN、META
└─ 重新運行回測
```

#### 預期效果

| 指標 | 優化前 | 優化後（預期） | 改善 |
|------|--------|---------------|------|
| Sharpe | 2.34 | 2.5-3.0 | +10-30% |
| Max Drawdown | 113% | < 40% | -65% |
| 達標策略數 | 0 | 5-10 | +∞ |

### 4.2 中期優化（2-4 週）

#### 優先任務 P1

```
任務 4：添加 MACD 趨勢追蹤策略
├─ 新建 strategies/trend/macd_trend.py
├─ 註冊到 registry.py
├─ 運行單獨回測
└─ 評估效果

任務 5：實現動態倉位管理
├─ 修改 backtest.py 的倉位計算
├─ 整合 volatility.py 的波動率分析
├─ 添加連續虧損保護
└─ 重新運行回測

任務 6：添加組合風險控制
├─ 新建 risk_rules/portfolio_risk.py
├─ 實現單一股票/行業限制
├─ 實現每日損失限制
└─ 測試風險控制效果
```

### 4.3 長期優化（1-2 個月）

#### 優先任務 P2

```
任務 7：多週期系統整合
├─ 添加 60 分鐘線數據支持
├─ 實現多週期確認邏輯
├─ 開發 MultiTimeframeStrategy
└─ 運行多週期回測

任務 8：成交量確認模組
├─ 新建 indicators/volume/volume_confirmation.py
├─ 添加 OBV、VWAP 指標
├─ 整合到現有策略
└─ 評估效果

任務 9：行業輪動策略
├─ 分析行業相關性
├─ 實現 SectorRotationStrategy
├─ 測試輪動效果
└─ 整合到組合管理
```

---

## 五、具體代碼修改建議

### 5.1 修改 rsi_reversal.py

```python
# === 修改後 ===
@strategy(
    name="RSI_Reversal_v2",
    type="mean_reversion",
    indicators=["RSI", "SMA", "ADX"],
    signals=["LONG", "SHORT", "HOLD", "CLOSE"],
    market_regimes=["neutral", "bull"]
)
class RSIReversalV2Strategy(BaseStrategy):
    """
    RSI 反轉策略 v2

    優化點：
    1. 添加趨勢濾網（SMA 200 確認）
    2. 添加 ADX 趨勢強度過濾
    3. 添加 CLOSE 信號（趨勢反轉時主動止盈）
    """

    def __init__(self,
                 period: int = 14,
                 oversold: float = 30.0,
                 overbought: float = 70.0,
                 sma_period: int = 200,
                 adx_period: int = 14,
                 adx_threshold: float = 25.0,
                 use_trend_filter: bool = True):

        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.sma_period = sma_period
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.use_trend_filter = use_trend_filter

    def generate_signal(self, indicators: dict, data) -> SignalResult:
        """生成交易信號"""
        rsi = indicators.get("RSI", {}).get("rsi", data["Close"] * 0 + 50)
        current_price = _get_current_price(data)

        if len(rsi) < self.period:
            return SignalResult(signal="HOLD", confidence=0.0, price=current_price, reason="Hold - insufficient data")

        latest_rsi = rsi.iloc[-1]
        prev_rsi = rsi.iloc[-2] if len(rsi) > 1 else latest_rsi

        # 獲取趨勢指標
        sma = indicators.get("SMA", {}).get("sma", pd.Series([current_price] * len(data)))
        adx = indicators.get("ADX", {}).get("adx", pd.Series([50] * len(data))).iloc[-1]

        current_sma = sma.iloc[-1]
        price_above_sma = current_price > current_sma

        # === 趨勢濾網 ===
        trend_filter_passed = True
        if self.use_trend_filter:
            trend_filter_passed = price_above_sma
            if self.use_trend_filter and adx < self.adx_threshold:
                trend_filter_passed = False

        # === 反轉信號 ===
        if latest_rsi < self.oversold and prev_rsi <= latest_rsi:
            if trend_filter_passed:
                confidence = min((self.oversold - latest_rsi) / self.oversold, 1.0)
                if price_above_sma:
                    confidence = min(confidence * 1.2, 1.0)

                return SignalResult(
                    signal="LONG",
                    confidence=confidence,
                    price=current_price,
                    reason="RSI oversold + uptrend confirmed",
                    metadata={"rsi": latest_rsi, "trend": "BULL"}
                )

        elif latest_rsi > self.overbought and prev_rsi >= latest_rsi:
            confidence = min((latest_rsi - self.overbought) / (100 - self.overbought), 1.0)
            return SignalResult(
                signal="SHORT",
                confidence=confidence,
                price=current_price,
                reason="RSI overbought with reversal signal",
                metadata={"rsi": latest_rsi}
            )

        return SignalResult(signal="HOLD", confidence=0.0, price=current_price, reason="Hold position", metadata={"rsi": latest_rsi})
```

### 5.2 修改 backtest.py 添加 ATR 止損

```python
# 在 BacktestEngine 中添加 ATR 止損支持

class BacktestEngine:
    DEFAULT_COMMISSION = 0.0015
    DEFAULT_SLIPPAGE = 0.001
    MIN_TRADES_THRESHOLD = 50
    MIN_SHARPE_THRESHOLD = 0.0

    def __init__(self, initial_capital: float = 100000,
                 commission: float = None,
                 slippage: float = None,
                 kelly_fraction: float = 0.25,
                 use_atr_stop: bool = False,
                 atr_multiplier: float = 2.0):

        self.initial_capital = initial_capital
        self.commission = commission or self.DEFAULT_COMMISSION
        self.slippage = slippage or self.DEFAULT_SLIPPAGE
        self.kelly_fraction = kelly_fraction
        self.use_atr_stop = use_atr_stop
        self.atr_multiplier = atr_multiplier

    def run_with_atr_stop(self, symbol: str, strategy, data: pd.DataFrame, strategy_name: str = "Unknown"):
        """
        運行帶 ATR 動態止損的回測
        """
        df = self._prepare_data(data.copy())
        all_indicators = calculate_indicators(df)

        capital = self.initial_capital
        position = PositionType.NONE
        entry_price = 0
        entry_date = None
        shares = 0
        trades = []
        equity = [self.initial_capital]

        # 獲取 ATR 序列
        atr = all_indicators["ATR"]["atr"]

        for i in range(len(df) - 1):
            current_price = df["Close"].iloc[i]
            current_date = df.index[i]

            ind = {}
            for ind_name, ind_values in all_indicators.items():
                ind[ind_name] = {}
                for key, series in ind_values.items():
                    if hasattr(series, 'iloc'):
                        ind[ind_name][key] = series.iloc[:i+1].reset_index(drop=True)
                    else:
                        ind[ind_name][key] = series

            signal = strategy.generate_signal(ind, df.iloc[:i+1])

            # === ATR 動態止損 ===
            if self.use_atr_stop and position != PositionType.NONE:
                current_atr = atr.iloc[i]
                atr_stop_distance = current_atr * self.atr_multiplier

                if position == PositionType.LONG:
                    atr_stop_price = entry_price - atr_stop_distance
                    if current_price < atr_stop_price:
                        # 觸發 ATR 止損
                        exit_price = current_price * (1 - self.slippage)
                        pnl = (exit_price - entry_price) * shares
                        # 記錄交易...
                        position = PositionType.NONE

                elif position == PositionType.SHORT:
                    atr_stop_price = entry_price + atr_stop_distance
                    if current_price > atr_stop_price:
                        # 觸發 ATR 止損
                        exit_price = current_price * (1 + self.slippage)
                        pnl = (entry_price - exit_price) * shares
                        # 記錄交易...
                        position = PositionType.NONE

            # === 原有信號邏輯 ===
            # ... (保持不變)

        return BacktestResult(...)
```

---

## 六、測試與驗證計劃

### 6.1 回測驗證清單

```
□ 驗證 1：趨勢濾網效果
   ├─ 對比修改前後的 Sharpe
   ├─ 檢查 TSLA 表現是否改善
   └─ 確認沒有過度濾網（信號太少）

□ 驗證 2：ATR 止損效果
   ├─ 測試不同 ATR 倍數（1.5x, 2.0x, 2.5x, 3.0x）
   ├─ 比較最大回撤改善
   └─ 檢查是否影響獲利

□ 驗證 3：股票池優化
   ├─ 剔除 TSLA、INTC、RKLB 後的回測
   ├─ 確認 Sharpe 提升
   └─ 檢查交易樣本數量足夠

□ 驗證 4：新策略效果
   ├─ MACD 趨勢追蹤策略回測
   ├─ 與 RSI 策略的相關性分析
   └─ 組合效果驗證
```

### 6.2 達標標準

```
最終目標：
├─ Sharpe > 1.5
├─ 年化報酬 > 20%
├─ 最大回撤 < 30%
└─ 交易樣本 > 50

中期目標（優化後）：
├─ Sharpe > 2.0
├─ 年化報酬 > 25%
├─ 最大回撤 < 35%
└─ 交易樣本 > 100
```

---

## 七、風險評估

### 7.1 優化風險

| 風險 | 可能性 | 影響 | 緩解措施 |
|------|--------|------|----------|
| 過度擬合 | 中 | 高 | 增加測試樣本、使用 Walk-Forward 驗證 |
| 信號過少 | 中 | 中 | 調整濾網參數、保持一定彈性 |
| 回撤增加 | 低 | 高 | 保留原有止損作為備用 |
| 系統複雜度 | 高 | 中 | 分階段實施、保持文檔更新 |

### 7.2 緩解策略

```
1. Walk-Forward 驗證
   ├─ 將數據分為樣本內和樣本外
   ├─ 在樣本內優化參數
   └─ 在樣本外驗證效果

2. 樣本外測試
   ├─ 使用 2023-2024 年數據優化
   ├─ 使用 2025 年數據驗證
   └─ 確保不是「後視偏差」

3. 敏感性分析
   ├─ 測試參數在一定範圍內的效果
   ├─ 避免「完美參數」
   └─ 選擇穩健而非最佳的參數

4. 逐步實施
   ├─ 先實施低風險優化（趨勢濾網）
   ├─ 再實施中等風險優化（ATR 止損）
   └─ 最後實施高風險優化（新策略）
```

---

## 八、總結

### 8.1 核心優化方向

```
TradeMaster v2 優化核心：

1. 策略層面
   ├─ 添加趨勢濾網 → 避免逆勢交易
   ├─ 添加 ATR 止損 → 適應市場波動
   ├─ 新增趨勢追蹤 → 填補策略空白
   └─ 新增多週期確認 → 提高信號質量

2. 風控層面
   ├─ 動態倉位管理 → 根據風險調整
   ├─ 組合風險控制 → 避免過度集中
   └─ 連續虧損保護 → 降低破產風險

3. 股票池層面
   ├─ 剔除問題股票（TSLA、INTC、RKLB）
   ├─ 專注高效策略（AAPL、NVDA、TSM）
   └─ 按波動率分組優化參數

4. 系統層面
   ├─ 整合現有模組（volatility、market_regime）
   ├─ 統一參數配置（sector_config）
   └─ 建立完整的回測框架
```

### 8.2 預期成果

```
實施完整優化方案後：

短期（1-2 週）：
├─ Sharpe: 2.34 → 2.5-3.0
├─ Max Drawdown: 113% → < 40%
├─ 達標策略數: 0 → 5-10
└─ 交易頻率: 適中

中期（2-4 週）：
├─ Sharpe: 2.5-3.0 → 3.0-4.0
├─ Max Drawdown: < 40% → < 30%
├─ 達標策略數: 5-10 → 15-20
└─ 策略多樣性: 2 → 5+

長期（1-2 個月）：
├─ Sharpe: > 3.5
├─ Max Drawdown: < 25%
├─ 實盤可行策略: 5+
└─ 多策略組合系統
```

---

## 附錄

### A. 參考文獻

- **[1]** Quantitative Trading: How to Build Your Own Algorithmic Trading Business（Ernest P. Chan）
- **[2]** Algorithmic Trading: Winning Strategies and Their Rationale（Ernest P. Chan）
- **[3]** Advances in Financial Machine Learning（Marcos López de Prado）

### B. 相關文件

- README.md - 項目總覽
- TECHNICAL_SPEC.md - 技術規格
- SYSTEM_OPTIMIZATION.md - 歷史優化記錄
- QUALIFIED_STRATEGY_REPORT.md - 達標策略報告
- TOP10_STRATEGY_REPORT.md - Top10 策略報告

### C. 聯繫方式

- 問題回報：請通過 Telegram 聯繫
- 代碼審查：@bull_zzz_bot 或 @alita_zzz_bot

---

*研究完成