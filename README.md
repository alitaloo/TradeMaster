# TradeMaster v2

量化交易回測系統 - RSI 均值回歸策略優化平台

---

## 🎯 項目目標

**目標**：找到 Sharpe > 1.5、報酬率 > 20%、最大回撤 < 30% 的可交易策略

**口號**：規範才有整齊的步伐，讓項目快速迭代 🚀

---

## 📁 項目結構規範

```
TradeMaster_v2/
├── README.md                    # 項目說明文檔 (重要！)
├── requirements.txt             # Python 依賴
├── .git/                        # Git 版本控制
│
├── core/                        # 核心引擎模組
│   ├── base_classes.py          # 回測基類
│   ├── registry.py              # 策略註冊表
│   ├── market_regime.py         # 市場體制識別
│   ├── volatility.py            # 波動率計算
│   ├── sector_config.py         # 板塊配置
│   └── decorators.py           # 裝飾器工具
│
├── strategies/                  # 策略模組
│   ├── mean_reversion/          # 均值回歸策略
│   │   └── rsi_reversal.py      # RSI 逆轉策略
│   ├── momentum/                # 動量策略
│   │   └── new_strategies.py
│   ├── trend/                   # 趨勢策略
│   │   ├── macd_trend.py
│   │   └── adx_trend.py
│   ├── composite/               # 複合策略
│   │   ├── composite_set1.py
│   │   ├── composite_set2.py
│   │   └── composite_v3.py
│   ├── volume/                  # 成交量策略
│   │   └── volume_strategies.py
│   └── high_sharpe_strategies.py # 高夏普策略
│
├── indicators/                  # 技術指標模組
│   ├── momentum/
│   ├── trend/
│   ├── volatility/
│   └── comprehensive/           # 綜合指標
│       ├── ichimoku.py
│       └── parabolic_sar.py
│
├── data/                        # 數據目錄
│   ├── historical/              # 歷史K線數據
│   │   ├── daily/              # 日線數據
│   │   └── intraday/           # 分鐘線數據
│   ├── backtest_results/        # 回測結果 (CSV格式)
│   │   ├── rsi2_results.csv     # RSI策略結果
│   │   ├── trend_filtered_results.csv
│   │   └── stooq_v2_results.csv
│   └── trademaster.db           # SQLite 數據庫
│
├── backtests/                   # 回測腳本 (所有回測相關腳本)
│   ├── backtest_rsi2.py         # RSI 策略回測
│   ├── backtest_trend_filtered.py
│   ├── backtest_stooq.py
│   ├── backtest_stooq_v2.py
│   ├── backtest_best_strategy.py # 最佳策略驗證
│   ├── backtest_qualified.py     # 達標策略測試
│   ├── run_backtest_*.py        # 各種回測運行腳本
│   ├── quick_backtest_*.py      # 快速回測腳本
│   ├── quick_optimize.py        # 快速優化
│   ├── final_strategy_test.py   # 最終策略測試
│   ├── run_top10_backtest.py    # Top10 策略回測
│   └── debug_*.py              # 調試腳本
│
├── reports/                     # 回測報告
│   ├── FINAL_REPORT.md          # 最終綜合報告
│   ├── QUALIFIED_STRATEGY_REPORT.md  # 達標策略報告
│   ├── BEST_STRATEGY_BACKTEST.md     # 最佳策略驗證報告
│   ├── TOP10_STRATEGY_REPORT.md      # Top10 策略回測報告
│   ├── *_RESULTS.md             # 策略結果報告
│   └── *_RESULTS.json           # 策略結果 JSON
│
├── docs/                        # 開發文檔和技術文檔
│   ├── TECHNICAL_SPEC.md        # 技術規格
│   ├── STRATEGY_RESEARCH.md     # 策略研究
│   ├── NEW_STRATEGIES_REPORT.md # 新策略報告
│   ├── EXTENSION_GUIDE.md       # 擴展指南
│   ├── P0_FIXES_REPORT.md       # 重要修復報告
│   ├── SYSTEM_GAPS_ANALYSIS.md  # 系統缺口分析
│   ├── SYSTEM_OPTIMIZATION.md   # 系統優化
│   └── NOTION_FOLDER_INDEX.md   # Notion 索引
│
├── archives/                    # 歸檔目錄
│   └── notion_export/           # Notion 導出文件
│       ├── NOTION_PART1_TECHNICAL.txt
│       ├── NOTION_PART2_BACKTEST.txt
│       └── NOTION_PART3_STRATEGY.txt
│
├── signals/                     # 信號生成模組
├── api/                         # API 服務
├── config/                      # 配置
├── risk_rules/                  # 風險規則
├── security/                   # 安全模組
├── tools/                      # 工具腳本
├── memory/                     # 會話記憶
├── alerts/                     # 警報模組
├── modules/                    # 其他模組
├── tests/                      # 測試腳本
└── logs/                       # 日誌文件
```

---

## 📋 配置股票清單

### 🔬 實驗回測
**目的**：快速驗證策略有效性
- AAPL (蘋果)
- TSLA (特斯拉)

