# TradeMaster v2

量化交易回測系統 - RSI 均值回歸策略優化平台

## 📁 項目結構規範

```
TradeMaster_v2/
├── README.md                    # 項目說明文檔
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
│   └── debug_*.py              # 調試腳本
│
├── reports/                     # 回測報告 (最終版本)
│   ├── FINAL_REPORT.md          # 最終綜合報告
│   ├── QUALIFIED_STRATEGY_REPORT.md  # 達標策略報告
│   ├── BEST_STRATEGY_BACKTEST.md     # 最佳策略驗證報告
│   └── best_strategy_results.json     # 最佳策略JSON結果
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
├── config/                     # 配置
├── risk_rules/                 # 風險規則
├── security/                   # 安全模組
├── tools/                      # 工具腳本
├── memory/                     # 會話記憶
├── alerts/                     # 警報模組
├── modules/                    # 其他模組
├── tests/                      # 測試腳本
└── logs/                       # 日誌文件
```

---

## 📋 文件命名規範

### 回測腳本 (backtests/)
- `backtest_<strategy_name>.py` - 主要回測腳本
- `run_backtest_<purpose>.py` - 特定目的回測
- `quick_backtest_<purpose>.py` - 快速測試
- `debug_<component>.py` - 調試腳本

### 報告 (reports/)
- `FINAL_REPORT.md` - 最終報告
- `QUALIFIED_STRATEGY_REPORT.md` - 達標策略報告
- `BEST_STRATEGY_BACKTEST.md` - 最佳策略驗證
- `*_REPORT.md` - 其他主題報告

### 數據 (data/backtest_results/)
- `<strategy_name>_results.csv` - 策略結果
- `stooq_v2_results.csv` - Stooq V2 數據

---

## 🚀 快速開始

### 環境設置
```bash
cd TradeMaster_v2
pip install -r requirements.txt
```

### 運行回測
```bash
# RSI 策略回測
python backtests/backtest_rsi2.py

# 最佳策略驗證
python backtests/backtest_best_strategy.py

# 達標策略測試
python backtests/backtest_qualified.py
```

### 查看報告
```bash
cat reports/FINAL_REPORT.md
cat reports/QUALIFIED_STRATEGY_REPORT.md
```

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

## 📝 開發規範

### 添加新策略
1. 在 `strategies/` 下創建對應類別目錄
2. 繼承 `core/base_classes.py` 中的基類
3. 在 `core/registry.py` 中註冊策略
4. 在 `backtests/` 創建回測腳本
5. 結果保存到 `data/backtest_results/`
6. 報告生成到 `reports/`

### 回測結果命名
```
<策略名稱>_results_YYYYMMDD.csv
```

### 報告命名
```
<TITLE>_YYYYMMDD_HHMM.md
```

---

## 📞 聯繫

- Repository: https://github.com/alitaloo/TradeMaster.git
- Branch: dev
