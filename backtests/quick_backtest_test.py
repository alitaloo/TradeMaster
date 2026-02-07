#!/usr/bin/env python3
"""
快速回測測試 - 排查異常數據
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from backtest import BacktestEngine
from core import PluginRegistry


def load_data(symbol):
    csv_path = PROJECT_DIR / "data" / "historical" / f"{symbol}.csv"
    df = pd.read_csv(csv_path, index_col=0)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    return df


def test_single(symbol, strategy_name):
    """測試單一策略"""
    print(f"\n=== {symbol} - {strategy_name} ===")
    
    data = load_data(symbol).tail(500).copy()
    print(f"數據: {len(data)} 天, \${data['Close'].min():.2f} - \${data['Close'].max():.2f}")
    
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
    
    strategy_cls = registry.get_strategy(strategy_name)
    if not strategy_cls:
        print(f"  ✗ 找不到策略")
        return
    
    try:
        strategy = strategy_cls()
        result = engine.run(symbol, strategy, data, strategy_name)
        
        # 計算夏普比率
        if result.volatility > 0:
            sharpe = (result.annualized_return - 0.02) / result.volatility
        else:
            sharpe = float('nan')
        
        print(f"  回測結果:")
        print(f"    報酬率: {result.total_return:.4f} ({result.total_return*100:.2f}%)")
        print(f"    年化報酬: {result.annualized_return:.4f}")
        print(f"    最大回撤: {result.max_drawdown:.4f} ({result.max_drawdown*100:.2f}%)")
        print(f"    波動率: {result.volatility:.6f}")
        print(f"    夏普比率: {sharpe:.4f}" if not np.isnan(sharpe) else f"    夏普比率: nan")
        print(f"    交易次數: {result.total_trades}")
        print(f"    勝率: {result.win_rate:.2%}")
        
        # 檢查權益曲線
        equity = result.equity_curve.tolist()
        print(f"  權益曲線:")
        print(f"    初始: \${equity[0]:,.2f}")
        print(f"    最終: \${equity[-1]:,.2f}")
        print(f"    最低: \${min(equity):,.2f}")
        print(f"    最高: \${max(equity):,.2f}")
        
        # 檢查異常
        if any(e <= 0 for e in equity):
            print(f"  ⚠️ 權益有零或負值!")
        
    except Exception as e:
        print(f"  ✗ 錯誤: {e}")
        import traceback
        traceback.print_exc()


def main():
    print("="*60)
    print("快速回測測試")
    print("="*60)
    
    # 測試報告中的異常策略
    test_cases = [
        ("AAPL", "Keltner_Bollinger_Squeeze"),
        ("AAPL", "Overbought_Decline"),
        ("AAPL", "VWAP_Reversal"),
        ("AAPL", "HistoricalVolatility_Range"),
        ("TSLA", "Keltner_Bollinger_Squeeze"),
        ("TSLA", "Overbought_Decline"),
    ]
    
    for symbol, strategy in test_cases:
        test_single(symbol, strategy)
    
    print("\n" + "="*60)
    print("測試完成")
    print("="*60)


if __name__ == "__main__":
    main()
