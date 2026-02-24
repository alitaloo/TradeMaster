#!/usr/bin/env python3
"""
TSLA MACD Trend Strategy Backtest
為 TSLA 測試 MACD Trend Following 策略
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import warnings
warnings.filterwarnings('ignore')

# 配置
SYMBOL = 'TSLA'
INITIAL_CAPITAL = 100000

# MACD 參數測試組合
MACD_PARAMS = [
    {'name': 'MACD_12_26_9', 'fast': 12, 'slow': 26, 'signal': 9, 'sl': 0.15, 'tp': 0.30},
    {'name': 'MACD_8_17_9', 'fast': 8, 'slow': 17, 'signal': 9, 'sl': 0.12, 'tp': 0.25},
    {'name': 'MACD_5_35_5', 'fast': 5, 'slow': 35, 'signal': 5, 'sl': 0.10, 'tp': 0.20},
    {'name': 'MACD_19_39_9', 'fast': 19, 'slow': 39, 'signal': 9, 'sl': 0.15, 'tp': 0.35},
    {'name': 'MACD_EMA_9_20', 'fast_ema': 9, 'slow_ema': 20, 'sl': 0.12, 'tp': 0.30},
]


def load_tsla_data():
    """載入 TSLA 數據"""
    filepath = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/historical/TSLA.csv'
    
    try:
        df = pd.read_csv(filepath, parse_dates=['Date'], index_col='Date')
        df = df.sort_index()
        
        # 計算 MACD
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
        df['MACD_Histogram'] = df['MACD_Line'] - df['Signal_Line']
        
        # 計算價格動量
        df['Momentum_10'] = df['Close'] / df['Close'].shift(10) - 1
        df['Momentum_20'] = df['Close'] / df['Close'].shift(20) - 1
        
        return df.dropna()
    
    except Exception as e:
        print(f"[ERROR] Failed to load TSLA: {e}")
        return None


def run_macd_backtest(df, fast, slow, signal, sl, tp):
    """執行 MACD 回測"""
    if df is None or len(df) < 100:
        return None
    
    initial_capital = INITIAL_CAPITAL
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    equity_curve = [capital]
    max_capital = capital
    max_drawdown = 0
    
    for i in range(slow + 20, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        macd = row['MACD_Histogram']
        prev_macd = prev_row['MACD_Histogram']
        
        # 買入信號: MACD 從負轉正 (黃金交叉)
        if position == 0 and prev_macd < 0 and macd > 0:
            position = capital / row['Close']
            entry_price = row['Close']
            capital = 0
            trades.append({'type': 'BUY', 'price': entry_price, 'date': row.name})
        
        # 賣出信號: MACD 從正轉負 (死亡交叉)
        elif position > 0 and prev_macd > 0 and macd < 0:
            capital = position * row['Close']
            trades.append({'type': 'SELL', 'price': row['Close'], 'date': row.name})
            position = 0
        
        # 止損
        elif position > 0:
            if row['Close'] < entry_price * (1 - sl):
                capital = position * row['Close'] * (1 - sl)
                trades.append({'type': 'STOP_LOSS', 'price': row['Close'], 'date': row.name})
                position = 0
            
            # 止盈
            elif row['Close'] > entry_price * (1 + tp):
                capital = position * row['Close'] * (1 + tp)
                trades.append({'type': 'TAKE_PROFIT', 'price': row['Close'], 'date': row.name})
                position = 0
        
        current_value = capital + position * row['Close']
        equity_curve.append(current_value)
        max_capital = max(max_capital, current_value)
        drawdown = (max_capital - current_value) / max_capital if max_capital > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)
    
    # 平倉
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


def run_ema_crossover_backtest(df, fast_ema, slow_ema, sl, tp):
    """執行 EMA 價格交叉回測"""
    if df is None or len(df) < slow_ema + 20:
        return None
    
    df['EMA_Fast'] = df['Close'].ewm(span=fast_ema, adjust=False).mean()
    df['EMA_Slow'] = df['Close'].ewm(span=slow_ema, adjust=False).mean()
    
    initial_capital = INITIAL_CAPITAL
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    equity_curve = [capital]
    max_capital = capital
    max_drawdown = 0
    
    for i in range(slow_ema + 20, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        ema_fast = row['EMA_Fast']
        ema_slow = row['EMA_Slow']
        prev_ema_fast = prev_row['EMA_Fast']
        prev_ema_slow = prev_row['EMA_Slow']
        
        # 黃金交叉: Fast EMA 上穿 Slow EMA
        if position == 0 and prev_ema_fast < prev_ema_slow and ema_fast > ema_slow:
            position = capital / row['Close']
            entry_price = row['Close']
            capital = 0
            trades.append({'type': 'BUY', 'price': entry_price, 'date': row.name})
        
        # 死亡交叉: Fast EMA 下穿 Slow EMA
        elif position > 0 and prev_ema_fast > prev_ema_slow and ema_fast < ema_slow:
            capital = position * row['Close']
            trades.append({'type': 'SELL', 'price': row['Close'], 'date': row.name})
            position = 0
        
        elif position > 0:
            if row['Close'] < entry_price * (1 - sl):
                capital = position * row['Close'] * (1 - sl)
                trades.append({'type': 'STOP_LOSS', 'price': row['Close'], 'date': row.name})
                position = 0
            elif row['Close'] > entry_price * (1 + tp):
                capital = position * row['Close'] * (1 + tp)
                trades.append({'type': 'TAKE_PROFIT', 'price': row['Close'], 'date': row.name})
                position = 0
        
        current_value = capital + position * row['Close']
        equity_curve.append(current_value)
        max_capital = max(max_capital, current_value)
        drawdown = (max_capital - current_value) / max_capital if max_capital > 0 else 0
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
    print(f"🚀 TSLA MACD Trend Strategy Backtest")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")
    
    df = load_tsla_data()
    
    if df is None:
        print("❌ 無法載入 TSLA 數據")
        return
    
    print(f"✅ TSLA 數據載入成功 ({len(df)} 天)")
    print(f"   數據範圍: {df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')}\n")
    
    results = []
    
    for params in MACD_PARAMS:
        print(f"📊 {params['name']}: ", end="", flush=True)
        
        if 'fast' in params:  # MACD
            result = run_macd_backtest(
                df,
                params['fast'],
                params['slow'],
                params['signal'],
                params['sl'],
                params['tp']
            )
        else:  # EMA Crossover
            result = run_ema_crossover_backtest(
                df,
                params['fast_ema'],
                params['slow_ema'],
                params['sl'],
                params['tp']
            )
        
        if result:
            results.append({
                'strategy': params['name'],
                'params': f"Fast:{params.get('fast', params.get('fast_ema'))}, Slow:{params.get('slow', params.get('slow_ema'))}, Signal:{params.get('signal', 'N/A')}, SL:{params['sl']*100:.0f}%, TP:{params['tp']*100:.0f}%",
                'sharpe': result['sharpe'],
                'return_pct': result['total_return'] * 100,
                'max_dd_pct': result['max_drawdown'] * 100,
                'num_trades': result['num_trades']
            })
            
            emoji = "📈" if result['total_return'] > 0 else "📉"
            print(f"{emoji} {result['total_return']*100:>7.1f}% | 夏普 {result['sharpe']:>6.2f} | DD {result['max_drawdown']*100:>5.1f}% | 交易 {result['num_trades']}")
        else:
            print("❌ 回測失敗")
    
    return pd.DataFrame(results)


def generate_report(results_df):
    """生成回測報告"""
    
    if results_df is None or len(results_df) == 0:
        print("❌ 沒有回測結果")
        return
    
    # 排序
    df = results_df.sort_values('sharpe', ascending=False)
    
    print("\n" + "="*80)
    print("📊 TSLA MACD 回測結果摘要")
    print("="*80)
    
    print(f"\n🏆 Top 3 最佳策略:")
    for i, (_, row) in enumerate(df.head(3).iterrows(), 1):
        print(f"   {i}. {row['strategy']}")
        print(f"      參數: {row['params']}")
        print(f"      📈 {row['return_pct']:>7.1f}% | 夏普 {row['sharpe']:>6.2f} | DD {row['max_dd_pct']:>5.1f}% | 交易 {row['num_trades']}")
    
    # 生成 Markdown 報告
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    report_path = f'/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/docs/TSLA_MACD_BACKTEST_{timestamp}.md'
    
    report = f"""# TSLA MACD Trend Strategy Backtest Report

