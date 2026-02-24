#!/usr/bin/env python3
"""
多週期回測分析 - 找出每支股票每個週期最好的指標
輸出: 每支股票的最佳策略配置
"""

import pandas as pd
import numpy as np
import mysql.connector
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

# 數據庫連接
DB_CONFIG = {
    'host': 'localhost',
    'user': 'alita',
    'password': 'alitamysql',
    'database': 'trademaster'
}

# 股票列表 (US.XXXX 格式)
STOCKS = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

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
    
    if timeframe == '5m':
        days = 30
    elif timeframe == '1h':
        days = 400
    else:
        days = 365
    
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
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = df['close'].ewm(span=fast).mean()
    ema_slow = df['close'].ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram


def calculate_sma(df: pd.DataFrame, period: int) -> pd.Series:
    return df['close'].rolling(window=period).mean()


def calculate_ema(df: pd.DataFrame, period: int) -> pd.Series:
    return df['close'].ewm(span=period).mean()


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2):
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3):
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period).mean()
    return k, d


def calculate_cci(df: pd.DataFrame, period: int = 20):
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(window=period).mean()
    mad = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (tp - sma_tp) / (0.015 * mad)
    return cci


def calculate_williams_r(df: pd.DataFrame, period: int = 14):
    highest_high = df['high'].rolling(window=period).max()
    lowest_low = df['low'].rolling(window=period).min()
    wr = -100 * (highest_high - df['close']) / (highest_high - lowest_low)
    return wr


def generate_signals(df: pd.DataFrame, indicator: str, params: dict) -> pd.DataFrame:
    df = df.copy()
    
    if indicator in ['RSI', 'RSI_7']:
        df['rsi'] = calculate_rsi(df, params['period'])
        df['signal'] = 0
        df.loc[df['rsi'] < params['oversold'], 'signal'] = 1
        df.loc[df['rsi'] > params['overbought'], 'signal'] = -1
        
    elif indicator == 'MACD':
        macd, signal_line, hist = calculate_macd(df, params['fast'], params['slow'], params['signal'])
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
        df['bb_lower'] = lower
        df['signal'] = 0
        df.loc[df['close'] < df['bb_lower'], 'signal'] = 1
        df.loc[df['close'] > df['bb_upper'], 'signal'] = -1
        
    elif indicator == 'Stochastic':
        k, d = calculate_stochastic(df, params['k_period'], params['d_period'])
        df['stoch_k'] = k
        df['stoch_d'] = d
        df['signal'] = 0
        oversold_val = params.get('oversold', 20)
        overbought_val = params.get('overbought', 80)
        df.loc[(df['stoch_k'] < oversold_val) & (df['stoch_d'] < oversold_val), 'signal'] = 1
        df.loc[(df['stoch_k'] > overbought_val) & (df['stoch_d'] > overbought_val), 'signal'] = -1
        
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


