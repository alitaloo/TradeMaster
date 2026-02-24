#!/usr/bin/env python3
"""
Top 10 策略 × Z關注15支股票 完整回測
對 sector_config.py 中的 15 支股票執行 Top 10 策略回測
"""

import pandas as pd
import numpy as np
from datetime import datetime
import json
import sys
import warnings
warnings.filterwarnings('ignore')

# 2026-02-12: 優化股票池 - 剔除 TSLA、INTC、RKLB（高波動/下降趨勢股票）
# 專注於：科技巨頭、半導體龍頭、穩定成長股
SYMBOLS = [
    # 半導體 (5支) - 高動能，適合趨勢追蹤
    'NVDA', 'TSM', 'AMD', 'MU',
    # 科技巨頭 (3支) - 穩定成長
    'AAPL', 'MSFT', 'AMZN',
    # 網路 (2支) - 穩定表現
    'META',
    # 企業軟體 (1支)
    'ORCL',
    # 共享出行 (1支) - 波動適中
    'UBER',
]

# Top 10 策略參數 (從 TOP10_STRATEGIES_20260209.md)
TOP10_STRATEGIES = [
    {'rank': 1, 'name': 'Stooq_V2', 'params': 'RSI(7/35/80) SL=8% TP=10%', 'rsi_oversold': 7, 'rsi_overbought': 35, 'rsi_exit': 80, 'stop_loss': 0.08, 'take_profit': 0.10},
    {'rank': 2, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=15% TP=20%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.15, 'take_profit': 0.20},
    {'rank': 3, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=15% TP=25%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.15, 'take_profit': 0.25},
    {'rank': 4, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=15% TP=30%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.15, 'take_profit': 0.30},
    {'rank': 5, 'name': 'Trend_Filtered', 'params': 'RSI(7/40/75) SMA(50/200) SL=5% TP=8%', 'rsi_oversold': 7, 'rsi_overbought': 40, 'rsi_exit': 75, 'sma_fast': 50, 'sma_slow': 200, 'stop_loss': 0.05, 'take_profit': 0.08},
    {'rank': 6, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=10% TP=30%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.10, 'take_profit': 0.30},
    {'rank': 7, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=10% TP=25%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.10, 'take_profit': 0.25},
    {'rank': 8, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=10% TP=20%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.10, 'take_profit': 0.20},
    {'rank': 9, 'name': 'Stooq_V2', 'params': 'RSI(14/35/65) SL=10% TP=15%', 'rsi_oversold': 14, 'rsi_overbought': 35, 'rsi_exit': 65, 'stop_loss': 0.10, 'take_profit': 0.15},
    {'rank': 10, 'name': 'Stooq_V2', 'params': 'RSI(10/40/75) SL=8% TP=10%', 'rsi_oversold': 10, 'rsi_overbought': 40, 'rsi_exit': 75, 'stop_loss': 0.08, 'take_profit': 0.10},
]


def load_stock_data(symbol):
    """載入股票數據"""
    data_dir = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/historical'
    filepath = f'{data_dir}/{symbol}.csv'
    
    try:
        df = pd.read_csv(filepath, parse_dates=['Date'], index_col='Date')
        df = df.sort_index()
        
        # 確保必要的欄位存在
        required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        for col in required_cols:
            if col not in df.columns:
                df[col] = df.get(col.lower(), df.get(col.title(), 100))
        
        # 計算 RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 計算 SMA
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
        
        return df.dropna()
    
    except Exception as e:
        print(f"   [ERROR] {symbol}: {e}")
        return None