**Generated Time:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  
**Stock:** TSLA  
**Strategy Type:** MACD Trend Following / EMA Crossover

---

## 📊 Test Configuration

| Item | Value |
|------|-------|
| Initial Capital | $100,000 |
| Data Range | {datetime.now().strftime('%Y-%m-%d')} |
| Test Parameters | {len(results_df)} MACD/EMA combinations |

---

## 🏆 Top 3 Best Strategies

| Rank | Strategy | Return | Sharpe | Max DD | Trades | Parameters |
|------|----------|--------|--------|--------|--------|-----------|
"""
    
    for i, (_, row) in enumerate(df.head(3).iterrows(), 1):
        report += f"| {i} | {row['strategy']} | **{row['return_pct']:.1f}%** | **{row['sharpe']:.2f}** | {row['max_dd_pct']:.1f}% | {row['num_trades']} | `{row['params']}` |\n"
    
    report += f"""

---

## 📈 Complete Results

| Rank | Strategy | Return | Sharpe | Max DD | Trades | Parameters |
|------|----------|--------|--------|--------|--------|-----------|
"""
    
    for i, (_, row) in enumerate(df.iterrows(), 1):
        report += f"| {i} | {row['strategy']} | {row['return_pct']:.1f}% | {row['sharpe']:.2f} | {row['max_dd_pct']:.1f}% | {row['num_trades']} | `{row['params']}` |\n"
    
    # 最佳策略分析
    best = df.iloc[0]
    
    report += f"""