def run_backtest(df: pd.DataFrame, indicator: str, params: dict) -> dict:
    """執行回測"""
    if df is None or len(df) < 50:
        return None
    
    df = generate_signals(df, indicator, params)
    
    position = 0
    trades = []
    capital = 100000
    shares = 0
    entry_price = 0
    
    for i in range(1, len(df)):
        if pd.isna(df['signal'].iloc[i]):
            continue
        if df['signal'].iloc[i] == 1 and position == 0:
            shares = capital / df['close'].iloc[i]
            position = 1
            entry_price = df['close'].iloc[i]
        elif df['signal'].iloc[i] == -1 and position == 1:
            pnl = (df['close'].iloc[i] - entry_price) / entry_price
            trades.append(pnl)
            capital = shares * df['close'].iloc[i]
            position = 0
            shares = 0
    
    if len(trades) == 0:
        return None
    
    total_return = (capital - 100000) / 100000
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t < 0]
    win_rate = len(wins) / len(trades) if trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    
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
    print("多股票多週期策略回測 - 找出每支股票每個週期最好的指標")
    print("=" * 80)
    
    # 結果存儲: {stock: {timeframe: {indicator: result}}}
    all_results = {}
    
    for symbol in STOCKS:
        all_results[symbol] = {}
        print(f"\n📊 {symbol}")
        
        for tf in TIMEFRAMES:
            print(f"  ⏱️ {tf}...", end=" ")
            
            df = get_data(symbol, tf)
            if df is None or len(df) < 50:
                print("數據不足")
                continue
            
            best_indicator = None
            best_sharpe = float('-inf')
            best_result = None
            
            for indicator, config in INDICATORS.items():
                params = config['params']
                result = run_backtest(df, indicator, params)
                
                if result and result['trades'] > 0:
                    # 用夏普比率排序
                    if result['sharpe'] > best_sharpe:
                        best_sharpe = result['sharpe']
                        best_indicator = indicator
                        best_result = result
            
            if best_indicator:
                all_results[symbol][tf] = {
                    'indicator': best_indicator,
                    'params': INDICATORS[best_indicator]['params'],
                    'sharpe': best_result['sharpe'],
                    'return': best_result['total_return'],
                    'win_rate': best_result['win_rate'],
                    'trades': best_result['trades']
                }
                print(f"✅ {best_indicator} (Sharpe: {best_result['sharpe']:.2f})")
            else:
                print("❌ 無有效結果")
    
    # 生成配置
    print("\n" + "=" * 80)
    print("🏆 最佳策略配置")
    print("=" * 80)
    
    stock_strategy_config = {}
    
    for symbol, timeframes in all_results.items():
        stock_strategy_config[symbol] = {}
        for tf, data in timeframes.items():
            stock_strategy_config[symbol][tf] = {
                'indicator': data['indicator'],
                'params': data['params']
            }
    
    # 打印配置
    print("\n📝 fox_analysis.py 配置:")
    print("-" * 60)
    print("STOCK_STRATEGY_CONFIG = {")
    for symbol, timeframes in stock_strategy_config.items():
        print(f"    '{symbol}': {{")
        for tf, config in timeframes.items():
            print(f"        '{tf}': {{'indicator': '{config['indicator']}', 'params': {config['params']}}},")
        print(f"    }},")
    print("}")
    
    # 保存到文件
    with open('/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/scripts/stock_strategy_config.json', 'w') as f:
        json.dump(stock_strategy_config, f, indent=2)
    
    print("\n✅ 配置已保存到 stock_strategy_config.json")
    
    # 保存到 MySQL
    print("\n💾 保存到 MySQL...")
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    for symbol, timeframes in all_results.items():
        for tf, data in timeframes.items():
            try:
                # 檢查是否存在
                cursor.execute(
                    "SELECT id FROM stock_strategies WHERE symbol = %s AND timeframe = %s",
                    (symbol, tf)
                )
                exists = cursor.fetchone()
                
                params_json = json.dumps(data['params'])
                
                if exists:
                    # 更新
                    cursor.execute("""
                        UPDATE stock_strategies 
                        SET indicator = %s, params = %s, sharpe = %s, 
                            return_pct = %s, win_rate = %s, trades = %s
                        WHERE symbol = %s AND timeframe = %s
                    """, (
                        data['indicator'],
                        params_json,
                        data['sharpe'],
                        data['return'],
                        data['win_rate'],
                        data['trades'],
                        symbol, tf
                    ))
                else:
                    # 插入
                    cursor.execute("""
                        INSERT INTO stock_strategies 
                        (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        symbol, tf,
                        data['indicator'],
                        params_json,
                        data['sharpe'],
                        data['return'],
                        data['win_rate'],
                        data['trades']
                    ))
            except Exception as e:
                print(f"  ❌ 保存失敗: {symbol} {tf} - {e}")
    
    conn.commit()
    conn.close()
    print("✅ 已保存到 MySQL")
    
    # 統計
    indicator_usage = {}
    for symbol, timeframes in stock_strategy_config.items():
        for tf, config in timeframes.items():
            ind = config['indicator']
            indicator_usage[ind] = indicator_usage.get(ind, 0) + 1
    
    print("\n📊 指標使用統計:")
    for ind, count in sorted(indicator_usage.items(), key=lambda x: -x[1]):
        print(f"  {ind}: {count}次")


if __name__ == '__main__':
    main()
