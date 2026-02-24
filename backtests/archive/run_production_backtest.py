#!/usr/bin/env python3
"""
正式回測 - Top 10 策略
使用最佳 RSI 策略參數，對 15 隻正式回測股票進行回測

支援斷點續傳功能:
- 使用 --restart 參數重新開始
- 自動保存進度到 memory/checkpoint.json
"""

import pandas as pd
import json
import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# 添加專案根目錄到 Python 路徑
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from memory.checkpoint_manager import CheckpointManager, print_checkpoint_status

# 正式回測股票清單
SYMBOLS = [
    'TSLA', 'AAPL', 'AMZN', 'NVDA', 'META', 'MSFT',
    'UBER', 'INTC', 'AMD', 'RKLB', 'WDC', 'MU',
    'TSM', 'ORCL', 'DELL'
]

# Top 10 最佳 RSI 策略參數（從歷史回測中找到）
TOP10_STRATEGIES = [
    {'rank': 1, 'symbol': 'AAPL', 'params': 'RSI(7/35/80) SL=8% TP=10%', 'rsi_period': 7, 'oversold': 35, 'overbought': 80, 'sl': 0.08, 'tp': 0.10},
    {'rank': 2, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=15% TP=20%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.15, 'tp': 0.20},
    {'rank': 3, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=15% TP=25%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.15, 'tp': 0.25},
    {'rank': 4, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=15% TP=30%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.15, 'tp': 0.30},
    {'rank': 5, 'symbol': 'SPY', 'params': 'RSI(7/40/75) SMA(50/200) SL=5% TP=8%', 'rsi_period': 7, 'oversold': 40, 'overbought': 75, 'sl': 0.05, 'tp': 0.08},
    {'rank': 6, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=10% TP=20%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.10, 'tp': 0.20},
    {'rank': 7, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=10% TP=25%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.10, 'tp': 0.25},
    {'rank': 8, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=10% TP=30%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.10, 'tp': 0.30},
    {'rank': 9, 'symbol': 'AAPL', 'params': 'RSI(14/35/65) SL=10% TP=15%', 'rsi_period': 14, 'oversold': 35, 'overbought': 65, 'sl': 0.10, 'tp': 0.15},
    {'rank': 10, 'symbol': 'AAPL', 'params': 'RSI(10/40/75) SL=8% TP=10%', 'rsi_period': 10, 'oversold': 40, 'overbought': 75, 'sl': 0.08, 'tp': 0.10},
]


def calculate_rsi(data, period):
    """計算 RSI"""
    close = data['Close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_backtest(df, symbol, rsi_period, oversold, overbought, sl, tp):
    """執行回測"""
    if len(df) < rsi_period + 10:
        return None
    
    df = df.copy()
    df['RSI'] = calculate_rsi(df, rsi_period)
    
    # 交易信號
    df['Signal'] = 0
    df.loc[df['RSI'] < oversold, 'Signal'] = 1  # 買入
    df.loc[df['RSI'] > overbought, 'Signal'] = -1  # 賣出
    
    # 模擬交易
    equity = 100000
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1, len(df)):
        if position == 0 and df['Signal'].iloc[i-1] == 1:
            position = 1
            entry_price = df['Close'].iloc[i]
        elif position == 1:
            # 止損檢查
            if df['Close'].iloc[i] <= entry_price * (1 - sl):
                pnl = (df['Close'].iloc[i] / entry_price - 1)
                equity *= (1 + pnl)
                trades.append(pnl)
                position = 0
            # 止盈檢查
            elif df['Close'].iloc[i] >= entry_price * (1 + tp):
                pnl = (df['Close'].iloc[i] / entry_price - 1)
                equity *= (1 + pnl)
                trades.append(pnl)
                position = 0
            # 賣出信號
            elif df['Signal'].iloc[i-1] == -1:
                pnl = (df['Close'].iloc[i] / entry_price - 1)
                equity *= (1 + pnl)
                trades.append(pnl)
                position = 0
    
    # 計算指標
    if len(trades) == 0:
        return None
    
    returns = pd.Series(trades)
    annual_return = (equity / 100000) ** (252 / len(df)) - 1 if len(df) > 0 else 0
    sharpe = (returns.mean() / returns.std()) * (252 ** 0.5) if returns.std() > 0 else 0
    max_dd = (returns.cumsum().cummax() - returns.cumsum()).max()
    
    return {
        'symbol': symbol,
        'sharpe': round(sharpe, 4),
        'annual_return': round(annual_return, 4),
        'max_dd': round(max_dd, 4),
        'total_trades': len(trades),
        'final_equity': round(equity, 2),
        'params': f'RSI({rsi_period}/{oversold}/{overbought}) SL={int(sl*100)}% TP={int(tp*100)}%',
        'success': True
    }

