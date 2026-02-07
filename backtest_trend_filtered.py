#!/usr/bin/env python3
"""
TradeMaster v2 - 結合趨勢過濾的高夏普策略
目標：Sharpe > 1.5, Return > 20%
"""
import urllib.request
import ssl
import pandas as pd
import io
import numpy as np
from typing import Dict

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

def calc_indicators(df, rsi_period=14):
    close = df['Close']
    
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    # SMA 趨勢
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    
    # ATR
    high = df['High']
    low = df['Low']
    atr = ((high - low).rolling(14).mean())
    
    return {
        'rsi': rsi.fillna(50),
        'sma50': sma50,
        'sma200': sma200,
        'atr': atr.fillna(atr.mean()),
        'close': close
    }

def run_trend_filtered_backtest(df, symbol,
                                 rsi_period=14, rsi_oversold=35, rsi_overbought=70,
                                 sma_fast=50, sma_slow=200,
                                 stop_loss=0.08, take_profit=0.12,
                                 atr_multiplier=1.5):
    """趨勢過濾回測"""
    ind = calc_indicators(df, rsi_period)
    
    position = None
    entry_price = None
    atr_sl = None
    equity = [100000]
    
    for i in range(len(df)):
        close = ind['close'].iloc[i]
        rsi = ind['rsi'].iloc[i]
        sma50 = ind['sma50'].iloc[i]
        sma200 = ind['sma200'].iloc[i]
        atr = ind['atr'].iloc[i]
        
        # 趨勢判斷
        trend_up = sma50 > sma200
        
        # 進場：RSI 超賣 + 趨勢向上
        if position is None:
            if rsi < rsi_oversold and trend_up:
                position = {
                    'entry': close,
                    'atr': atr,
                    'stop': close - atr_multiplier * atr
                }
        
        # 出場
        elif position:
            pnl_pct = (close - position['entry']) / position['entry']
            atr_stop = position['stop']
            
            # ATR 止損 / RSI 止盈 / RSI 止損
            if close <= atr_stop or pnl_pct >= take_profit or rsi > rsi_overbought or pnl_pct <= -stop_loss:
                equity.append(equity[-1] * (1 + pnl_pct))
                position = None
            else:
                equity.append(equity[-1])
                # 更新 ATR 止損
                position['stop'] = max(position['stop'], close - atr_multiplier * atr)
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
    
    return {
        'symbol': symbol,
        'sharpe': sharpe,
        'return': ret,
        'max_dd': dd,
        'params': f"RSI({rsi_period}/{rsi_oversold}/{rsi_overbought}) SMA({sma_fast}/{sma_slow}) SL={stop_loss:.0%} TP={take_profit:.0%}"
    }

def main():
    print("="*70)
    print("🚀 趨勢過濾策略回測")
    print("="*70)
    
    # 下載數據
    print("\n📥 下載數據...")
    data = {s: download_stooq(s) for s in ['AAPL', 'TSLA', 'SPY']}
    for s, df in data.items():
        print(f"  ✓ {s}: {len(df)} 天")
    
    results = []
    
    for symbol, df in data.items():
        print(f"\n📊 {symbol} 測試中...")
        
        for rsi_period in [7, 10, 14]:
            for rsi_os in [25, 30, 35, 40]:
                for rsi_ob in [65, 70, 75]:
                    for sl in [0.05, 0.08, 0.10]:
                        for tp in [0.08, 0.10, 0.12, 0.15]:
                            if sl >= tp: continue
                            
                            r = run_trend_filtered_backtest(
                                df, symbol,
                                rsi_period=rsi_period,
                                rsi_oversold=rsi_os,
                                rsi_overbought=rsi_ob,
                                stop_loss=sl,
                                take_profit=tp
                            )
                            if r:
                                results.append(r)
    
    df = pd.DataFrame(results)
    qualified = df[(df['sharpe'] > 1.5) & (df['return'] > 0.20)].sort_values('sharpe', ascending=False)
    
    print("\n" + "="*70)
    print("📋 結果")
    print("="*70)
    print(f"\n總測試: {len(df)}")
    print(f"達標 (Sharpe > 1.5, Return > 20%): {len(qualified)}")
    
    print("\n🏆 TOP 10:")
    for i, (_, r) in enumerate(df.sort_values('sharpe', ascending=False).head(10).iterrows(), 1):
        status = '✅' if r['sharpe'] > 1.5 and r['return'] > 0.20 else '⚠️'
        print(f"{i}. {r['symbol']} {status}")
        print(f"   Sharpe:{r['sharpe']:.2f} Return:{r['return']:.2%} DD:{r['max_dd']:.2%}")
        print(f"   {r['params']}")
    
    df.to_csv('/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/trend_filtered_results.csv', index=False)
    print(f"\n💾 結果已保存")

if __name__ == "__main__":
    main()
