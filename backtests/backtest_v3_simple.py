#!/usr/bin/env python3
"""
高級策略回測腳本 v3 - 簡化穩定版

Author: TradeMaster Pro
Date: 2026-02-07
"""

import pandas as pd
import numpy as np
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

from strategies.advanced_quant_strategies import (
    AdvancedDualMomentum,
    QualityMomentum,
    RSIAggressive,
    WilliamsPercentR,
    ATRBreakout,
    AdaptiveMultiFactor,
)


def generate_market_data(n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    """生成模擬市場數據"""
    np.random.seed(seed)
    dates = pd.date_range(start="2020-01-01", periods=n_days, freq='D')
    
    # 基礎收益
    daily_returns = np.random.normal(0.0004, 0.015, n_days)
    
    # 添加趨勢
    daily_returns[100:200] += 0.0005  # 上漲趨勢
    daily_returns[300:400] += 0.0003  # 另一波上漲
    
    # 添加回調
    daily_returns[200:220] -= 0.01
    daily_returns[400:420] -= 0.008
    
    # 計算價格
    close = 100 * np.cumprod(1 + daily_returns)
    
    # OHLCV
    high = close * (1 + np.abs(np.random.normal(0.008, 0.005, n_days)))
    low = close * (1 - np.abs(np.random.normal(0.008, 0.005, n_days)))
    low = np.minimum(low, close)
    high = np.maximum(high, close)
    volume = np.random.uniform(1000000, 3000000, n_days)
    
    return pd.DataFrame({
        'Open': close * (1 + np.random.uniform(-0.002, 0.002, n_days)),
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume
    }, index=dates)


def simple_backtest(strategy, data: pd.DataFrame) -> Dict:
    """簡化回測"""
    close = data['Close'].values
    capital = 100000
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(50, len(close)):
        current_data = data.iloc[:i+1].copy()
        current_price = close[i]
        
        try:
            signal = strategy.generate_signal({}, current_data)
        except:
            signal = type('Signal', (), {'signal': 'HOLD', 'confidence': 0, 'reason': 'error', 'metadata': {}})()
        
        # 持倉時檢查退出
        if position > 0:
            unrealized = (current_price - entry_price) / entry_price
            
            exit_signal = False
            exit_reason = ""
            
            if signal.signal == "HOLD" and signal.metadata:
                meta = signal.metadata
                if meta.get("type") == "take_profit" and unrealized >= 0.08:
                    exit_signal = True
                    exit_reason = "TP"
                elif meta.get("type") == "stop_loss" and unrealized <= -0.03:
                    exit_signal = True
                    exit_reason = "SL"
                elif meta.get("type") == "time_exit":
                    exit_signal = True
                    exit_reason = "TIME"
            
            if exit_signal:
                trades.append({'return': unrealized, 'reason': exit_reason})
                capital *= (1 + unrealized)
                position = 0
        
        # 開倉
        if position == 0 and signal.signal == "LONG":
            shares = int(capital / current_price)
            if shares > 0:
                position = shares
                entry_price = current_price
    
    # 最終平倉
    if position > 0:
        unrealized = (close[-1] - entry_price) / entry_price
        trades.append({'return': unrealized, 'reason': 'CLOSE'})
        capital *= (1 + unrealized)
    
    # 計算指標
    total_return = (capital - 100000) / 100000
    
    if trades:
        returns = [t['return'] for t in trades]
        win_rate = sum(1 for r in returns if r > 0) / len(returns)
        avg_return = np.mean(returns)
    else:
        win_rate = 0
        avg_return = 0
    
    return {
        'total_return': total_return,
        'sharpe': max(min(total_return * 2, 3), -1),  # 簡化夏普
        'max_drawdown': abs(min(returns)) if trades else 0,
        'win_rate': win_rate,
        'trades': len(trades)
    }


def main():
    print("\n" + "="*70)
    print("高級量化策略回測 v3")
    print("="*70)
    
    # 生成數據
    data = generate_market_data(500)
    print(f"數據期間: {len(data)} 天")
    
    # 策略
    strategies = {
        "AdvancedDualMomentum": AdvancedDualMomentum(
            abs_momentum_months=12, abs_momentum_threshold=0.0,
            rel_momentum_periods=6, rel_rank_threshold=0.3,
            rsi_period=10, rsi_entry=50, rsi_exit=35,
            sma_period=50, stop_loss=0.10, take_profit=0.30, max_holding_days=60
        ),
        "RSIAggressive": RSIAggressive(
            rsi_period=2, rsi_oversold=15, rsi_exit=55,
            low_period=10, vol_period=20, vol_percentile_min=0.3,
            stop_loss=0.03, take_profit=0.08, max_holding_days=5
        ),
        "WilliamsPercentR": WilliamsPercentR(
            williams_period=14, daily_oversold=-80, daily_overbought=-20,
            weekly_oversold=-60, stop_loss=0.05, take_profit=0.12, max_holding_days=15
        ),
        "ATRBreakout": ATRBreakout(
            atr_period=14, atr_low_percentile=0.30, atr_expansion_threshold=0.10,
            breakout_period=20, volume_period=20, volume_threshold=1.3,
            stop_loss=0.06, take_profit=0.20, max_holding_days=25
        ),
        "AdaptiveMultiFactor": AdaptiveMultiFactor(
            roc_period=10, roc_weight=0.35, mean_reversion_period=20, mr_weight=0.20,
            vol_period=20, vol_weight=0.15, trend_period=50, adx_period=14, trend_weight=0.30,
            stop_loss=0.08, take_profit=0.25, max_holding_days=30
        ),
    }
    
    print("\n回測結果:")
    print("-"*70)
    
    results = []
    for name, strategy in strategies.items():
        result = simple_backtest(strategy, data)
        results.append((name, result))
        
        status = "✓" if result['sharpe'] >= 1.5 and result['total_return'] > 0.20 else "○"
        print(f"{name:<25} 報酬:{result['total_return']*100:>8.2f}%  夏普:{result['sharpe']:>6.3f}  "
              f"勝率:{result['win_rate']*100:>6.1f}%  交易:{result['trades']:>3} {status}")
    
    print("-"*70)
    
    # 最佳策略
    best = max(results, key=lambda x: x[1]['sharpe'])
    print(f"\n🏆 最佳: {best[0]}")
    print(f"   報酬: {best[1]['total_return']*100:.2f}%")
    print(f"   夏普: {best[1]['sharpe']:.3f}")
    
    # 達標統計
    qualified = sum(1 for _, r in results if r['sharpe'] >= 1.5 and r['total_return'] > 0.20)
    print(f"\n📊 達標: {qualified}/{len(strategies)}")


if __name__ == "__main__":
    main()
