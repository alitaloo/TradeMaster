#!/usr/bin/env python3
"""
多股票多週期回測 - 單一指標 + 組合策略
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

TIMEFRAMES = ['5m', '1h', '1d']


def get_stocks_from_db():
    """從數據庫讀取啟用的股票清單"""
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol FROM stocks WHERE enabled=1 ORDER BY symbol")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_data(symbol, tf):
    """獲取K線數據"""
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
    df = pd.DataFrame(rows, columns=['ts', 'open', 'high', 'low', 'close', 'volume'])
    df['ts'] = pd.to_datetime(df['ts'])
    df.set_index('ts', inplace=True)
    return df


def calc_indicators(df):
    """計算所有指標，返回 DataFrame"""
    c = df['close']
    h, l = df['high'], df['low']
    
    ind = pd.DataFrame(index=df.index)
    
    # RSI 14
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, 0.0001)
    ind['RSI'] = 100 - (100 / (1 + rs))
    
    # RSI 7
    gain7 = delta.where(delta > 0, 0).rolling(7).mean()
    loss7 = (-delta.where(delta < 0, 0)).rolling(7).mean()
    rs7 = gain7 / loss7.replace(0, 0.0001)
    ind['RSI_7'] = 100 - (100 / (1 + rs7))
    
    # MACD
    ema12 = c.ewm(span=12).mean()
    ema26 = c.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    ind['MACD'] = macd - signal
    
    # SMA Cross
    ind['SMA_Cross'] = c.rolling(10).mean() - c.rolling(50).mean()
    
    # EMA Cross
    ind['EMA_Cross'] = c.ewm(span=12).mean() - c.ewm(span=26).mean()
    
    # Bollinger
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    ind['Bollinger'] = (c - sma20) / std20.replace(0, 0.0001)
    
    # Stochastic
    lo14 = l.rolling(14).min()
    hi14 = h.rolling(14).max()
    ind['Stochastic'] = 100 * (c - lo14) / (hi14 - lo14).replace(0, 0.0001)
    
    # CCI
    tp = (h + l + c) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    ind['CCI'] = (tp - sma_tp) / (0.015 * mad.replace(0, 0.0001))
    
    # Williams %R
    ind['Williams_R'] = -100 * (h.rolling(14).max() - c) / (h.rolling(14).max() - l.rolling(14).min()).replace(0, 0.0001)
    
    return ind


def get_signal(name, val):
    """單一指標信號"""
    if pd.isna(val):
        return 0
    
    if name == 'RSI':
        if val < 30: return 1
        elif val > 70: return -1
    elif name == 'RSI_7':
        if val < 25: return 1
        elif val > 75: return -1
    elif name == 'MACD':
        if val > 0: return 1
        elif val < 0: return -1
    elif name in ['SMA_Cross', 'EMA_Cross']:
        if val > 0: return 1
        elif val < 0: return -1
    elif name == 'Bollinger':
        if val < -1: return 1
        elif val > 1: return -1
    elif name == 'Stochastic':
        if val < 20: return 1
        elif val > 80: return -1
    elif name == 'CCI':
        if val < -100: return 1
        elif val > 100: return -1
    elif name == 'Williams_R':
        if val < -80: return 1
        elif val > -20: return -1
    return 0


def get_composite_signal(name, ind_row):
    """組合策略信號"""
    if name == 'RSI+MACD':
        s1 = get_signal('RSI', ind_row.get('RSI', 50))
        s2 = get_signal('MACD', ind_row.get('MACD', 0))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'RSI+BB':
        s1 = get_signal('RSI', ind_row.get('RSI', 50))
        s2 = get_signal('Bollinger', ind_row.get('Bollinger', 0))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'RSI+STOCH':
        s1 = get_signal('RSI', ind_row.get('RSI', 50))
        s2 = get_signal('Stochastic', ind_row.get('Stochastic', 50))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'MACD+SMA':
        s1 = get_signal('MACD', ind_row.get('MACD', 0))
        s2 = get_signal('SMA_Cross', ind_row.get('SMA_Cross', 0))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'MACD+EMA':
        s1 = get_signal('MACD', ind_row.get('MACD', 0))
        s2 = get_signal('EMA_Cross', ind_row.get('EMA_Cross', 0))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'BB+STOCH':
        s1 = get_signal('Bollinger', ind_row.get('Bollinger', 0))
        s2 = get_signal('Stochastic', ind_row.get('Stochastic', 50))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'CCI+WR':
        s1 = get_signal('CCI', ind_row.get('CCI', 0))
        s2 = get_signal('Williams_R', ind_row.get('Williams_R', -50))
        if s1 == s2 and s1 != 0:
            return s1
    elif name == 'RSI+MACD+BB':
        s1 = get_signal('RSI', ind_row.get('RSI', 50))
        s2 = get_signal('MACD', ind_row.get('MACD', 0))
        s3 = get_signal('Bollinger', ind_row.get('Bollinger', 0))
        if s1 == s2 == s3 and s1 != 0:
            return s1
    return 0


def backtest(df, ind_df, strategy_name, is_composite=False):
    """回測單一策略"""
    if df is None or len(df) < 50:
        return None
    
    trades = []
    position = 0
    entry_price = 0
    
    for i in range(50, len(df)):
        row = ind_df.iloc[i].to_dict()
        
        if is_composite:
            signal = get_composite_signal(strategy_name, row)
        else:
            signal = get_signal(strategy_name, row.get(strategy_name, 0))
        
        price = df['close'].iloc[i]
        
        if signal == 1 and position == 0:
            position = 1
            entry_price = price
        elif signal == -1 and position == 1:
            pnl = (price - entry_price) / entry_price
            trades.append(pnl)
            position = 0
    
    if len(trades) < 3:
        return None
    
    total_return = sum(trades)
    win_rate = len([t for t in trades if t > 0]) / len(trades)
    std = np.std(trades)
    sharpe = (np.mean(trades) / std * np.sqrt(252)) if std > 0 else 0
    
    return {
        'sharpe': sharpe,
        'return': total_return,
        'win_rate': win_rate,
        'trades': len(trades)
    }


def main():
    print("=" * 70)
    print("多股票多週期回測 - 單一指標 + 組合策略")
    print("=" * 70)
    
    # 所有策略
    single_strategies = ['RSI', 'RSI_7', 'MACD', 'SMA_Cross', 'EMA_Cross', 
                         'Bollinger', 'Stochastic', 'CCI', 'Williams_R']
    composite_strategies = ['RSI+MACD', 'RSI+BB', 'RSI+STOCH', 'MACD+SMA', 
                            'MACD+EMA', 'BB+STOCH', 'CCI+WR', 'RSI+MACD+BB']
    
    # 從數據庫讀取股票清單
    STOCKS = get_stocks_from_db()
    print(f"📋 從數據庫讀取 {len(STOCKS)} 支股票")
    
    all_results = {}
    
    for sym in STOCKS:
        all_results[sym] = {}
        print(f"\n📊 {sym}")
        
        for tf in TIMEFRAMES:
            df = get_data(sym, tf)
            if df is None or len(df) < 50:
                print(f"  {tf}: 數據不足")
                continue
            
            ind_df = calc_indicators(df)
            
            best_sharpe = float('-inf')
            best_strategy = None
            best_result = None
            best_is_composite = False
            
            # 測試單一指標
            for strat in single_strategies:
                result = backtest(df, ind_df, strat, is_composite=False)
                if result and result['sharpe'] > best_sharpe:
                    best_sharpe = result['sharpe']
                    best_strategy = strat
                    best_result = result
                    best_is_composite = False
            
            # 測試組合策略
            for strat in composite_strategies:
                result = backtest(df, ind_df, strat, is_composite=True)
                if result and result['sharpe'] > best_sharpe:
                    best_sharpe = result['sharpe']
                    best_strategy = strat
                    best_result = result
                    best_is_composite = True
            
            if best_strategy:
                tag = "🎯" if best_is_composite else "📈"
                all_results[sym][tf] = {
                    'indicator': best_strategy,
                    'is_composite': best_is_composite,
                    'sharpe': best_result['sharpe'],
                    'return': best_result['return'],
                    'win_rate': best_result['win_rate'],
                    'trades': best_result['trades']
                }
                print(f"  {tf}: {tag} {best_strategy} (Sharpe: {best_sharpe:.2f}, Win: {best_result['win_rate']*100:.1f}%, Trades: {best_result['trades']})")
            else:
                print(f"  {tf}: ❌ 無有效結果")
    
    # 保存到 MySQL
    print("\n" + "=" * 70)
    print("💾 保存到 MySQL...")
    
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    single_count = 0
    composite_count = 0
    
    for sym, tfs in all_results.items():
        for tf, data in tfs.items():
            params = json.dumps({'composite': data['is_composite']})
            cursor.execute("""
                INSERT INTO stock_strategies (symbol, timeframe, indicator, params, sharpe, return_pct, win_rate, trades)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    indicator=VALUES(indicator), params=VALUES(params),
                    sharpe=VALUES(sharpe), return_pct=VALUES(return_pct), 
                    win_rate=VALUES(win_rate), trades=VALUES(trades)
            """, (sym, tf, data['indicator'], params, 
                  data['sharpe'], data['return'], data['win_rate'], data['trades']))
            
            if data['is_composite']:
                composite_count += 1
            else:
                single_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"✅ 完成！單一策略: {single_count}, 組合策略: {composite_count}")
    
    # 統計
    print("\n📊 策略使用統計:")
    usage = {}
    for sym, tfs in all_results.items():
        for tf, data in tfs.items():
            name = data['indicator']
            usage[name] = usage.get(name, 0) + 1
    
    for name, cnt in sorted(usage.items(), key=lambda x: -x[1]):
        tag = "🎯" if '+' in name else "📈"
        print(f"  {tag} {name}: {cnt}次")


if __name__ == '__main__':
    main()
