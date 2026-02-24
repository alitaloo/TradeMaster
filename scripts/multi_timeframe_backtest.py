#!/usr/bin/env python3
"""
多週期回測分析
對 5m, 1h, 1d 三個週期進行回測，找出每個週期最好的指標
"""

import pandas as pd
import numpy as np
import mysql.connector
from datetime import datetime, timedelta
import os
import sys
import warnings
warnings.filterwarnings('ignore')

# MySQL 配置 - 從統一配置導入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from config.database import MYSQL_CONFIG as DB_CONFIG
except ImportError:
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster'
    }

# 股票列表 - 全部使用 US.XXXX 格式 (與富途 WATCHLIST 一致)
WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

# 所有週期都用同一個列表
STOCKS_5M = WATCHLIST
STOCKS_1H = WATCHLIST
STOCKS_1D = WATCHLIST

# 週期
TIMEFRAMES = ['5m', '1h', '1d']

# 要測試的指標策略
INDICATORS = {
    'RSI': {'type': 'momentum', 'params': {'period': 14, 'oversold': 30, 'overbought': 70}},
    'RSI_7': {'type': 'momentum', 'params': {'period': 7, 'oversold': 25, 'overbought': 75}},
    'MACD': {'type': 'trend', 'params': {'fast': 12, 'slow': 26, 'signal': 9}},
    'SMA_Cross': {'type': 'trend', 'params': {'fast': 10, 'slow': 50}},
    'EMA_Cross': {'type': 'trend', 'params': {'fast': 12, 'slow': 26}},
    'Bollinger': {'type': 'volatility', 'params': {'period': 20, 'std': 2}},
    'Stochastic': {'type': 'mean_reversion', 'params': {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80}},
    'CCI': {'type': 'mean_reversion', 'params': {'period': 20, 'oversold': -100, 'overbought': 100}},
    'Williams_R': {'type': 'mean_reversion', 'params': {'period': 14, 'oversold': -80, 'overbought': -20}},
}


