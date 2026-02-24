#!/usr/bin/env python3
"""
深入排查回測引擎異常數據
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


def debug_max_drawdown_calculation():
    """調試最大回撤計算"""
    print("="*80)
    print("🔍 調試最大回撤計算")
    print("="*80)
    
    # 測試 1: 正常權益曲線
    equity_normal = [100000, 105000, 103000, 108000, 110000]
    
    # 測試 2: 權益歸零
    equity_zero = [100000, 50000, 0, 0, 0]
    
    # 測試 3: 權益為負
    equity_negative = [100000, 50000, -10000, -50000, -100000]
    
    # 測試 4: 除以零的情況
    equity_div_zero = [100000, 0, 0, 0, 0]
    
    def calculate_max_drawdown(equity_list, name):
        print(f"\n📊 {name}:")
        print(f"   權益: {equity_list}")
        
        equity_series = pd.Series(equity_list)
        rolling_max = equity_series.expanding().max()
        
        print(f"   rolling_max: {rolling_max.tolist()}")
        
        # 檢查 rolling_max 是否為 0
        if (rolling_max == 0).any():
            print(f"   ⚠️ rolling_max 包含 0!")
        
        try:
            drawdown = (equity_series - rolling_max) / rolling_max.replace(0, np.nan)
            print(f"   drawdown: {drawdown.tolist()}")
            max_dd = abs(drawdown.min())
            print(f"   最大回撤: {max_dd:.4f}")
        except Exception as e:
            print(f"   ✗ 錯誤: {e}")
    
    calculate_max_drawdown(equity_normal, "正常權益曲線")
    calculate_max_drawdown(equity_zero, "權益歸零")
    calculate_max_drawdown(equity_negative, "權益為負")
    calculate_max_drawdown(equity_div_zero, "除以零測試")


def debug_real_strategy():
    """用真實策略調試"""
    print("\n" + "="*80)
    print("🚀 真實策略調試")
    print("="*80)
    
    # 載入數據
    data = load_data("AAPL").tail(500).copy()
    print(f"\n📊 AAPL 數據: {len(data)} 天")
    
    # 創建引擎
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.001,
        kelly_fraction=0.5
    )
    
    # 獲取策略
    registry = PluginRegistry()
    for category in (PROJECT_DIR / "strategies").iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    strategy = registry.get_strategy("Keltner_Bollinger_Squeeze")()
    
    # 運行回測
    print(f"\n🎯 運行 Keltner_Bollinger_Squeeze 回測...")
    result = engine.run("AAPL", strategy, data, "Keltner_Bollinger_Squeeze")
    
    # 打印結果
    print(f"\n📋 回測結果:")
    print(f"   總報酬: {result.total_return:.4f} ({result.total_return:.2%})")
    print(f"   年化報酬: {result.annualized_return:.4f}")
    print(f"   最大回撤: {result.max_drawdown:.4f} ({result.max_drawdown:.2%})")
    print(f"   波動率: {result.volatility:.4f}")
    print(f"   總交易次數: {result.total_trades}")
    print(f"   勝率: {result.win_rate:.4f} ({result.win_rate:.2%})")
    
    # 檢查異常
    print(f"\n🔍 異常檢查:")
    if result.total_return < -100:
        print(f"   ⚠️ 報酬率異常低: {result.total_return:.2%}")
    if result.max_drawdown > 100:
        print(f"   ⚠️ 最大回撤異常高: {result.max_drawdown:.2%}")
    if result.volatility > 10:
        print(f"   ⚠️ 波動率異常高: {result.volatility:.4f}")
    
    # 檢查權益曲線
    equity = result.equity_curve.tolist()
    print(f"\n📈 權益曲線:")
    print(f"   初始: ${equity[0]:,.2f}")
    print(f"   最終: ${equity[-1]:,.2f}")
    print(f"   最低: ${min(equity):,.2f}")
    print(f"   最高: ${max(equity):,.2f}")
    
    if any(e < 0 for e in equity):
        print(f"   ⚠️ 權益出現負值!")
        negative_idx = [i for i, e in enumerate(equity) if e < 0]
        print(f"   負值索引: {negative_idx}")
    
    # 檢查 NaN
    if np.isnan(result.total_return):
        print(f"   ⚠️ total_return 是 NaN")
    if np.isnan(result.max_drawdown):
        print(f"   ⚠️ max_drawdown 是 NaN")
    if np.isnan(result.volatility):
        print(f"   ⚠️ volatility 是 NaN")


def debug_shapre_ratio():
    """調試夏普比率計算"""
    print("\n" + "="*80)
    print("📊 夏普比率計算 Debug")
    print("="*80)
    
    # 測試夏普比率計算
    equity_normal = [100000, 105000, 103000, 108000, 110000, 115000, 112000, 118000]
    equity_negative = [100000, 50000, 0, 0, 0]
    equity_nan = [100000, np.nan, 50000, np.nan, 0]
    
    def calculate_sharpe(equity_list, name):
        print(f"\n📊 {name}:")
        equity_series = pd.Series(equity_list)
        returns = equity_series.pct_change().dropna()
        
        print(f"   returns: {returns.tolist()}")
        
        if len(returns) > 0:
            mean_return = returns.mean()
            std_return = returns.std()
            
            print(f"   mean: {mean_return:.6f}")
            print(f"   std: {std_return:.6f}")
            
            if std_return > 0:
                # 年化夏普比率 (假設每日數據)
                sharpe = (mean_return - 0.02/252) / std_return * np.sqrt(252)
                print(f"   夏普比率: {sharpe:.4f}")
            else:
                print(f"   ⚠️ 標準差為 0，無法計算夏普比率")
        else:
            print(f"   ⚠️ 無法計算報酬")
    
    calculate_sharpe(equity_normal, "正常權益")
    calculate_sharpe(equity_negative, "權益為負")
    calculate_sharpe(equity_nan, "包含 NaN")


def debug_trade_analysis():
    """調試交易分析"""
    print("\n" + "="*80)
    print("💰 交易分析 Debug")
    print("="*80)
    
    # 模擬交易數據
    trades = [
        {"net_pnl": 1000, "commission": 10, "slippage_cost": 5},
        {"net_pnl": -500, "commission": 10, "slippage_cost": 5},
        {"net_pnl": 2000, "commission": 20, "slippage_cost": 10},
        {"net_pnl": -300, "commission": 10, "slippage_cost": 5},
    ]
    
    def analyze_trades(trade_list, name):
        print(f"\n📊 {name}:")
        
        pnls = [t.get("net_pnl", 0) for t in trade_list]
        total_trades = len(trade_list)
        winning = len([p for p in pnls if p > 0])
        losing = len([p for p in pnls if p <= 0])
        
        print(f"   總交易: {total_trades}")
        print(f"   盈利: {winning}")
        print(f"   虧損: {losing}")
        print(f"   勝率: {winning/total_trades:.2%}" if total_trades > 0 else "   勝率: N/A")
        
        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p <= 0]
        
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        
        print(f"   平均盈利: ${avg_win:.2f}")
        print(f"   平均虧損: ${avg_loss:.2f}")
        
        if avg_loss > 0:
            profit_factor = avg_win / avg_loss
            print(f"   盈虧比: {profit_factor:.2f}")
        else:
            print(f"   盈虧比: N/A")
    
    analyze_trades(trades, "正常交易")
    
    # 異常情況：無交易
    analyze_trades([], "無交易")
    
    # 異常情況：只有虧損
    losses_only = [
        {"net_pnl": -500, "commission": 10, "slippage_cost": 5},
        {"net_pnl": -300, "commission": 10, "slippage_cost": 5},
    ]
    analyze_trades(losses_only, "只有虧損")


def main():
    print("="*80)
    print("🐛 回測引擎異常排查")
    print("="*80)
    
    debug_max_drawdown_calculation()
    debug_shapre_ratio()
    debug_trade_analysis()
    
    # 真實策略測試（可選，會比較慢）
    print("\n" + "="*80)
    print("🧪 真實策略測試")
    print("="*80)
    debug_real_strategy()
    
    print("\n" + "="*80)
    print("✅ Debug 完成")
    print("="*80)


if __name__ == "__main__":
    main()
