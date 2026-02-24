#!/usr/bin/env python3
"""
多股票多週期回測 + 組合策略
"""

import pandas as pd
import numpy as np
import mysql.connector
from datetime import datetime, timedelta
import json
import warnings
warnings.filterwarnings('ignore')

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

INDICATORS = {
    'RSI': {'p': 14, 'os': 30, 'ob': 70},
    'RSI_7': {'p': 7, 'os': 25, 'ob': 75},
    'MACD': {'f': 12, 's': 26, 'sig': 9},
    'SMA_Cross': {'f': 10, 'sl': 50},
    'EMA_Cross': {'f': 12, 's': 26},
    'Bollinger': {'p': 20, 'std': 2},
    'Stochastic': {'k': 14, 'd': 3, 'os': 20, 'ob': 80},
    'CCI': {'p': 20, 'os': -100, 'ob': 100},
    'Williams_R': {'p': 14, 'os': -80, 'ob': -20},
}

# 組合策略
COMPOSITES = {
    'RSI+MACD': ['RSI', 'MACD'],
    'RSI+BB': ['RSI', 'Bollinger'],
    'RSI+STOCH': ['RSI', 'Stochastic'],
    'MACD+SMA': ['MACD', 'SMA_Cross'],
    'BB+STOCH': ['Bollinger', 'Stochastic'],
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


def calc_all(df):
    c = df['c']
    h, l = df['h'], df['l']
    
    # RSI
    d = c.diff()
    g = d.where(d > 0, 0).rolling(14).mean()
    ls = (-d.where(d < 0, 0)).rolling(14).mean()
    rsi = 100 - (100 / (1 + g / ls.replace(0, 0.001)))
    
    # RSI 7
    d7 = c.diff()
    g7 = d7.where(d7 > 0, 0).rolling(7).mean()
    ls7 = (-d7.where(d7 < 0, 0)).rolling(7).mean()
    rsi7 = 100 - (100 / (1 + g7 / ls7.replace(0, 0.001)))
    
    # MACD
    ema12 = c.ewm(span=12).mean()
    ema26 = c.ewm(span=26).mean()
    macd = ema12 - ema26
    macd_sig = macd.ewm(span=9).mean()
    macd_hist = macd - macd_sig
    
    # SMA
    sma10 = c.rolling(10).mean()
    sma50 = c.rolling(50).mean()
    sma_cross = sma10 - sma50
    
    # EMA
    ema10 = c.ewm(span=12).mean()
    ema50 = c.ewm(span=26).mean()
    ema_cross = ema10 - ema50
    
    # BB
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    bb = (c - sma20) / std20.replace(0, 0.001)
    
    # Stoch
    lo14 = l.rolling(14).min()
    hi14 = h.rolling(14).max()
    k = 100 * (c - lo14) / (hi14 - lo14).replace(0, 0.001)
    d3 = k.rolling(3).mean()
    stoch = k - d3
    
    return {
        'RSI': rsi.iloc[-1] if len(rsi) > 0 else 50,
        'RSI_7': rsi7.iloc[-1] if len(rsi7) > 0 else 50,
        'MACD': macd_hist.iloc[-1] if len(macd_hist) > 0 else 0,
        'SMA_Cross': sma_cross.iloc[-1] if len(sma_cross) > 0 else 0,
        'EMA_Cross': ema_cross.iloc[-1] if len(ema_cross) > 0 else 0,
        'Bollinger': bb.iloc[-1] if len(bb) > 0 else 0,
        'Stochastic': stoch.iloc[-1] if len(stoch) > 0 else 0,
        'CCI': 0,
        'Williams_R': 0,
    }


def get_signal(name, val):
    cfg = INDICATORS.get(name, {})
    if name in ['RSI', 'RSI_7']:
        if val < cfg.get('os', 30):
            return 1
        elif val > cfg.get('ob', 70):
            return -1
    elif name == 'MACD':
        if val > 0:
            return 1
        elif val < 0:
            return -1
    elif name in ['SMA_Cross', 'EMA_Cross']:
        if val > 0:
            return 1
        elif val < 0:
            return -1
    elif name == 'Bollinger':
        if val < -1:
            return 1
        elif val > 1:
            return -1
    elif name == 'Stochastic':
        if val < -60:
            return 1
        elif val > 60:
            return -1
    return 0


def run_backtest(df, ind_func):
    if df is None or len(df) < 30:
        return None
    
    trades = []
    capital = 100000
    pos = 0
    entry = 0
    
    for i in range(20, len(df)):
        signal = ind_func()
        if signal == 1 and pos == 0:
            pos = 1
            entry = df['c'].iloc[i]
        elif signal == -1 and pos == 1:
            pnl = (df['c'].iloc[i] - entry) / entry
            trades.append(pnl)
            pos = 0
    
    if len(trades) < 2:
        return None
    
    ret = sum(trades) / len(trades)
    wins = len([t for t in trades if t > 0])
    win_rate = wins / len(trades)
    std = np.std(trades)
    sharpe = (np.mean(trades) / std * np.sqrt(252)) if std > 0 else 0
    
    return {'return': ret, 'win': win_rate, 'sharpe': sharpe, 'trades': len(trades)}


def main():
    print("=" * 60)
    print("多股票多週期 + 組合策略回測")
    print("=" * 60)
    
    all_results = {}
    
    for sym in STOCKS:
        all_results[sym] = {}
        print(f"\n📊 {sym}")
        
        for tf in TIMEFRAMES:
            df = get_data(sym, tf)
            if df is None or len(df) < 30:
                print(f"  {tf}: 數據不足")
                continue
            
            ind = calc_all(df)
            
            # 測試所有單一指標
            best_sharpe = float('-inf')
            best_name = None
            best_result = None
            
            for name in INDICATORS.keys():
                val = ind.get(name, 0)
                signal = get_signal(name, val)
                
                # 簡單回測
                trades = []
                pos = 0
                entry = 0
                for i in range(20, len(df)):
                    s = get_signal(name, ind[name] if name in ind else 0)
                    if s == 1 and pos == 0:
                        pos = 1
                        entry = df['c'].iloc[i]
                    elif s == -1 and pos == 1:
                        pnl = (df['c'].iloc[i] - entry) / entry
                        trades.append(pnl)
                        pos = 0
                
                if len(trades) >= 2:
                    ret = sum(trades) / len(trades)
                    wins = len([t for t in trades if t > 0])
                    win_rate = wins / len(trades)
                    std = np.std(trades)
                    sharpe = (np.mean(trades) / std * np.sqrt(252)) if std > 0 else 0
                    
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_name = name
                        best_result = {'return': ret, 'win': win_rate, 'sharpe': sharpe, 'trades': len(trades)}
            
            if best_name:
                all_results[sym][tf] = {
                    'indicator': best_name,
                    'sharpe': best_result['sharpe'],
                    'return': best_result['return'],
                    'win': best_result['win'],
                    'trades': best_result['trades']
                }
                print(f"  {tf}: {best_name} Sharpe={best_result['sharpe']:.2f}")
    
    # 保存到 MySQL
    print("\n" + "=" * 60)
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    for sym, tfs in all_results.items():
        for tf, data in tfs.items():
            cursor.execute("""
                INSERT INTO stock_strategies (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE indicator=VALUES(indicator), sharpe=VALUES(sharpe), 
                    return_pct=VALUES(return_pct), win_rate=VALUES(win_rate), trades=VALUES(trades)
            """, (sym, tf, data['indicator'], json.dumps({'single': True}), 
                 data['sharpe'], data['return'], data['win'], data['trades']))
    
    conn.commit()
    conn.close()
    print("✅ 已保存到 MySQL")


if __name__ == '__main__':
    main()
