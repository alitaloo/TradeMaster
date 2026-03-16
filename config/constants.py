#!/usr/bin/env python3
"""
TradeMaster Constants - 統一配置值
所有模組應從這裡導入配置值
"""

# ==================== 股票池配置 ====================

# 默認關注股票列表
DEFAULT_STOCKS = [
    "AAPL", "MSFT", "NVDA", "TSM", "AMZN", "META",
    "UBER", "MU", "AMD", "ORCL", "GOOGL", "GOOG",
    "NFLX", "ADBE", "CRM", "QCOM", "TXN", "AVGO",
    "COIN", "MSTR"
]

# 完整股票池（用於回測）
ALL_STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA",
    "TSM", "AMD", "INTC", "AVGO", "UBER", "ORCL", 
    "WDC", "MU", "COIN", "RKLB", "GOOG", "NFLX",
    "ADBE", "CRM", "QCOM", "TXN", "PYPL", "SHOP"
]

# ==================== 資金配置 ====================

# 默認初始資金
DEFAULT_CAPITAL = 100000

# 模擬交易初始資金
PAPER_TRADING_INITIAL_BALANCE = 100000

# 實盤初始資金（預設）
LIVE_TRADING_INITIAL_BALANCE = 50000

# ==================== 風控配置 ====================

RISK_CONFIG = {
    # 按比例設定（佔總資產百分比），由 RiskEngine 動態計算實際金額
    'max_single_amount_pct': 0.10,       # 單筆上限 = 總資產 × 10%
    'max_total_position_pct': 0.90,      # 總持倉上限 = 總資產 × 90%
    'max_position_per_stock_pct': 0.25,  # 單股上限 = 總資產 × 25%
    'max_leverage': 3.0,                 # 最大杠桿倍數
    'min_confidence': 0.6,              # 最小信心度
    'max_stocks': 10,                   # 最大持倉股票數
}

# 止損止盈配置
STOP_LOSS_PCT = 0.05      # 5% 止損
TAKE_PROFIT_PCT = 0.10   # 10% 止盈

# ==================== K線配置 ====================

# K線時間間隔
KLINE_INTERVALS = {
    '1m': '1分鐘',
    '5m': '5分鐘',
    '15m': '15分鐘',
    '30m': '30分鐘',
    '1h': '1小時',
    '1d': '1日',
    '1w': '1週',
}

# 默認K線間隔
DEFAULT_KLINE_INTERVAL = '5m'

# K線數據保留條數
DEFAULT_KLINE_LIMIT = 2000

# ==================== 信號配置 ====================

# 信號去重時間窗口（小時）
SIGNAL_DEDUP_HOURS = 4

# 信號強度閾值
SIGNAL_STRENGTH_THRESHOLD = {
    'STRONG': 60,   # 強信號
    'WEAK': 40,     # 弱信號
}

# ==================== 預測配置 ====================

# 預測時間窗口（小時）
PREDICTION_EXPIRY_HOURS = 4

# 最小數據量要求
MIN_DATA_POINTS = 20

# 預設預測週期（天）
DEFAULT_PREDICTION_PERIOD = 5

# ==================== 富途 API 配置 ====================

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

# ==================== 回測配置 ====================

# 回測默認參數
BACKTEST_CONFIG = {
    'initial_capital': 100000,
    'commission': 0.001,     # 0.1% 手續費
    'slippage': 0.001,       # 0.1% 滑點
}

# ==================== 導入兼容 ====================

# 向後兼容導出
STOCKS = DEFAULT_STOCKS
