#!/usr/bin/env python3
"""
TradeMaster v2 - RSI-2 激进策略
目標：Sharpe > 1.5, Return > 20%
"""
import urllib.request
import ssl
import pandas as pd
import io
import numpy as np

def download_stooq(symbol):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    url = f'https://stooq.com/q/d/l/?s={symbol}.us&d1=20200101&d2=20251231&i=d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, context=ssl_context, timeout=60) as response:
        df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
    df['Date'] = pd.to_datetime(df['Date'])
    return df.sort_values('Date').reset_index(drop=True)

def rsi2(data):
    """RSI-2 使用 2 日週期"""
    close = data['Close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=2).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=2).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs)).fillna(50)

def rsi(data, period=14):
    close = data['Close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs)).fillna(50)

def sma(data, period):
    return data['Close'].rolling(period).mean()

def roc(data, period=10):
    """ROC 動量"""
    return ((data['Close'] - data['Close'].shift(period)) / data['Close'].shift(period)) * 100

def run_rsi2_test(df, symbol, 
                  rsi2_oversold=10, rsi2_overbought=90,
                  confirm_rsi=50,
                  stop_loss=0.10, take_profit=0.15,
                  min_roc=0):
    """RSI-2 策略回測"""
    df = df.copy()
    df['RSI2'] = rsi2(df)
    df['RSI14'] = rsi(df, 14)
    df['SMA200'] = sma(df, 200)
    df['ROC10'] = roc(df, 10)
    
    position = None
    entry_price = None
    equity = [100000]
    
    for i in range(len(df)):
        rsi2_val = df['RSI2'].iloc[i]
        rsi14_val = df['RSI14'].iloc[i]
        price = df['Close'].iloc[i]
        sma200 = df['SMA200'].iloc[i]
        roc10 = df['ROC10'].iloc[i]
        
        # 確認趨勢：價格在 200 日均線上方
        trend_up = price > sma200
        
        # 進場：RSI2 超賣 + 趨勢向上 + 動量確認
        if position is None:
            if rsi2_val < rsi2_oversold and trend_up and roc10 > min_roc:
                position = {'entry': price}
        
        # 出場
        elif position:
            pnl = (price - position['entry']) / position['entry']
            # RSI2 過熱 / 止盈 / 止損 / RSI14 確認反彈
            if rsi2_val > rsi2_overbought or pnl >= take_profit or pnl <= -stop_loss or rsi14_val > confirm_rsi:
                equity.append(equity[-1] * (1 + pnl))
                position = None
            else:
                equity.append(equity[-1])
        else:
            equity.append(equity[-1])
    
    if len(equity) < 2:
        return None
    
    eq = pd.Series(equity)
    ret = (eq.iloc[-1]/eq.iloc[0]-1) * (252/len(df))
    vol = eq.pct_change().std() * np.sqrt(252)
    sharpe = ret / vol if vol > 0 else 0
    
    peak = eq.expanding().max()
    dd = abs(((eq - peak) / peak).min())
    
    trades = sum(1 for i in range(len(df)) if df['RSI2'].iloc[i] < rsi2_oversold and df['Close'].iloc[i] > df['SMA200'].iloc[i])
    
    return {
        'symbol': symbol,
        'sharpe': sharpe,
        'return': ret,
        'max_dd': dd,
        'trades': trades,
        'params': f"RSI2({rsi2_oversold}/{rsi2_overbought}) ROC>{min_roc} SL={stop_loss:.0%} TP={take_profit:.0%}"
    }

def main():
    print("="*70)
    print("🚀 RSI-2 激进策略回測")
    print("="*70)
    
    print("\n📥 下載數據...")
    data = {s: download_stooq(s) for s in ['AAPL', 'TSLA', 'SPY', 'NVDA', 'MSFT']}
    for s, df in data.items():
        print(f"  ✓ {s}: {len(df)} 天")
    
    results = []
    
    for symbol, df in data.items():
        print(f"\n📊 {symbol} 測試中...")
        
        for rsi2_os in [5, 10, 15, 20]:
            for rsi2_ob in [80, 85, 90]:
                for min_roc in [0, 5, 10]:
                    for sl in [0.08, 0.10, 0.12, 0.15]:
                        for tp in [0.12, 0.15, 0.20, 0.25]:
                            if sl >= tp: continue
                            
                            r = run_rsi2_test(df, symbol,
                                             rsi2_oversold=rsi2_os,
                                             rsi2_overbought=rsi2_ob,
                                             min_roc=min_roc,
                                             stop_loss=sl,
                                             take_profit=tp)
                            if r:
                                results.append(r)
    
    df = pd.DataFrame(results)
    qualified = df[(df['sharpe'] > 1.5) & (df['return'] > 0.20)].sort_values('sharpe', ascending=False)
    
    print("\n" + "="*70)
    print("📋 RSI-2 策略結果")
    print("="*70)
    print(f"\n總測試: {len(df)}")
    print(f"達標 (Sharpe > 1.5, Return > 20%): {len(qualified)}")
    
    print("\n🏆 TOP 15:")
    for i, (_, r) in enumerate(df.sort_values('sharpe', ascending=False).head(15).iterrows(), 1):
        status = '✅' if r['sharpe'] > 1.5 and r['return'] > 0.20 else '⚠️'
        print(f"{i}. {r['symbol']} {status}")
        print(f"   Sharpe:{r['sharpe']:.2f} Return:{r['return']:.2%} DD:{r['max_dd']:.2%} Trades:{r['trades']}")
        print(f"   {r['params']}")
    
    df.to_csv('/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/rsi2_results.csv', index=False)
    print(f"\n💾 結果已保存: rsi2_results.csv")

if __name__ == "__main__":
    main()