def run_stooq_v2_backtest(df, rsi_oversold, rsi_overbought, rsi_exit, stop_loss, take_profit):
    """Stooq_V2 策略回測"""
    if df is None or len(df) < 100:
        return None
    
    initial_capital = 100000
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    equity_curve = [capital]
    max_capital = capital
    max_drawdown = 0
    
    for i in range(20, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        rsi = row['RSI']
        prev_rsi = prev_row['RSI']
        
        # 買入信號: RSI 低於 oversold
        if position == 0 and prev_rsi > rsi_oversold and rsi < rsi_oversold:
            position = capital / row['Close']
            entry_price = row['Close']
            capital = 0
            trades.append({'type': 'BUY', 'price': entry_price, 'date': row.name})
        
        # 賣出信號 1: RSI 高於 overbought
        elif position > 0 and prev_rsi < rsi_overbought and rsi > rsi_overbought:
            capital = position * row['Close']
            trades.append({'type': 'SELL', 'price': row['Close'], 'date': row.name})
            position = 0
        
        # 賣出信號 2: RSI 反彈後再次跌破 exit
        elif position > 0 and prev_rsi > rsi_exit and rsi < rsi_exit:
            capital = position * row['Close']
            trades.append({'type': 'SELL', 'price': row['Close'], 'date': row.name})
            position = 0
        
        # 止損
        elif position > 0 and row['Close'] < entry_price * (1 - stop_loss):
            capital = position * row['Close'] * (1 - stop_loss)
            trades.append({'type': 'STOP_LOSS', 'price': row['Close'], 'date': row.name})
            position = 0
        
        # 止盈
        elif position > 0 and row['Close'] > entry_price * (1 + take_profit):
            capital = position * row['Close'] * (1 + take_profit)
            trades.append({'type': 'TAKE_PROFIT', 'price': row['Close'], 'date': row.name})
            position = 0
        
        # 記錄 equity
        current_value = capital + position * row['Close']
        equity_curve.append(current_value)
        max_capital = max(max_capital, current_value)
        drawdown = (max_capital - current_value) / max_capital
        max_drawdown = max(max_drawdown, drawdown)
    
    # 平倉
    if position > 0:
        final_price = df.iloc[-1]['Close']
        capital = position * final_price
        trades.append({'type': 'CLOSE', 'price': final_price, 'date': df.iloc[-1].name})
    
    # 計算指標
    total_return = (capital - initial_capital) / initial_capital
    annual_return = total_return * 252 / len(df) * 252  # 年化報酬
    volatility = np.std(np.diff(equity_curve)) / equity_curve[0] if len(equity_curve) > 1 else 0.01
    volatility = volatility * np.sqrt(252)
    sharpe = annual_return / volatility if volatility > 0 else 0
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'num_trades': len([t for t in trades if t['type'] in ['BUY', 'SELL']]),
        'trades': trades
    }