### 🎯 正式回測
**目的**：找出可實際交易的策略
| # | 股票代碼 | 公司名稱 |
|---|---------|----------|
| 1 | TSLA | Tesla (特斯拉) |
| 2 | AAPL | Apple (蘋果) |
| 3 | AMZN | Amazon (亞馬遜) |
| 4 | NVDA | NVIDIA (英偉達) |
| 5 | META | Meta (Facebook) |
| 6 | MSFT | Microsoft (微軟) |
| 7 | UBER | Uber (優步) |
| 8 | INTC | Intel (英特爾) |
| 9 | AMD | AMD |
| 10 | RKLB | Rocket Lab (火箭實驗室) |
| 11 | WDC | Western Digital (西部數據) |
| 12 | MU | Micron (美光) |
| 13 | TSM | TSMC (台積電) |
| 14 | ORCL | Oracle (甲骨文) |
| 15 | DELL | Dell (戴爾) |

---

## 📋 文件命名規範

### 回測腳本 (backtests/)
| 前綴 | 用途 | 示例 |
|------|------|------|
| `backtest_` | 主要回測腳本 | `backtest_rsi2.py` |
| `run_` | 特定目的回測 | `run_top10_backtest.py` |
| `quick_` | 快速測試 | `quick_backtest.py` |
| `final_` | 最終驗證 | `final_strategy_test.py` |
| `debug_` | 調試腳本 | `debug_*.py` |

### 數據文件 (data/backtest_results/)
| 格式 | 用途 | 示例 |
|------|------|------|
| `<strategy>_results.csv` | 策略回測結果 | `rsi2_results.csv` |
| `stooq_v2_results.csv` | Stooq V2 數據 | - |
| `trend_filtered_results.csv` | 趨勢過濾結果 | - |

### 報告文件 (reports/)
| 類型 | 命名格式 | 示例 |
|------|----------|------|
| **調研報告** | `RESEARCH_<topic>_YYYYMMDD.md` | `RESEARCH_RSI_20260207.md` |
| **測試報告** | `TEST_<purpose>_YYYYMMDD.md` | `TEST_QUALIFIED_20260207.md` |
| **Top10報告** | `TOP10_STRATEGY_REPORT.md` | - |
| **達標報告** | `QUALIFIED_STRATEGY_REPORT.md` | - |
| **最佳策略報告** | `BEST_STRATEGY_BACKTEST.md` | - |
| **最終報告** | `FINAL_REPORT.md` | - |
| **結果JSON** | `<type>_results.json` | `top10_results.json` |

---

## 🔄 工作流程規範

### 完整流程（必須嚴格遵守）

```
┌─────────────────────────────────────────────────────────────────┐
│                        完整工作流程                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1️⃣ 調研 (Research)                                             │
│     ├── 閱讀現有文檔和報告                                       │
│     ├── 研究市場上量化機構常用策略                               │
│     ├── 生成調研報告 → docs/RESEARCH_*.md                       │
│     └── 輸出：策略想法、參數範圍                                 │
│                                                                 │
│  2️⃣ 開發 (Development)                                         │
│     ├── 在 strategies/ 實現新策略                               │
│     ├── 在 indicators/ 添加必要指標                             │
│     ├── 更新 core/registry.py 註冊策略                           │
│     └── 遵循代碼規範                                             │
│                                                                 │
│  3️⃣ 實驗回測 (Experiment Backtest)                              │
│     ├── 對象：AAPL, TSLA                                       │
│     ├── 腳本：quick_*.py 或 debug_*.py                          │
│     ├── 數據：data/backtest_results/*.csv                       │
│     └── 輸出：docs/TEST_*.md                                    │
│                                                                 │
│  4️⃣ 正式回測 (Production Backtest)                              │
│     ├── 對象：15 隻正式股票清單                                  │
│     ├── 腳本：run_*.py 或 final_*.py                             │
│     ├── 數據：data/backtest_results/*.csv                       │
│     └── 輸出：reports/TOP10_*.md 或 QUALIFIED_*.md               │
│                                                                 │
│  5️⃣ 數據下載 (Data Download)                                     │
│     ├── 腳本：download_data.py                                  │
│     ├── 目標：補齊缺失股票的歷史數據                             │
│     └── 數據存放：data/historical/daily/                        │
│                                                                 │
│  6️⃣ 報告生成 (Report Generation)                                │
│     ├── 調研報告 → docs/RESEARCH_*.md                          │
│     ├── 測試報告 → docs/TEST_*.md                               │
│     ├── 回測報告 → reports/TOP10_*.md                            │
│     └── 遵循報告命名規範                                         │
│                                                                 │
│  7️⃣ Git 提交 (Commit & Push)                                   │
│     ├── commit 前確保代碼可運行                                  │
│     ├── 提交信息清晰描述改動                                     │
│     └── push 到 dev 分支                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 每次操作前檢查清單

- [ ] 閱讀 README.md（必須！）
- [ ] 確認使用的股票清單（實驗 vs 正式）
- [ ] 確認輸出目錄（docs vs reports）
- [ ] 遵循文件命名規範
- [ ] 確認工作流程順序

---

## 📊 策略成果

### 達標策略 (Sharpe > 1.5, Return > 20%, MaxDD < 30%)

| 標的 | Sharpe | 年化報酬 | 最大回撤 | 狀態 |
|------|--------|---------|----------|------|
| **AMAT** | **3.45** | **106.78%** | **14.69%** | 🏆 最佳 |
| **AAPL** | **1.58** | **31.89%** | **19.32%** | ✅ |
| MU | 2.60 | 90.14% | 29.94% | ✅ |
| SMH | 2.39 | 70.11% | 28.04% | ✅ |

### 最佳策略參數 (AMAT)
- **RSI 買入**: < 32
- **RSI 賣出**: > 74
- **止損**: 5.8%
- **止盈**: 15%
- **RSI 週期**: 14

---

## 🚀 快速開始

### 環境設置
```bash
cd TradeMaster_v2
pip install -r requirements.txt
```

### 運行回測
```bash
# 實驗回測 (AAPL, TSLA)
python backtests/quick_backtest.py

