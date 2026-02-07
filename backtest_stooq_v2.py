#!/usr/bin/env python3
"""
TradeMaster v2 - 真實數據回測 v2
重點測試高報酬參數組合
"""
import urllib.request
import ssl
import pandas as pd
import io
import numpy as np
from datetime import datetime
from typing import Dict
import logging

logger = logging.getLogger(__name__)


def download_stooq(symbol: str, start_date: str = "20200101", end_date: str = "20251231") -> pd.DataFrame:
    """從 Stooq 下載歷史數據"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    url = f'https://stooq.com/q/d/l/?s={symbol}.us&d1={start_date}&d2={end_date}&i=d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, context=ssl_context, timeout=60) as response:
        df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
    
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').reset_index(drop=True)
    
    return df


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """計算 RSI"""
    close = data['Close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def run_backtest_v2(data: pd.DataFrame, symbol: str, 
                    rsi_period: int = 14, 
                    oversold: int = 35, 
                    overbought: int = 70,
                    stop_loss: float = 0.10,
                    take_profit: float = 0.10,
                    trailing_stop: float = 0.0) -> dict:
    """改進的回測"""
    df = data.copy()
    df['RSI'] = calculate_rsi(df, rsi_period)
    
    position = None
    entry_price = None
    equity = [100000]
    
    for i in range(len(df)):
        rsi = df['RSI'].iloc[i]
        price = df['Close'].iloc[i]
        
        # 進場邏輯
        if position is None:
            if rsi < oversold:
                position = {"shares": 100000 / price, "entry": price}
        
        # 出場邏輯
        elif position:
            pnl = (price - position["entry"]) / position["entry"]
            
            # 止盈或止損
            if pnl >= take_profit or pnl <= -stop_loss:
                equity.append(equity[-1] * (1 + pnl))
                position = None
            # RSI 過熱出場
            elif rsi > overbought:
                equity.append(equity[-1] * (1 + pnl))
                position = None
            else:
                equity.append(equity[-1])
        else:
            equity.append(equity[-1])
    
    # 計算指標
    equity_series = pd.Series(equity)
    returns = equity_series.pct_change().dropna()
    
    total_return = (equity[-1] / equity[0]) - 1
    annual_return = total_return * (252 / len(df))
    volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0
    sharpe = annual_return / volatility if volatility > 0 else 0
    
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    max_drawdown = abs(drawdown.min())
    
    return {
        'symbol': symbol,
        'sharpe': sharpe,
        'return': annual_return,
        'max_dd': max_drawdown,
        'total_trades': sum(1 for i in range(len(df)) if df['RSI'].iloc[i] < oversold),
        'final_equity': equity[-1],
        'params': f"RSI({rsi_period}/{oversold}/{overbought}) SL={stop_loss:.0%} TP={take_profit:.0%}"
    }


def main():
    print("="*70)
    print("🚀 TradeMaster v2 - 真實數據回測 v2 (高報酬參數)")
    print("="*70)
    
    # 下載數據
    print("\n📥 下載數據...")
    data = {}
    for symbol in ['AAPL', 'TSLA', 'SPY']:
        data[symbol] = download_stooq(symbol)
        print(f"  ✓ {symbol}: {len(data[symbol])} 天")
    
    results = []
    
    # 擴大參數範圍測試
    for symbol, df in data.items():
        print(f"\n📊 {symbol} 測試中...")
        
        # RSI 參數
        for rsi_period in [7, 10, 14]:
            for oversold in [25, 30, 35, 40]:
                for overbought in [65, 70, 75, 80]:
                    # 止損止盈
                    for sl in [0.05, 0.08, 0.10, 0.12, 0.15]:
                        for tp in [0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30]:
                            if sl >= tp:  # 止損必須小於止盈
                                continue
                            
                            r = run_backtest_v2(df, symbol, rsi_period, oversold, overbought, sl, tp)
                            results.append(r)
    
    # 排序
    qualified = [r for r in results if r['sharpe'] > 1.5 and r['return'] > 0.20]
    qualified.sort(key=lambda x: x['sharpe'], reverse=True)
    
    # 顯示結果
    print("\n" + "="*70)
    print("📋 真實數據回測結果")
    print("="*70)
    
    print(f"\n✅ 達標策略 (Sharpe > 1.5, Return > 20%): {len(qualified)} 個")
    
    for i, r in enumerate(qualified[:15], 1):
        print(f"\n{i}. {r['symbol']}")
        print(f"   Sharpe: {r['sharpe']:.2f} | Return: {r['return']:.2%} | MaxDD: {r['max_dd']:.2%}")
        print(f"   {r['params']}")
    
    # 保存
    df_results = pd.DataFrame(results)
    df_results.to_csv('/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/stooq_v2_results.csv', index=False)
    print(f"\n💾 完整結果: stooq_v2_results.csv")
    
    return qualified


if __name__ == "__main__":
    main()