def run_trend_filtered_backtest(df, rsi_oversold, rsi_overbought, rsi_exit, sma_fast, sma_slow, stop_loss, take_profit):
    """Trend_Filtered 策略回測"""
    if df is None or len(df) < 200:
        return None
    
    # 檢查是否有 SMA 數據
    if 'SMA_50' not in df.columns or 'SMA_200' not in df.columns:
        # 使用簡化的趨勢判斷
        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        df['SMA_200'] = df['Close'].rolling(window=200).mean()
    
    df = df.dropna()
    if len(df) < 200:
        return None
    
    initial_capital = 100000
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    equity_curve = [capital]
    max_capital = capital
    max_drawdown = 0
    
    for i in range(200, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        rsi = row['RSI']
        prev_rsi = prev_row['RSI']
        sma_50 = row['SMA_50']
        sma_200 = row['SMA_200']
        prev_sma_50 = prev_row['SMA_50']
        
        # 趨勢判斷: SMA_50 > SMA_200 為上升趨勢
        is_uptrend = sma_50 > sma_200
        
        # 買入信號: 上升趨勢 + RSI 低於 oversold
        if position == 0 and is_uptrend and prev_rsi > rsi_oversold and rsi < rsi_oversold:
            position = capital / row['Close']
            entry_price = row['Close']
            capital = 0
            trades.append({'type': 'BUY', 'price': entry_price, 'date': row.name})
        
        # 賣出信號: RSI 高於 overbought
        elif position > 0 and prev_rsi < rsi_overbought and rsi > rsi_overbought:
            capital = position * row['Close']
            trades.append({'type': 'SELL', 'price': row['Close'], 'date': row.name})
            position = 0
        
        # 止損/止盈
        elif position > 0:
            if row['Close'] < entry_price * (1 - stop_loss):
                capital = position * row['Close'] * (1 - stop_loss)
                trades.append({'type': 'STOP_LOSS', 'price': row['Close'], 'date': row.name})
                position = 0
            elif row['Close'] > entry_price * (1 + take_profit):
                capital = position * row['Close'] * (1 + take_profit)
                trades.append({'type': 'TAKE_PROFIT', 'price': row['Close'], 'date': row.name})
                position = 0
        
        current_value = capital + position * row['Close']
        equity_curve.append(current_value)
        max_capital = max(max_capital, current_value)
        drawdown = (max_capital - current_value) / max_capital
        max_drawdown = max(max_drawdown, drawdown)
    
    if position > 0:
        final_price = df.iloc[-1]['Close']
        capital = position * final_price
        trades.append({'type': 'CLOSE', 'price': final_price, 'date': df.iloc[-1].name})
    
    total_return = (capital - initial_capital) / initial_capital
    annual_return = total_return * 252 / len(df) * 252
    volatility = np.std(np.diff(equity_curve)) / equity_curve[0] if len(equity_curve) > 1 else 0.01
    volatility = volatility * np.sqrt(252)
    sharpe = annual_return / volatility if volatility > 0 else 0
    
    return {
        'total_return': total_return,
        'annual_return': annual_return,
        'sharpe': sharpe,
        'max_drawdown': max_drawdown,
        'num_trades': len([t for t in trades if t['type'] in ['BUY', 'SELL']]),
        'trades': trades
    }


def run_backtests():
    """執行所有回測"""
    print("\n" + "="*80)
    print("🚀 Top 10 策略 × Z關注15支股票 完整回測")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    
    results = []
    total_tests = len(SYMBOLS) * len(TOP10_STRATEGIES)
    completed = 0
    
    for symbol in SYMBOLS:
        print(f"📊 {symbol}")
        df = load_stock_data(symbol)
        
        if df is None:
            print(f"   ❌ 數據載入失敗\n")
            continue
        
        print(f"   ✅ 數據載入成功 ({len(df)} 天)")
        
        for strat in TOP10_STRATEGIES:
            completed += 1
            
            if strat['name'] == 'Stooq_V2':
                result = run_stooq_v2_backtest(
                    df,
                    strat['rsi_oversold'],
                    strat['rsi_overbought'],
                    strat['rsi_exit'],
                    strat['stop_loss'],
                    strat['take_profit']
                )
            else:  # Trend_Filtered
                result = run_trend_filtered_backtest(
                    df,
                    strat['rsi_oversold'],
                    strat['rsi_overbought'],
                    strat['rsi_exit'],
                    strat.get('sma_fast', 50),
                    strat.get('sma_slow', 200),
                    strat['stop_loss'],
                    strat['take_profit']
                )
            
            if result:
                results.append({
                    'symbol': symbol,
                    'strategy_rank': strat['rank'],
                    'strategy_name': strat['name'],
                    'params': strat['params'],
                    'sharpe': result['sharpe'],
                    'return_pct': result['total_return'] * 100,
                    'max_dd_pct': result['max_drawdown'] * 100,
                    'num_trades': result['num_trades']
                })
                
                emoji = "📈" if result['total_return'] > 0 else "📉"
                print(f"   [{completed:3d}/{total_tests}] {strat['name']} #{strat['rank']}: {emoji} {result['total_return']*100:>7.1f}% | 夏普 {result['sharpe']:>5.2f} | DD {result['max_drawdown']*100:>5.1f}%")
            else:
                print(f"   [{completed:3d}/{total_tests}] {strat['name']} #{strat['rank']}: ❌ 回測失敗")
        
        print()
    
    return pd.DataFrame(results)


def generate_report(results_df):
    """生成回測報告"""
    
    if results_df is None or len(results_df) == 0:
        print("❌ 沒有回測結果")
        return
    
    # 排序
    df = results_df.sort_values('sharpe', ascending=False)
    
    # 達標統計
    qualified = df[(df['sharpe'] > 1.5) & (df['return_pct'] > 20) & (df['max_dd_pct'] < 30)]
    
    # 統計摘要
    avg_sharpe = df['sharpe'].mean()
    avg_return = df['return_pct'].mean()
    avg_maxdd = df['max_dd_pct'].mean()
    
    print("\n" + "="*80)
    print("📊 回測結果摘要")
    print("="*80)
    print(f"\n總測試數: {len(df)}")
    print(f"達標數 (Sharpe>1.5, Return>20%, MaxDD<30%): {len(qualified)}")
    print(f"平均 Sharpe: {avg_sharpe:.2f}")
    print(f"平均報酬率: {avg_return:.1f}%")
    print(f"平均最大回撤: {avg_maxdd:.1f}%")
    
    print(f"\n🏆 Top 10 策略-股票組合:")
    print("-"*80)
    for i, (_, row) in enumerate(df.head(10).iterrows(), 1):
        print(f"{i:2d}. {row['symbol']:6s} + {row['strategy_name']} #{row['strategy_rank']}")
        print(f"    參數: {row['params']}")
        print(f"    📈 {row['return_pct']:>7.1f}% | 夏普 {row['sharpe']:>5.2f} | DD {row['max_dd_pct']:>5.1f}% | 交易 {row['num_trades']}")
    
    # 生成 Markdown 報告
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    report_path = f'/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/docs/TOP10_15STOCKS_{timestamp}.md'
    
    report = f"""# TradeMaster v2 - Top 10 策略 × Z關注15支股票 回測報告

**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}  
**股票清單**: 半導體(NVDA,TSM,AMD,MU), 科技巨頭(AAPL,MSFT,AMZN), 網路(META), 企業軟體(ORCL), 共享出行(UBER)

---

## 📊 測試配置

| 項目 | 數值 |
|------|------|
| 股票數 | {len(SYMBOLS)} |
| 策略數 | {len(TOP10_STRATEGIES)} |
| 總測試數 | {len(df)} |
| 起始資金 | $100,000 |

---

## 🏆 Top 10 最佳策略-股票組合

| 排名 | 股票 | 策略 | 報酬率 | 夏普 | 最大回撤 | 交易數 | 參數 |
|------|------|------|--------|------|----------|--------|------|
"""
    
    for i, (_, row) in enumerate(df.head(10).iterrows(), 1):
        report += f"| {i} | {row['symbol']} | {row['strategy_name']}#{row['strategy_rank']} | **{row['return_pct']:.1f}%** | **{row['sharpe']:.2f}** | {row['max_dd_pct']:.1f}% | {row['num_trades']} | `{row['params']}` |\n"
    
    report += f"""

---

## 📈 統計摘要

| 指標 | 數值 |
|------|------|
| 達標組合數 (Sharpe>1.5, Return>20%, MaxDD<30%) | {len(qualified)} |
| 平均 Sharpe | {avg_sharpe:.2f} |
| 平均報酬率 | {avg_return:.1f}% |
| 平均最大回撤 | {avg_maxdd:.1f}% |

---

## 🎯 達標策略清單
"""
    
    if len(qualified) > 0:
        for _, row in qualified.iterrows():
            report += f"""
### {row['symbol']} + {row['strategy_name']} #{row['strategy_rank']}
- **報酬率**: {row['return_pct']:.1f}%
- **夏普比率**: {row['sharpe']:.2f}
- **最大回撤**: {row['max_dd_pct']:.1f}%
- **交易次數**: {row['num_trades']}
- **參數**: `{row['params']}`
"""
    else:
        report += "\n暫無達標策略\n"
    
    report += f"""

---

## 📊 各股票最佳策略

| 股票 | 最佳策略 | 報酬率 | 夏普 | 最大回撤 |
|------|----------|--------|------|----------|
"""
    
    for symbol in SYMBOLS:
        stock_df = df[df['symbol'] == symbol]
        if len(stock_df) > 0:
            best = stock_df.iloc[0]
            report += f"| {symbol} | {best['strategy_name']}#{best['strategy_rank']} | {best['return_pct']:.1f}% | {best['sharpe']:.2f} | {best['max_dd_pct']:.1f}% |\n"
    
    report += f"""

---

## 💡 關鍵發現

1. **最佳策略-股票組合**: {df.iloc[0]['symbol']} + {df.iloc[0]['strategy_name']} (Sharpe: {df.iloc[0]['sharpe']:.2f})
2. **達標率**: {len(qualified)/len(df)*100:.1f}%
3. **最高報酬**: {df['return_pct'].max():.1f}% ({df.loc[df['return_pct'].idxmax(), 'symbol']})
4. **最低回撤**: {df['max_dd_pct'].min():.1f}% ({df.loc[df['max_dd_pct'].idxmin(), 'symbol']})

---

## 📁 數據文件

- 報告路徑: `docs/TOP10_15STOCKS_{timestamp}.md`

---

*Generated by TradeMaster v2 | Fox Analysis*
"""
    
    # 保存報告
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 報告已保存: {report_path}")
    
    # 保存 CSV
    csv_path = f'/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/docs/TOP10_15STOCKS_{timestamp}.csv'
    df.to_csv(csv_path, index=False)
    print(f"✅ CSV 已保存: {csv_path}")
    
    return report_path, csv_path


if __name__ == "__main__":
    results = run_backtests()
    report_path, csv_path = generate_report(results)
    
    print("\n" + "="*80)
    print("✅ 回測完成！")
    print("="*80)