# Top10 策略回測
python backtests/run_top10_backtest.py

# 最佳策略驗證
python backtests/backtest_best_strategy.py
```

### 查看報告
```bash
# Top10 報告
cat reports/TOP10_STRATEGY_REPORT.md

# 達標策略報告
cat reports/QUALIFIED_STRATEGY_REPORT.md
```

---

## 🚀 實盤交易系統 (v2 升級)

2026-02-13 升級為支持實盤交易功能

### 新增項目結構

```
TradeMaster_v2/
├── migrations/                    # 數據庫遷移
│   ├── 001_signals.sql          # 信號表
│   ├── 002_positions.sql        # 持倉表
│   ├── 003_orders.sql           # 訂單表
│   ├── 004_news_notifications_risk.sql  # 新聞/推送/風控日誌表
│   └── migrate_v2.py           # 遷移腳本
│
├── api/                         # API 端點 (已擴展)
│   ├── signals_bp.py            # 信號 API
│   ├── positions_bp.py          # 持倉 API
│   ├── orders_bp.py            # 訂單 API
│   └── ...
│
├── core/                        # 核心引擎 (已擴展)
│   ├── risk_engine.py           # 風控引擎
│   └── position_manager.py      # 持倉管理
│
├── middleware/                  # 中間件
│   └── auth.py                 # API 認證
│
└── utils/                      # 工具
    ├── logger.py               # 結構化日誌
    └── metrics.py              # 監控指標
```

### API 端點

| 端點 | 功能 |
|------|------|
| `GET /api/v1/signals` | 獲取信號列表 |
| `POST /api/v1/signals` | 創建新信號 |
| `GET /api/v1/positions` | 獲取持倉列表 |
| `GET /api/v1/positions/summary` | 持倉摘要 |
| `GET /api/v1/orders` | 獲取訂單列表 |
| `POST /api/v1/orders` | 創建訂單 |

### 數據庫表

| 表名 | 功能 |
|------|------|
| `signals` | 交易信號記錄 |
| `positions` | 持倉記錄 |
| `orders` | 訂單記錄 |
| `news` | 新聞記錄 |
| `notifications` | 推送記錄 |
| `risk_logs` | 風控日誌 |

### 運行遷移

```bash
# 執行遷移
python3 migrations/migrate_v2.py

# 查看狀態
python3 migrations/migrate_v2.py --status

# 回滾
python3 migrations/migrate_v2.py --rollback
```

### API Key 認證

**用途：**
- 保護 API 不被隨便訪問
- 區分不同用戶/應用
- 記錄誰調用了 API
- 必要时可以停用某個 key

**使用方式：**

```bash
# 請求時帶上 API Key
curl -H "Authorization: sk_abc123_xyz" \
     http://localhost:8080/api/v1/positions
```

**認證流程：**
```
1. 調用 API 時帶上 Header: Authorization: <api_key>
2. 服務器驗證 key 是否有效
3. 有效 → 返回數據，無效 → 返回 401 錯誤
```

### 風控引擎

**功能：**
- 單筆金額檢查 (上限 $10,000)
- 總持倉檢查 (上限 $50,000)
- 單股票持倉檢查 (上限 $20,000)
- 止損檢查
- 信心度檢查
- 杠桿檢查
- 風險評分 (0-100)

### 持倉管理

**功能：**
- 持倉 CRUD
- 盈虧計算
- 持倉同步
- 持倉報警 (-5% 止損 / +10% 止盈)

---

## 📝 開發規範

### 添加新策略
1. 在 `strategies/` 下創建對應類別目錄
2. 繼承 `core/base_classes.py` 中的基類
3. 在 `core/registry.py` 中註冊策略
4. 在 `backtests/` 創建回測腳本
5. 結果保存到 `data/backtest_results/`
6. 報告生成到對應目錄（docs/ 或 reports/）

### 數據覆蓋檢查
```bash
# 檢查現有數據覆蓋的股票
cut -d',' -f1 data/backtest_results/*.csv | sort | uniq
```

---

## 📞 聯繫

- Repository: https://github.com/alitaloo/TradeMaster.git
- Branch: dev

---

*Updated: 2026-02-13*
*規範創造效率，流程保證質量*