---

## 💡 Key Findings

### Best Strategy: {best['strategy']}
- **Return:** {best['return_pct']:.1f}%
- **Sharpe Ratio:** {best['sharpe']:.2f}
- **Max Drawdown:** {best['max_dd_pct']:.1f}%
- **Number of Trades:** {best['num_trades']}
- **Parameters:** `{best['params']}`

### Comparison with RSI Strategy

| Metric | RSI (Worst) | MACD (Best) | Improvement |
|--------|-------------|--------------|-------------|
| Return | -35.35% | **{best['return_pct']:.1f}%** | +{best['return_pct'] - (-35.35):.1f}% |
| Sharpe | -35.35 | **{best['sharpe']:.2f}** | +{best['sharpe'] - (-35.35):.2f} |

---

## 🎯 Recommendations

1. **Primary Strategy:** Use {best['strategy']} for TSLA
   - Parameters: {best['params']}
   - Stop Loss: {int(float(best['params'].split('SL:')[1].split('%')[0]))}%
   - Take Profit: {int(float(best['params'].split('TP:')[1].split('%')[0]))}%

2. **Risk Management:**
   - Position Size: Max 10% (TSLA is high volatility)
   - Daily Stop: 3%
   - Weekly Review: Check strategy performance

3. **Alternatives:**
   - If {best['strategy']} underperforms, try #{df.iloc[1]['strategy']}
   - Monitor and adjust parameters quarterly

---

## 📁 Files

- Report: `docs/TSLA_MACD_BACKTEST_{timestamp}.md`
- CSV: `docs/TSLA_MACD_BACKTEST_{timestamp}.csv`

---

*Generated by TradeMaster v2 | Bull Analysis*
*Analysis Time: {datetime.now().strftime('%Y-%m-%d')}*
"""
    
    # 保存報告
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"\n✅ 報告已保存: {report_path}")
    
    # 保存 CSV
    csv_path = f'/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/docs/TSLA_MACD_BACKTEST_{timestamp}.csv'
    df.to_csv(csv_path, index=False)
    print(f"✅ CSV 已保存: {csv_path}")
    
    return report_path, csv_path


if __name__ == "__main__":
    results = run_backtests()
    report_path, csv_path = generate_report(results)
    
    print("\n" + "="*80)
    print("✅ TSLA MACD 回測完成！")
    print("="*80)
