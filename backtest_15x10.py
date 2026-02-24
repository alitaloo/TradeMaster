#!/usr/bin/env python3
"""
TradeMaster v2 - 15 stocks × 10 strategies comprehensive backtest
"""

import pandas as pd
import numpy as np
from datetime import datetime
from backtest import BacktestEngine
from core import PluginRegistry
import warnings
import sys
warnings.filterwarnings('ignore')

# Configuration
STOCKS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'NFLX', 'AMD', 'INTC', 'CRM', 'ORCL', 'ADBE', 'PYPL', 'SHOP']
STRATEGIES = [
    'Oversold_Bounce',
    'MACDTrend',
    'ADXTrend', 
    'RSI_Divergence',
    'Bollinger_Mean_Reversion',
    'Three_MA_Trend',
    'Dual_Moving_Average_Crossover',
    'CCI_Mean_Reversion',
    'Stochastic_RSI_Oscillator',
    'WilliamsR_Momentum'
]

def load_data(symbol):
    """Load stock data from CSV"""
    filepath = f"data/historical/{symbol}.csv"
    if not os.path.exists(filepath):
        return None
    
    try:
        df = pd.read_csv(filepath, index_col='Date', parse_dates=True)
        return df
    except Exception as e:
        print(f"   [ERROR] Failed to load {symbol}: {e}")
        return None

def run_backtests():
    """Run comprehensive backtests"""
    
    print(f"\n{'='*70}")
    print(f"TradeMaster v2 - 完整回測 (15 股票 × 10 策略)")
    print(f"時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # Initialize
    engine = BacktestEngine(initial_capital=100000)
    registry = PluginRegistry()
    registry.discover_plugins('strategies/')
    
    results = []
    total_tests = len(STOCKS) * len(STRATEGIES)
    completed = 0
    
    for symbol in STOCKS:
        print(f"📊 {symbol}")
        data = load_data(symbol)
        
        if data is None:
            print(f"   ❌ 數據不存在\n")
            continue
        
        print(f"   ✅ 數據載入成功 ({len(data)} 天)")
        
        for strategy_name in STRATEGIES:
            completed += 1
            
            # Check if strategy exists
            if strategy_name not in [s[0] for s in registry.list_strategies()]:
                print(f"   [{completed:3d}/{total_tests}] {strategy_name}: ❌ 策略不存在")
                continue
            
            try:
                # Run backtest
                strategy_class = registry.get_strategy(strategy_name)
                strategy = strategy_class()
                result = engine.run(symbol, strategy, data, strategy_name)
                
                # Calculate metrics
                sharpe = result.annualized_return / result.volatility if result.volatility > 0 else 0
                max_dd = abs(result.max_drawdown) if result.max_drawdown else 0
                
                results.append({
                    'stock': symbol,
                    'strategy': strategy_name,
                    'total_return': result.total_return * 100,
                    'sharpe_ratio': sharpe,
                    'max_drawdown': max_dd,
                    'num_trades': result.total_trades,
                    'win_rate': getattr(result, 'win_rate', 0)
                })
                
                emoji = "📈" if result.total_return > 0 else "📉"
                print(f"   [{completed:3d}/{total_tests}] {strategy_name}: {emoji} {result.total_return*100:>7.1f}% | 夏普 {sharpe:>5.2f} | DD {max_dd:>5.1f}% | 交易 {result.total_trades}")
                
            except Exception as e:
                print(f"   [{completed:3d}/{total_tests}] {strategy_name}: ❌ {str(e)[:40]}")
        
        print()
    
    return results

def generate_report(results):
    """Generate markdown report"""
    
    print(f"\n{'='*70}")
    print("📊 結果摘要")
    print(f"{'='*70}")
    
    if not results:
        print("❌ 沒有有效結果")
        return
    
    df = pd.DataFrame(results)
    
    # Top 10 by Sharpe ratio
    df_sorted = df.sort_values('sharpe_ratio', ascending=False)
    top10 = df_sorted.head(10)
    
    print(f"\n🏆 Top 10 策略 (按夏普比率排序):\n")
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        print(f"   {i}. {row['stock']} - {row['strategy']}")
        print(f"      📈 報酬: {row['total_return']:>8.2f}% | 夏普: {row['sharpe_ratio']:>5.2f} | DD: {row['max_drawdown']:>5.1f}% | 交易: {row['num_trades']}")
    
    # Best strategy per stock
    print(f"\n📊 各股票最佳策略:\n")
    for symbol in STOCKS:
        stock_df = df[df['stock'] == symbol]
        if len(stock_df) > 0:
            best = stock_df.sort_values('sharpe_ratio', ascending=False).iloc[0]
            print(f"   {symbol:6s}: {best['strategy']:<30} (夏普 {best['sharpe_ratio']:.2f}, {best['total_return']:>7.1f}%)")
    
    # Save files
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # CSV
    csv_file = f"docs/backtest_15x10_{timestamp}.csv"
    df.to_csv(csv_file, index=False)
    print(f"\n✅ CSV 已保存: {csv_file}")
    
    # Markdown report
    md_file = f"docs/backtest_15x10_{timestamp}.md"
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# TradeMaster v2 - 完整回測報告\n\n")
        f.write(f"**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## 📊 測試配置\n\n")
        f.write(f"- **股票數**: {len(STOCKS)}\n")
        f.write(f"- **策略數**: {len(STRATEGIES)}\n")
        f.write(f"- **總測試數**: {len(results)}\n")
        f.write(f"- **起始資金**: $100,000\n\n")
        f.write(f"---\n\n")
        f.write(f"## 🏆 Top 10 策略 (按夏普比率排序)\n\n")
        f.write(f"| 排名 | 股票 | 策略 | 報酬率 | 夏普 | 最大回撤 | 交易數 |\n")
        f.write(f"|------|------|------|--------|------|----------|--------|\n")
        for i, (_, row) in enumerate(top10.iterrows(), 1):
            f.write(f"| {i} | {row['stock']} | {row['strategy']} | {row['total_return']:.2f}% | {row['sharpe_ratio']:.2f} | {row['max_drawdown']:.1f}% | {row['num_trades']} |\n")
        f.write(f"\n---\n*Generated by TradeMaster v2*\n")
    
    print(f"✅ Markdown 報告已保存: {md_file}")
    
    print(f"\n{'='*70}")
    print("✅ 完整回測完成!")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    import os
    os.chdir("/Users/alita/.openclaw/workspace/codes/TradeMaster_v2")
    results = run_backtests()
    generate_report(results)
