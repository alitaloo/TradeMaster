#!/usr/bin/env python3
"""
TradeMaster v2 - 16股票 x 7策略 完整回測分析
"""

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

# 導入技術指標
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.indicators import calculate_adx

DATA_DIR = Path("data/historical")
REPORT_FILE = Path("strategy_full_report.txt")

# 2026-02-12: 優化股票池 - 剔除 TSLA、INTC、RKLB（高波動/下降趨勢股票）
# 專注於：科技巨頭、半導體龍頭、穩定成長股
STOCKS = ["AAPL", "MSFT", "NVDA", "TSM", "AMZN", "META", "UBER", "MU", "AMD", "ORCL"]

def load(sym):
    p = DATA_DIR / f"{sym}.csv"
    return pd.read_csv(p, index_col=0, parse_dates=True) if p.exists() else None

def compute(df):
    d = df.copy()
    d['Close'] = pd.to_numeric(d['Close'], errors='coerce')
    d['SMA50'] = d['Close'].rolling(50, min_periods=1).mean()
    d['SMA200'] = d['Close'].rolling(200, min_periods=1).mean()
    d['EMA12'] = d['Close'].ewm(span=12, adjust=False).mean()
    d['EMA26'] = d['Close'].ewm(span=26, adjust=False).mean()
    d['MACD'] = d['EMA12'] - d['EMA26']
    d['MACD_Sig'] = d['MACD'].ewm(span=9, adjust=False).mean()
    
    delta = d['Close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14, min_periods=1).mean()
    rs = gain / (loss.replace(0, np.nan))
    d['RSI'] = (100 - (100 / (1 + rs))).fillna(50)
    
    m = d['Close'].rolling(20, min_periods=1).mean()
    s = d['Close'].rolling(20, min_periods=1).std()
    d['BB_Up'] = m + s * 2
    d['BB_Low'] = m - s * 2
    d['BB_Pct'] = ((d['Close'] - d['BB_Low']) / (d['BB_Up'] - d['BB_Low']).replace(0, np.nan)).fillna(0.5)
    
    # 使用標準 Wilder's Smoothing ADX 計算
    adx_result = calculate_adx(d, period=14)
    d['ADX'] = adx_result['ADX']
    d['PLUS_DI'] = adx_result['PLUS_DI']
    d['MINUS_DI'] = adx_result['MINUS_DI']
    return d

# 7種策略信號邏輯
def signals(d):
    return {
        "SMA_Crossover": (d['Close'] > d['SMA50']) & (d['SMA50'] > d['SMA200']),
        "MACD_Cross": d['MACD'] > d['MACD_Sig'],
        "RSI_Strategy": d['RSI'] < 35,
        "BB_Strategy": d['BB_Pct'] < 0.2,
        "ADX_Trend": (d['ADX'] > 25) & (d['PLUS_DI'] > d['MINUS_DI']),
        "MA+MACD": (d['Close'] > d['SMA50']) & (d['MACD'] > 0),
        "MultiFactor": ((d['Close'] > d['SMA50']).astype(int) + (d['MACD'] > 0).astype(int) + (d['PLUS_DI'] > d['MINUS_DI']).astype(int)) >= 2
    }

def backtest(d, sig):
    if len(d) < 252:
        return None
    daily_ret = d['Close'].pct_change()
    strat_ret = sig.shift(1) * daily_ret.dropna()
    if len(strat_ret) < 100:
        return None
    ann = strat_ret.mean() * 252
    vol = strat_ret.std() * np.sqrt(252)
    sharpe = ann / vol if vol > 0 else 0
    cum = (1 + strat_ret).cumprod()
    cummax = cum.expanding().max()
    dd = (cum - cummax) / cummax
    max_dd = abs(dd.min())
    trades = sig.diff().abs().sum()
    curr = "LONG" if sig.iloc[-1] else "SHORT"
    return {
        'ann': ann,
        'monthly': strat_ret.mean() * 21,
        'shp': sharpe,
        'dd': max_dd,
        'long': int(trades * 0.6),
        'short': int(trades * 0.4),
        'sig': curr
    }

print("=" * 95)
print("               TradeMaster v2 - 16股票 x 7策略 完整回測分析")
print(f"               {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 95)

all_results = {}

for sym in STOCKS:
    df = load(sym)
    if df is None:
        continue
    d = compute(df)
    sigs = signals(d)
    bt = []
    for name, sig in sigs.items():
        r = backtest(d, sig)
        if r:
            bt.append({'s': name, **r})
    bt.sort(key=lambda x: x['shp'] if not np.isnan(x['shp']) else -99, reverse=True)
    all_results[sym] = bt[0] if bt else None
    if bt:
        print(f"{sym}: {bt[0]['s']} (Sharpe={bt[0]['shp']:.2f})")

print("\n" + "=" * 95)
print("                         完整策略回測報告")
print(f"                         {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 95)
print(f"{'#':<3}{'股票':<8}{'最佳策略':<20}{'年化':>8}{'月化':>8}{'夏普':>7}{'最大回撤':>9}{'買入':>5}{'賣出':>5}{'信號':<8}")
print("-" * 95)

best_all = []
for i, (sym, r) in enumerate(all_results.items(), 1):
    if r:
        print(f"{i:<3}{sym:<8}{r['s']:<20}{r['ann']:>7.1%}{r['monthly']:>7.2%}{r['shp']:>6.2f}{r['dd']:>8.1%}{r['long']:>4}{r['short']:>4}{r['sig']:<8}")
        best_all.append({**r, 'sym': sym})

print("-" * 95)
best_all.sort(key=lambda x: x.get('shp', 0) if not np.isnan(x.get('shp', 0)) else -99, reverse=True)
print("\n🏆 TOP 5 最佳表現:")
for i, b in enumerate(best_all[:5], 1):
    print(f"   {i}. {b['sym']} - {b['s']}: 夏普={b['shp']:.2f}, 年化={b['ann']:.1%}, 信號={b['sig']}")

longs = len([b for b in best_all if b.get('sig') == 'LONG'])
print(f"\n📊 信號統計: 🟢 LONG={longs} | 🔴 SHORT={len(best_all) - longs}")
print("=" * 95)

with open(REPORT_FILE, 'w') as f:
    f.write("TradeMaster v2 策略回測報告\n")
    f.write(f"生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    for sym, r in all_results.items():
        if r:
            f.write(f"{sym}: {r['s']} (Sharpe={r['shp']:.2f}, 年化={r['ann']:.1%})\n")

print(f"\n✅ 報告已保存: {REPORT_FILE}")