def get_data(symbol: str, timeframe: str, days: int = 365) -> pd.DataFrame:
    """從數據庫獲取數據"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 計算日期範圍
    if timeframe == '5m':
        # 5分鐘: 最近 30 天
        days = 30
    elif timeframe == '1h':
        # 1小時: 使用所有可用數據 (至少90天)
        days = 400
    else:
        # 1天: 最近 365 天
        days = 365
    
    # 使用字符串比較 (timestamp 存儲為字串)
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    query = """
        SELECT timestamp, open_price, high_price, low_price, close_price, volume
        FROM kline_cache
        WHERE symbol = %s AND interval_val = %s
        AND timestamp >= %s
        ORDER BY timestamp ASC
    """
    
    cursor.execute(query, (symbol, timeframe, cutoff))
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """計算 RSI"""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """計算 MACD"""
    ema_fast = df['close'].ewm(span=fast).mean()
    ema_slow = df['close'].ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    """計算 SMA"""
    return df['close'].rolling(window=period).mean()


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """計算 EMA"""
    return df['close'].ewm(span=period).mean()


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2):
    """計算布林帶"""
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    """計算隨機指標"""
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period).mean()
    return k, d


def calculate_cci(df: pd.DataFrame, period: int = 20):
    """計算 CCI"""
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma_tp) / (0.015 * mad)
    return cci


def calculate_williams_r(df: pd.DataFrame, period: int = 14):
    """計算 Williams %R"""
    highest_high = df['high'].rolling(window=period).max()
    lowest_low = df['low'].rolling(window=period).min()
    wr = -100 * (highest_high - df['close']) / (highest_high - lowest_low)
    return wr


def generate_signals(df: pd.DataFrame, indicator: str, params: dict) -> pd.DataFrame:
    """根據指標生成信號"""
    df = df.copy()
    
    if indicator == 'RSI':
        df['rsi'] = calculate_rsi(df, params['period'])
        df['signal'] = 0
        df.loc[df['rsi'] < params['oversold'], 'signal'] = 1  # 買入
        df.loc[df['rsi'] > params['overbought'], 'signal'] = -1  # 賣出
        
    elif indicator == 'RSI_7':
        df['rsi'] = calculate_rsi(df, params['period'])
        df['signal'] = 0
        df.loc[df['rsi'] < params['oversold'], 'signal'] = 1
        df.loc[df['rsi'] > params['overbought'], 'signal'] = -1
        
    elif indicator == 'MACD':
        macd, signal_line, hist = calculate_macd(df, params['fast'], params['slow'], params['signal'])
        df['macd'] = macd
        df['macd_signal'] = signal_line
        df['hist'] = hist
        df['signal'] = 0
        df.loc[df['hist'] > 0, 'signal'] = 1
        df.loc[df['hist'] < 0, 'signal'] = -1
        
    elif indicator == 'SMA_Cross':
        df['sma_fast'] = calculate_sma(df, params['fast'])
        df['sma_slow'] = calculate_sma(df, params['slow'])
        df['signal'] = 0
        df.loc[df['sma_fast'] > df['sma_slow'], 'signal'] = 1
        df.loc[df['sma_fast'] < df['sma_slow'], 'signal'] = -1
        
    elif indicator == 'EMA_Cross':
        df['ema_fast'] = calculate_ema(df, params['fast'])
        df['ema_slow'] = calculate_ema(df, params['slow'])
        df['signal'] = 0
        df.loc[df['ema_fast'] > df['ema_slow'], 'signal'] = 1
        df.loc[df['ema_fast'] < df['ema_slow'], 'signal'] = -1
        
    elif indicator == 'Bollinger':
        upper, middle, lower = calculate_bollinger(df, params['period'], params['std'])
        df['bb_upper'] = upper
        df['bb_middle'] = middle
        df['bb_lower'] = lower
        df['signal'] = 0
        df.loc[df['close'] < df['bb_lower'], 'signal'] = 1
        df.loc[df['close'] > df['bb_upper'], 'signal'] = -1
        
    elif indicator == 'Stochastic':
        k, d = calculate_stochastic(df, params['k_period'], params['d_period'])
        df['stoch_k'] = k
        df['stoch_d'] = d
        df['signal'] = 0
        df.loc[(df['stoch_k'] < params['oversold']) & (df['stoch_d'] < params['oversold']), 'signal'] = 1
        df.loc[(df['stoch_k'] > params['overbought']) & (df['stoch_d'] > params['overbought']), 'signal'] = -1
        
    elif indicator == 'CCI':
        df['cci'] = calculate_cci(df, params['period'])
        df['signal'] = 0
        df.loc[df['cci'] < params['oversold'], 'signal'] = 1
        df.loc[df['cci'] > params['overbought'], 'signal'] = -1
        
    elif indicator == 'Williams_R':
        df['wr'] = calculate_williams_r(df, params['period'])
        df['signal'] = 0
        df.loc[df['wr'] < params['oversold'], 'signal'] = 1
        df.loc[df['wr'] > params['overbought'], 'signal'] = -1
    
    return df


def backtest(df: pd.DataFrame) -> dict:
    """執行回測"""
    if df is None or len(df) < 50:
        return None
    
    df = generate_signals_rsi(df)
    
    # 簡單回測
    position = 0
    trades = []
    capital = 100000
    shares = 0
    
    for i in range(1, len(df)):
        if df['signal'].iloc[i] == 1 and position == 0:  # 買入
            shares = capital / df['close'].iloc[i]
            position = 1
            entry_price = df['close'].iloc[i]
        elif df['signal'].iloc[i] == -1 and position == 1:  # 賣出
            capital = shares * df['close'].iloc[i]
            pnl = (df['close'].iloc[i] - entry_price) / entry_price
            trades.append(pnl)
            position = 0
            shares = 0
    
    # 計算指標
    if len(trades) == 0:
        return None
    
    total_return = (capital - 100000) / 100000
    win_rate = sum(1 for t in trades if t > 0) / len(trades)
    avg_win = sum(t for t in trades if t > 0) / len([t for t in trades if t > 0]) if any(t > 0 for t in trades) else 0
    avg_loss = sum(t for t in trades if t < 0) / len([t for t in trades if t < 0]) if any(t < 0 for t in trades) else 0
    
    # 夏普比率 (簡化)
    if np.std(trades) > 0:
        sharpe = (np.mean(trades) / np.std(trades)) * np.sqrt(252)
    else:
        sharpe = 0
    
    return {
        'total_return': total_return,
        'win_rate': win_rate,
        'trades': len(trades),
        'sharpe': sharpe,
        'avg_win': avg_win,
        'avg_loss': avg_loss
    }


def generate_signals_rsi(df: pd.DataFrame, period: int = 14, oversold: int = 30, overbought: int = 70) -> pd.DataFrame:
    """生成 RSI 信號"""
    df = df.copy()
    df['rsi'] = calculate_rsi(df, period)
    df['signal'] = 0
    df.loc[df['rsi'] < oversold, 'signal'] = 1
    df.loc[df['rsi'] > overbought, 'signal'] = -1
    return df


def run_backtest_for_indicator(df: pd.DataFrame, indicator: str, params: dict) -> dict:
    """對單一指標進行回測"""
    df = df.copy()
    
    if indicator in ['RSI', 'RSI_7']:
        df = generate_signals(df, indicator, params)
    elif indicator == 'MACD':
        df = generate_signals(df, indicator, params)
    elif indicator == 'SMA_Cross':
        df = generate_signals(df, indicator, params)
    elif indicator == 'EMA_Cross':
        df = generate_signals(df, indicator, params)
    elif indicator == 'Bollinger':
        df = generate_signals(df, indicator, params)
    elif indicator == 'Stochastic':
        df = generate_signals(df, indicator, params)
    elif indicator == 'CCI':
        df = generate_signals(df, indicator, params)
    elif indicator == 'Williams_R':
        df = generate_signals(df, indicator, params)
    else:
        return None
    
    # 回測
    position = 0
    trades = []
    capital = 100000
    shares = 0
    entry_price = 0
    
    for i in range(1, len(df)):
        if pd.isna(df['signal'].iloc[i]):
            continue
        if df['signal'].iloc[i] == 1 and position == 0:  # 買入
            shares = capital / df['close'].iloc[i]
            position = 1
            entry_price = df['close'].iloc[i]
        elif df['signal'].iloc[i] == -1 and position == 1:  # 賣出
            pnl = (df['close'].iloc[i] - entry_price) / entry_price
            trades.append(pnl)
            capital = shares * df['close'].iloc[i]
            position = 0
            shares = 0
    
    if len(trades) == 0:
        return {'trades': 0, 'total_return': 0, 'win_rate': 0, 'sharpe': 0}
    
    total_return = (capital - 100000) / 100000
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    
    # 夏普比率
    if np.std(trades) > 0:
        sharpe = (np.mean(trades) / np.std(trades)) * np.sqrt(252)
    else:
        sharpe = 0
    
    return {
        'total_return': total_return,
        'win_rate': win_rate,
        'trades': len(trades),
        'sharpe': sharpe,
        'avg_win': avg_win,
        'avg_loss': avg_loss
    }


def main():
    print("=" * 80)
    print("多週期回測分析 - 找出每個週期最好的指標")
    print("=" * 80)
    
    results = {}
    
    for tf in TIMEFRAMES:
        print(f"\n📊 週期: {tf}")
        print("-" * 60)
        
        results[tf] = {}
        
        # 根據週期選擇股票列表
        if tf == '5m':
            stocks = STOCKS_5M
        elif tf == '1h':
            stocks = STOCKS_1H
        else:
            stocks = STOCKS_1D
        
        for indicator in INDICATORS:
            params = INDICATORS[indicator]['params']
            all_results = []
            
            for symbol in stocks:
                df = get_data(symbol, tf)
                if df is None or len(df) < 50:
                    continue
                
                result = run_backtest_for_indicator(df, indicator, params)
                if result and result['trades'] > 0:
                    all_results.append(result)
            
            if all_results:
                # 計算平均
                avg_return = sum(r['total_return'] for r in all_results) / len(all_results)
                avg_sharpe = sum(r['sharpe'] for r in all_results) / len(all_results)
                avg_win_rate = sum(r['win_rate'] for r in all_results) / len(all_results)
                avg_trades = sum(r['trades'] for r in all_results) / len(all_results)
                
                results[tf][indicator] = {
                    'avg_return': avg_return,
                    'avg_sharpe': avg_sharpe,
                    'avg_win_rate': avg_win_rate,
                    'avg_trades': avg_trades
                }
                
                print(f"  {indicator:15s} | Return: {avg_return:7.2%} | Sharpe: {avg_sharpe:6.2f} | Win: {avg_win_rate:6.2%} | Trades: {avg_trades:5.1f}")
    
    # 找出每個週期最好的指標
    print("\n" + "=" * 80)
    print("🏆 最佳指標")
    print("=" * 80)
    
    for tf in TIMEFRAMES:
        if not results[tf]:
            continue
        
        best = max(results[tf].items(), key=lambda x: x[1]['avg_sharpe'])
        print(f"\n{tf} 週期: {best[0]}")
        print(f"  - 平均報酬: {best[1]['avg_return']:7.2%}")
        print(f"  - 夏普比率: {best[1]['avg_sharpe']:6.2f}")
        print(f"  - 勝率: {best[1]['avg_win_rate']:6.2%}")
        print(f"  - 平均交易次數: {best[1]['avg_trades']:5.1f}")


if __name__ == '__main__':
    main()