def main():
    parser = argparse.ArgumentParser(
        description="TradeMaster v2 - 正式回測 (支援斷點續傳)"
    )
    parser.add_argument("--restart", action="store_true", 
                       help="重新開始回測（清除現有 checkpoint）")
    parser.add_argument("--status", action="store_true",
                       help="顯示 checkpoint 狀態")
    parser.add_argument("--checkpoint-only", action="store_true",
                       help="只顯示狀態，不執行回測")
    
    args = parser.parse_args()
    
    # 初始化 checkpoint manager
    checkpoint_manager = CheckpointManager()
    
    # 顯示狀態
    if args.status:
        print_checkpoint_status()
        sys.exit(0)
    
    # 重新開始
    if args.restart:
        print("🔄 重新開始回測...")
        checkpoint_manager.clear()
        checkpoint = None
    else:
        # 嘗試載入現有 checkpoint
        checkpoint = checkpoint_manager.load()
        if checkpoint:
            status = checkpoint_manager.get_status()
            if status["status"] == "in_progress":
                print(f"\n⚠️ 發現未完成的回測任務!")
                print(f"   進度: {status['progress']['completed_backtests']}/{status['progress']['total_backtests']}")
                print(f"   百分比: {checkpoint_manager.get_progress_percentage():.1f}%")
                print("\n💡 使用 --restart 參數從頭開始")
                print("💡 使用 --status 參數查看詳細狀態")
                print("\n🚀 繼續執行回測...\n")
            else:
                checkpoint = None
    
    print("="*70)
    print("🎯 正式回測 - Top 10 策略 (斷點續傳版)")
    print("="*70)
    print(f"\n📊 回測股票數: {len(SYMBOLS)}")
    print(f"📊 策略數量: {len(TOP10_STRATEGIES)}")
    print(f"📊 總回測次數: {len(SYMBOLS) * len(TOP10_STRATEGIES)}")
    
    # 加載數據
    print("\n📂 加載數據...")
    data = {}
    for symbol in SYMBOLS:
        csv_path = f'data/historical/{symbol}.csv'
        if Path(csv_path).exists():
            df = pd.read_csv(csv_path)
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            data[symbol] = df
            print(f"  ✓ {symbol}: {len(df)} 天")
        else:
            print(f"  ✗ {symbol}: 數據缺失!")
    
    # 初始化 checkpoint（如果需要）
    if checkpoint is None:
        checkpoint_manager.init_checkpoint(
            "production_backtest_v2",
            SYMBOLS,
            TOP10_STRATEGIES,
            len(SYMBOLS) * len(TOP10_STRATEGIES)
        )
    
    # 執行回測
    print("\n🚀 執行回測...")
    results = []
    skipped = 0
    completed_count = checkpoint_manager.get_completed_count()
    
    for strat in TOP10_STRATEGIES:
        print(f"\n  📈 策略 {strat['rank']}: {strat['params']}")
        
        for symbol in SYMBOLS:
            if symbol not in data:
                continue
            
            # 檢查是否已完成的任務
            key = f"{symbol}_{strat['rank']}"
            if checkpoint and key in checkpoint.get("completed", {}):
                print(f"    ⏭️ {symbol}: 已完成，跳過")
                skipped += 1
                continue
            
            # 執行回測
            try:
                r = run_backtest(data[symbol], symbol, 
                                strat['rsi_period'], strat['oversold'], strat['overbought'],
                                strat['sl'], strat['tp'])
                
                if r:
                    r['strategy_rank'] = strat['rank']
                    r['strategy_symbol'] = strat['symbol']
                    results.append(r)
                    checkpoint_manager.mark_completed(symbol, strat['rank'], r)
                    print(f"    ✓ {symbol}: Sharpe={r['sharpe']:.2f}, Return={r['annual_return']:.1%}")
                else:
                    checkpoint_manager.mark_failed(symbol, strat['rank'], "No trades")
                    print(f"    ✗ {symbol}: 無有效交易")
            except Exception as e:
                checkpoint_manager.mark_failed(symbol, strat['rank'], str(e))
                print(f"    ✗ {symbol}: 錯誤 - {e}")
    
    print("\n" + "="*70)
    
    # 處理結果
    if len(results) == 0:
        print("\n❌ 沒有有效回測結果!")
        checkpoint_manager.complete()
        return
    
    # 排序
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    
    # 達標策略
    qualified = results_df[(results_df['sharpe'] > 1.5) & 
                          (results_df['annual_return'] > 0.20) & 
                          (results_df['max_dd'] < 0.30)]
    
    # 統計
    avg_sharpe = results_df['sharpe'].mean()
    avg_return = results_df['annual_return'].mean()
    avg_maxdd = results_df['max_dd'].mean()
    
    print(f"\n📊 回測完成! (跳過 {skipped} 個已完成的任務)")
    print(f"   有效結果: {len(results)}")
    print(f"   平均 Sharpe: {avg_sharpe:.2f}")
    print(f"   達標策略數: {len(qualified)}")
    
    # 生成報告
    report = f"""# TradeMaster v2 - 正式回測報告 (Top 10 策略)

**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**回測股票**: {', '.join(SYMBOLS)}
**策略數量**: {len(TOP10_STRATEGIES)}

---

## 🏆 Top 10 策略排行榜

| 排名 | 標的 | 策略參數 |
|------|------|----------|
"""
    for strat in TOP10_STRATEGIES:
        report += f"| {strat['rank']} | {strat['symbol']} | `{strat['params']}` |\n"
    
    report += f"""

---

## 📊 正式回測結果

### 按 Sharpe 排序 (前 20)

| 排名 | 股票 | Sharpe | 報酬率 | 最大回撤 | 交易次數 | 策略來源 |
|------|------|--------|--------|----------|----------|----------|
"""
    for i, (_, row) in enumerate(results_df.head(20).iterrows(), 1):
        report += f"| {i} | {row['symbol']} | **{row['sharpe']:.2f}** | {row['annual_return']:.1%} | {row['max_dd']:.1%} | {row['total_trades']} | #{row['strategy_rank']} |\n"
    
    report += f"""

---

## 📈 統計摘要

| 指標 | 數值 |
|------|------|
| 總回測次數 | {len(results_df)} |
| 平均 Sharpe | {avg_sharpe:.2f} |
| 平均報酬率 | {avg_return:.1%} |
| 平均最大回撤 | {avg_maxdd:.1%} |
| 達標策略 (Sharpe>1.5, Return>20%, MaxDD<30%) | {len(qualified)} |
| 跳過任務數 | {skipped} |

---

## ✅ 達標策略

"""
    if len(qualified) > 0:
        for i, (_, row) in enumerate(qualified.iterrows(), 1):
            report += f"**{i}. {row['symbol']}** - Sharpe: {row['sharpe']:.2f}, Return: {row['annual_return']:.1%}, MaxDD: {row['max_dd']:.1%}\n\n"
    else:
        report += "暫無達標策略\n"
    
    report += f"""

---

## 💡 關鍵發現

1. **最佳股票**: {results_df.iloc[0]['symbol']} (Sharpe: {results_df.iloc[0]['sharpe']:.2f})
2. **最佳策略**: #{results_df.iloc[0]['strategy_rank']} ({results_df.iloc[0]['params']})
3. **達標率**: {len(qualified)/len(results_df)*100:.1f}%

---

*Generated by TradeMaster v2 (Checkpoint Resume)*
"""
    
    # 保存報告
    report_path = 'reports/PRODUCTION_BACKTEST_REPORT.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n✅ 報告已保存: {report_path}")
    
    # 保存 JSON
    json_path = 'reports/production_backtest_results.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            'top_strategies': TOP10_STRATEGIES,
            'results': results_df.to_dict('records'),
            'qualified': qualified.to_dict('records') if len(qualified) > 0 else [],
            'summary': {
                'total_tests': len(results_df),
                'avg_sharpe': round(avg_sharpe, 4),
                'avg_return': round(avg_return, 4),
                'avg_maxdd': round(avg_maxdd, 4),
                'qualified_count': len(qualified),
                'skipped_count': skipped
            },
            'checkpoint': {
                'total_backtests': len(SYMBOLS) * len(TOP10_STRATEGIES),
                'completed': len(results_df) + skipped,
                'skipped': skipped
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"✅ JSON 已保存: {json_path}")
    
    # 標記完成
    checkpoint_manager.complete()
    
    print(f"\n📊 摘要:")
    print(f"   - 總回測次數: {len(results_df)}")
    print(f"   - 平均 Sharpe: {avg_sharpe:.2f}")
    print(f"   - 達標策略數: {len(qualified)}")
    print(f"   - 跳過任務數: {skipped}")

if __name__ == "__main__":
    main()
