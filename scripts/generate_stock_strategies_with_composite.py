#!/usr/bin/env python3
"""
多股票多週期 + 組合策略 回測
找出每支股票每個週期最好的指標 + 組合策略
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

# 股票列表
STOCKS = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

TIMEFRAMES = ['5m', '1h', '1d']

# 單一指標策略
SINGLE_INDICATORS = {
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

# 組合策略 (簡化版)
COMPOSITE_STRATEGIES = {
    # RSI + MACD 組合
    'RSI_MACD': {
        'indicators': ['RSI', 'MACD'],
        'logic': 'both_agree'  # 兩個指標都信號一致才動作
    },
    # RSI + Bollinger 組合
    'RSI_BB': {
        'indicators': ['RSI', 'Bollinger'],
        'logic': 'both_agree'
    },
    # RSI + Stochastic 組合
    'RSI_STOCH': {
        'indicators': ['RSI', 'Stochastic'],
        'logic': 'both_agree'
    },
    # MACD + SMA 組合
    'MACD_SMA': {
        'indicators': ['MACD', 'SMA_Cross'],
        'logic': 'both_agree'
    },
    # MACD + EMA 組合
    'MACD_EMA': {
        'indicators': ['MACD', 'EMA_Cross'],
        'logic': 'both_agree'
    },
    # Bollinger + Stochastic 組合
    'BB_STOCH': {
        'indicators': ['Bollinger', 'Stochastic'],
        'logic': 'both_agree'
    },
    # CCI + Williams_R 組合
    'CCI_WR': {
        'indicators': ['CCI', 'Williams_R'],
        'logic': 'both_agree'
    },
    # 三重組合: RSI + MACD + Bollinger
    'RSI_MACD_BB': {
        'indicators': ['RSI', 'MACD', 'Bollinger'],
        'logic': 'all_agree'  # 三個都信號一致
    },
}


def get_data(symbol: str, timeframe: str, days: int = 365) -> pd.DataFrame:
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


def calculate_all_indicators(df: pd.DataFrame) -> dict:
    """計算所有指標"""
    indicators = {}
    
    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    indicators['RSI'] = 100 - (100 / (1 + rs))
    
    # RSI 7
    delta7 = df['close'].diff()
    gain7 = delta7.where(delta7 > 0, 0).rolling(window=7).mean()
    loss7 = (-delta7.where(delta7 < 0, 0)).rolling(window=7).mean()
    rs7 = gain7 / loss7
    indicators['RSI_7'] = 100 - (100 / (1 + rs7))
    
    # MACD
    ema_fast = df['close'].ewm(span=12).mean()
    ema_slow = df['close'].ewm(span=26).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=9).mean()
    indicators['MACD'] = macd - signal_line  # histogram
    
    # SMA
    indicators['SMA_Cross'] = df['close'].rolling(10).mean() - df['close'].rolling(50).mean()
    
    # EMA
    indicators['EMA_Cross'] = df['close'].ewm(span=12).mean() - df['close'].ewm(span=26).mean()
    
    # Bollinger
    sma = df['close'].rolling(20).mean()
    std = df['close'].rolling(20).std()
    indicators['Bollinger'] = (df['close'] - sma) / std  # z-score
    
    # Stochastic
    low_min = df['low'].rolling(14).min()
    high_max = df['high'].rolling(14).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    indicators['Stochastic'] = k - k.rolling(3).mean()
    
    # CCI
    tp = (df['high'] + df['low'] + df['close']) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean())
    indicators['CCI'] = (tp - sma_tp) / (0.015 * mad)
    
    # Williams R
    highest_high = df['high'].rolling(14).max()
    lowest_low = df['low'].rolling(14).min()
    indicators['Williams_R'] = -100 * (highest_high - df['close']) / (highest_high - lowest_low)
    
    return indicators


def get_single_signal(indicator_name: str, indicators: dict) -> int:
    """獲取單一指標信號"""
    ind = indicators.get(indicator_name)
    if ind is None or len(ind) == 0 or pd.isna(ind.iloc[-1]):
        return 0
    
    val = ind.iloc[-1]
    
    # 根據指標類型計算信號
    if indicator_name in ['RSI', 'RSI_7']:
        if val < 30:
            return 1
        elif val > 70:
            return -1
    elif indicator_name == 'MACD':
        if val > 0:
            return 1
        elif val < 0:
            return -1
    elif indicator_name in ['SMA_Cross', 'EMA_Cross']:
        if val > 0:
            return 1
        elif val < 0:
            return -1
    elif indicator_name == 'Bollinger':
        if val < -1:
            return 1
        elif val > 1:
            return -1
    elif indicator_name == 'Stochastic':
        if val < -60:  # 两者都超卖
            return 1
        elif val > 60:
            return -1
    elif indicator_name == 'CCI':
        if val < -100:
            return 1
        elif val > 100:
            return -1
    elif indicator_name == 'Williams_R':
        if val < -80:
            return 1
        elif val > -20:
            return -1
    
    return 0


def get_composite_signal(strategy_name: str, indicators: dict) -> int:
    """獲取組合策略信號"""
    config = COMPOSITE_STRATEGIES.get(strategy_name)
    if not config:
        return 0
    
    indicator_names = config['indicators']
    signals = [get_single_signal(ind, indicators) for ind in indicator_names]
    
    # 過濾掉 0 (無信號)
    valid_signals = [s for s in signals if s != 0]
    
    if not valid_signals:
        return 0
    
    if config['logic'] == 'both_agree':
        # 所有有效信號必須一致
        if len(valid_signals) >= 2 and len(set(valid_signals)) == 1:
            return valid_signals[0]
    elif config['logic'] == 'all_agree':
        # 所有指標都必須有效且一致
        if len(valid_signals) == len(indicator_names) and len(set(valid_signals)) == 1:
            return valid_signals[0]
    
    return 0


def run_backtest(df: pd.DataFrame, strategy_func, is_composite: bool = False) -> dict:
    """執行回測"""
    if df is None or len(df) < 50:
        return None
    
    indicators = calculate_all_indicators(df)
    
    position = 0
    trades = []
    capital = 100000
    shares = 0
    entry_price = 0
    
    for i in range(1, len(df)):
        if is_composite:
            signal = strategy_func(indicators)
        else:
            signal = get_single_signal(strategy_func, {strategy_func: indicators.get(strategy_func, pd.Series([50]))})
        
        if signal == 1 and position == 0:
            shares = capital / df['close'].iloc[i]
            position = 1
            entry_price = df['close'].iloc[i]
        elif signal == -1 and position == 1:
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
    
    if np.std(trades) > 0:
        sharpe = (np.mean(trades) / np.std(trades)) * np.sqrt(252)
    else:
        sharpe = 0
    
    return {
        'total_return': total_return,
        'win_rate': win_rate,
        'trades': len(trades),
        'sharpe': sharpe
    }


def main():
    print("=" * 80)
    print("多股票多週期 + 組合策略 回測")
    print("=" * 80)
    
    all_results = {}
    
    # 所有策略 (單一 + 組合)
    all_strategies = {}
    for name, config in SINGLE_INDICATORS.items():
        all_strategies[name] = {'type': 'single', 'config': config}
    for name, config in COMPOSITE_STRATEGIES.items():
        all_strategies[name] = {'type': 'composite', 'config': config}
    
    for symbol in STOCKS:
        all_results[symbol] = {}
        print(f"\n📊 {symbol}")
        
        for tf in TIMEFRAMES:
            print(f"  ⏱️ {tf}...", end=" ")
            
            df = get_data(symbol, tf)
            if df is None or len(df) < 50:
                print("數據不足")
                continue
            
            best_strategy = None
            best_sharpe = float('-inf')
            best_result = None
            
            # 測試所有策略
            for strategy_name, strategy_info in all_strategies.items():
                if strategy_info['type'] == 'single':
                    result = run_backtest(df, strategy_name, False)
                else:
                    result = run_backtest(df, lambda ind, s=strategy_name: get_composite_signal(s, ind), True)
                
                if result and result['trades'] > 3 and result['sharpe'] > best_sharpe:
                    best_sharpe = result['sharpe']
                    best_strategy = strategy_name
                    best_result = result
            
            if best_strategy:
                is_composite = all_strategies[best_strategy]['type'] == 'composite'
                all_results[symbol][tf] = {
                    'indicator': best_strategy,
                    'is_composite': is_composite,
                    'sharpe': best_result['sharpe'],
                    'return': best_result['total_return'],
                    'win_rate': best_result['win_rate'],
                    'trades': best_result['trades']
                }
                print(f"✅ {best_strategy} (Sharpe: {best_result['sharpe']:.2f})")
            else:
                print("❌ 無有效結果")
    
    # 保存到 MySQL
    print("\n" + "=" * 80)
    print("💾 保存到 MySQL...")
    print("=" * 80)
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    composite_count = 0
    single_count = 0
    
    for symbol, timeframes in all_results.items():
        for tf, data in timeframes.items():
            params = {'is_composite': data['is_composite']}
            
            cursor.execute("""
                INSERT INTO stock_strategies (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    indicator = VALUES(indicator),
                    params = VALUES(params),
                    sharpe = VALUES(sharpe),
                    return_pct = VALUES(return_pct),
                    win_rate = VALUES(win_rate),
                    trades = VALUES(trades)
            """, (
                symbol, tf,
                data['indicator'],
                json.dumps(params),
                data['sharpe'],
                data['return'],
                data['win_rate'],
                data['trades']
            ))
            
            if data['is_composite']:
                composite_count += 1
            else:
                single_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"✅ 已保存! 單一策略: {single_count}, 組合策略: {composite_count}")
    
    # 統計
    indicator_usage = {}
    for symbol, timeframes in all_results.items():
        for tf, data in timeframes.items():
            ind = data['indicator']
            indicator_usage[ind] = indicator_usage.get(ind, 0) + 1
    
    print("\n📊 策略使用統計:")
    for ind, count in sorted(indicator_usage.items(), key=lambda x: -x[1]):
        is_comp = "🎯" if all_results.get(list(all_results.keys())[0], {}).get(tf, {}).get('is_composite') else "📊"
        print(f"  {ind}: {count}次")


if __name__ == '__main__':
    main()
