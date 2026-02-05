# TradeMaster Pro v2.0 - 可擴展交易系統

## 安裝方式

```bash
pip install -r requirements.txt
```

## 配置

```bash
cp config/settings.example.yaml config/settings.yaml
# 編輯 config/settings.yaml
```

## 使用方式

```bash
# 每日掃描
python main.py --task daily_scan

# 回測策略
python run_backtest.py --strategy RSI_Reversal --period 1y

# 查看可用指標
python main.py --list indicators

# 查看可用策略
python main.py --list strategies
```

## 目錄結構

```
trade_master/
├── config/              # 配置管理
├── core/                # 核心框架
├── indicators/          # 技術指標插件
├── strategies/          # 策略插件
├── risk_rules/         # 風控規則
├── data/               # 數據模組
├── alerts/             # 通知系統
├── security/          # 安全機制
├── tests/             # 測試
└── main.py            # 入口
```

## 擴展指南

參考 `docs/EXTENSION_GUIDE.md`
