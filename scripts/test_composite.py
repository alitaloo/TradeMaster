#!/usr/bin/env python3
"""
多股票多週期回測 + 簡單組合策略
"""

import pandas as pd
import numpy as np
import mysql.connector
from datetime import datetime, timedelta
import json
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

STOCKS = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

TIMEFRAMES = ['5m', '1h', '1d']

# 單一指標
INDICATORS = {
    'RSI': {'period': 14, 'os': 30, 'ob': 70},
    'RSI_7': {'period': 7, 'os': 25, 'ob': 75},
    'MACD': {'fast': 12, 'slow': 26, 'sig': 9},
    'SMA_Cross': {'fast': 10, 'slow': 50},
    'EMA_Cross': {'fast': 12, 'slow': 26},
    'Bollinger': {'period': 20, 'std': 2},
    'Stochastic': {'k': 14, 'd': 3, 'os': 20, 'ob': 80},
    'CCI': {'period': 20, 'os': -100, 'ob': 100},
    'Williams_R': {'period': 14, 'os': -80, 'ob': -20},
}

# 簡單組合策略
COMPOSITES = {
    'RSI_MACD': lambda rsi, macd: 1 if (rsi < 30 and macd > 0) else (-1 if (rsi > 70 and macd < 0) else 0),
    'RSI_BB': lambda rsi, bb: 1 if (rsi < 30 and bb < -1) else (-1 if (rsi > 70 and bb > 1) else 0),
    'RSI_STOCH': lambda rsi, stoch: 1 if (rsi < 30 and stoch < 20) else (-1 if (rsi > 70 and stoch > 80) else 0),
    'MACD_SMA': lambda macd, sma: 1 if (macd > 0 and sma > 0) else (-1 if (macd < 0 and sma < 0) else 0),
}


def get_data(symbol, tf):
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    days = 30 if tf == '5m' else (400 if tf == '1h' else 365)
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT timestamp, open_price, high_price, low_price, close_price, volume
        FROM kline_cache WHERE symbol = %s AND interval_val = %s AND timestamp >= %s
        ORDER BY timestamp ASC
    """, (symbol, tf, cutoff))
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    df['ts'] = pd.to_datetime(df['ts'])
    return df


def calc_indicators(df):
    c = df['c']
    h, l = df['h'], df['l']
    
    # RSI
    d = c.diff()
    g, lss = d.where(d > 0, 0).rolling(14).mean(), (-d.where(d < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + g / lss.replace(0, 0.001)))
    
    # MACD
    ema12, ema26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    
    # SMA
    sma10, sma50 = c.rolling(10).mean(), c.rolling(50).mean()
    
    # Bollinger
    sma20, std20 = c.rolling(20).mean(), c.rolling(20).std()
    bb = (c - sma20) / std20
    
    # Stochastic
    lo, hi = l.rolling(14).min(), h.rolling(14).max()
    k = 100 * (c - lo) / (hi - lo).replace(0, 0.001)
    
    return {
        'rsi': rsi.iloc[-1] if len(rsi) > 0 else 50,
        'macd': (macd - signal).iloc[-1] if len(macd) > 0 else 0,
        'sma': (sma10 - sma50).iloc[-1] if len(sma10) > 0 else 0,
        'bb': bb.iloc[-1] if len(bb) > 0 else 0,
        'stoch': k.iloc[-1] if len(k) > 0 else 50
    }


def backtest(df, ind):
    if df is None or len(df) < 30:
        return None
    
    trades, capital, pos = [], 100000, 0
    for i in range(20, len(df)):
        signal = 0
        if ind['rsi'] < 30 and ind['macd'] > 0:
            signal = 1
        elif ind['rsi'] > 70 and ind['macd'] < 0:
            signal = -1
        
        if signal == 1 and pos == 0:
            pos = 1
            entry = df['c'].iloc[i]
        elif signal == -1 and pos == 1:
            pnl = (df['c'].iloc[i] - entry) / entry
            trades.append(pnl)
            pos = 0
    
    if len(trades) < 2:
        return None
    
    ret = sum(trades)
    win = len([t for t in trades if t > 0]) / len(trades)
    sharpe = (np.mean(trades) / np.std(trades) * np.sqrt(252)) if np.std(trades) > 0 else 0
    
    return {'return': ret, 'win': win, 'sharpe': sharpe, 'trades': len(trades)}


def main():
    print("=" * 60)
    print("多股票多週期回測 (含組合策略)")
    print("=" * 60)
    
    results = {}
    
    for sym in STOCKS:
        results[sym] = {}
        print(f"\n📊 {sym}")
        
        for tf in TIMEFRAMES:
            df = get_data(sym, tf)
            if df is None or len(df) < 30:
                print(f"  {tf}: 數據不足")
                continue
            
            ind = calc_indicators(df)
            result = backtest(df, ind)
            
            if result:
                results[sym][tf] = {
                    'indicator': 'RSI_MACD',  # 簡單組合
                    'sharpe': result['sharpe'],
                    'return': result['return'],
                    'win': result['win'],
                    'trades': result['trades']
                }
                print(f"  {tf}: RSI_MACD Sharpe={result['sharpe']:.2f}")
    
    # 保存
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    for sym, tfs in results.items():
        for tf, data in tfs.items():
            cursor.execute("""
                INSERT INTO stock_strategies (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE indicator=VALUES(indicator), sharpe=VALUES(sharpe), return_pct=VALUES(return_pct), win_rate=VALUES(win_rate), trades=VALUES(trades)
            """, (sym, tf, data['indicator'], json.dumps({'composite': True}), data['sharpe'], data['return'], data['win'], data['trades']))
    
    conn.commit()
    conn.close()
    print("\n✅ 完成!")


if __name__ == '__main__':
    main()
