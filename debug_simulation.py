#!/usr/bin/env python3
"""
模擬報告中的異常情況
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

# 添加專案根目錄
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest import BacktestEngine, calculate_indicators
from core import PluginRegistry


def load_data(symbol):
    """載入股票數據"""
    csv_path = PROJECT_DIR / "data" / "historical" / f"{symbol}.csv"
    df = pd.read_csv(csv_path, index_col=0)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    return df


def simulate_all_strategies():
    """模擬所有策略的回測"""
    print("="*80)
    print("🚀 模擬所有策略回測")
    print("="*80)
    
    # 載入數據
    data = load_data("AAPL").tail(500).copy()
    print(f"\n📊 AAPL 數據: {len(data)} 天")
    
    # 初始化回測引擎
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.001,
        kelly_fraction=0.5
    )
    
    # 獲取所有策略
    registry = PluginRegistry()
    strategies_path = PROJECT_DIR / "strategies"
    for category in strategies_path.iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    strategies = []
    for name, meta in registry.list_strategies():
        strategies.append({
            'name': name,
            'cls': registry.get_strategy(name)
        })
    
    print(f"\n📈 測試 {len(strategies)} 個策略...")
    
    results = []
    for i, s in enumerate(strategies):
        try:
            if s['cls'] is None:
                continue
                
            # 提取參數
            params = {}
            strategy = s['cls'](**params)
            
            # 運行回測
            backtest_result = engine.run("AAPL", strategy, data, s['name'])
            
            # 計算夏普比率
            if backtest_result.volatility > 0 and not np.isnan(backtest_result.volatility):
                sharpe = (backtest_result.annualized_return - 0.02) / backtest_result.volatility
            else:
                sharpe = np.nan
            
            results.append({
                'strategy': s['name'],
                'return': backtest_result.total_return,
                'max_dd': backtest_result.max_drawdown,
                'sharpe': sharpe,
                'volatility': backtest_result.volatility,
                'win_rate': backtest_result.win_rate,
                'trades': backtest_result.total_trades
            })
            
            if i < 5:
                print(f"   {s['name']}: 夏普={sharpe:.2f}, 報酬={backtest_result.total_return:.2%}, 最大回撤={backtest_result.max_drawdown:.2%}")
            
        except Exception as e:
            print(f"   ✗ {s['name']}: {e}")
            continue
    
    print(f"\n📊 統計:")
    print(f"   成功: {len(results)}")
    
    # 檢查異常值
    print(f"\n🔍 異常檢查:")
    for r in results:
        if r['return'] < -100:
            print(f"   ⚠️ {r['strategy']}: 報酬率異常 {r['return']:.2%}")
        if r['max_dd'] > 100:
            print(f"   ⚠️ {r['strategy']}: 最大回撤異常 {r['max_dd']:.2%}")
        if np.isnan(r['sharpe']):
            print(f"   ⚠️ {r['strategy']}: 夏普比率是 NaN")
    
    # 排序
    results.sort(key=lambda x: x['sharpe'] if not np.isnan(x['sharpe']) else -999, reverse=True)
    
    print(f"\n🏆 Top 5:")
    for i, r in enumerate(results[:5]):
        sharpe_str = f"{r['sharpe']:.2f}" if not np.isnan(r['sharpe']) else "nan"
        print(f"   {i+1}. {r['strategy']}: 夏普={sharpe_str}, 報酬={r['return']:.2%}, 最大回撤={r['max_dd']:.2%}")
    
    print(f"\n💀 Bottom 5:")
    for i, r in enumerate(results[-5:]):
        sharpe_str = f"{r['sharpe']:.2f}" if not np.isnan(r['sharpe']) else "nan"
        print(f"   {i+1}. {r['strategy']}: 夏普={sharpe_str}, 報酬={r['return']:.2%}, 最大回撤={r['max_dd']:.2%}")


def debug_volatility_calculation():
    """調試波動率計算"""
    print("\n" + "="*80)
    print("📊 波動率計算 Debug")
    print("="*80)
    
    # 測試不同的權益曲線
    test_cases = [
        ("正常", [100000, 105000, 103000, 108000, 110000]),
        ("小幅下跌", [100000, 98000, 96000, 97000, 95000]),
        ("大幅下跌", [100000, 50000, 25000, 10000, 5000]),
        ("歸零", [100000, 50000, 0, 0, 0]),
        ("為負", [100000, 50000, -10000, -50000, -100000]),
        ("波動大", [100000, 120000, 80000, 140000, 60000]),
    ]
    
    for name, equity in test_cases:
        equity_series = pd.Series(equity)
        returns = equity_series.pct_change().dropna()
        
        if len(returns) > 0:
            volatility = returns.std() * np.sqrt(252)
            print(f"\n{name}:")
            print(f"   報酬: {returns.tolist()}")
            print(f"   標準差: {returns.std():.6f}")
            print(f"   波動率 (年化): {volatility:.6f}")
            
            # 計算夏普
            if volatility > 0:
                annualized_return = ((equity[-1] - equity[0]) / equity[0]) if equity[0] != 0 else 0
                sharpe = (annualized_return - 0.02) / volatility
                print(f"   年化報酬: {annualized_return:.4f}")
                print(f"   夏普比率: {sharpe:.4f}")
            else:
                print(f"   ⚠️ 波動率為 0，無法計算夏普")
        else:
            print(f"\n{name}:")
            print(f"   ⚠️ 無法計算波動率（報酬序列為空）")


def debug_specific_strategy():
    """調試特定策略"""
    print("\n" + "="*80)
    print("🎯 調試特定策略 - Keltner_Bollinger_Squeeze")
    print("="*80)
    
    data = load_data("AAPL").tail(500).copy()
    
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.001,
        kelly_fraction=0.5
    )
    
    registry = PluginRegistry()
    for category in (PROJECT_DIR / "strategies").iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    strategy = registry.get_strategy("Keltner_Bollinger_Squeeze")()
    result = engine.run("AAPL", strategy, data, "Keltner_Bollinger_Squeeze")
    
    print(f"\n📋 回測結果:")
    print(f"   總報酬: {result.total_return:.6f} ({result.total_return:.2%})")
    print(f"   年化報酬: {result.annualized_return:.6f}")
    print(f"   最大回撤: {result.max_drawdown:.6f} ({result.max_drawdown:.2%})")
    print(f"   波動率: {result.volatility:.6f}")
    print(f"   勝率: {result.win_rate:.6f} ({result.win_rate:.2%})")
    print(f"   交易次數: {result.total_trades}")
    print(f"   盈虧比: {result.profit_factor:.2f}")
    
    # 計算夏普
    if result.volatility > 0 and not np.isnan(result.volatility):
        sharpe = (result.annualized_return - 0.02) / result.volatility
        print(f"   夏普比率: {sharpe:.4f}")
    else:
        print(f"   夏普比率: NaN (波動率為 {result.volatility})")
    
    # 檢查權益曲線
    equity = result.equity_curve.tolist()
    print(f"\n📈 權益曲線:")
    print(f"   初始: ${equity[0]:,.2f}")
    print(f"   最終: ${equity[-1]:,.2f}")
    print(f"   最低: ${min(equity):,.2f}")
    print(f"   最高: ${max(equity):,.2f}")
    
    # 報酬率
    total_ret = (equity[-1] - equity[0]) / equity[0]
    print(f"   報酬率: {total_ret:.4f} ({total_ret:.2%})")


def main():
    print("="*80)
    print("🐛 模擬報告異常情況")
    print("="*80)
    
    simulate_all_strategies()
    debug_volatility_calculation()
    debug_specific_strategy()
    
    print("\n" + "="*80)
    print("✅ 完成")
    print("="*80)


if __name__ == "__main__":
    main()
