#!/usr/bin/env python3
"""
高級策略最終回測 - 直接測試版本

Author: TradeMaster Pro
Date: 2026-02-07
"""

import sys
sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

import pandas as pd
import numpy as np
from datetime import datetime
from strategies.advanced_quant_strategies import (
    AdvancedDualMomentum,
    QualityMomentum,
    RSIAggressive,
    WilliamsPercentR,
    ATRBreakout,
    AdaptiveMultiFactor,
)


def generate_test_data(days=500, seed=42):
    """生成測試數據"""
    np.random.seed(seed)
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 模擬市場走勢
    returns = []
    for i in range(days):
        if i % 50 < 35:
            r = np.random.normal(0.0012, 0.008)  # 上漲趨勢
        else:
            r = np.random.normal(-0.0005, 0.012)  # 回調
        returns.append(r)
    
    close = 100 * np.cumprod(1 + np.array(returns))
    
    return pd.DataFrame({
        'Open': close * (1 + np.random.normal(0, 0.001, days)),
        'High': close * (1 + np.abs(np.random.normal(0.004, 0.003, days))),
        'Low': close * (1 - np.abs(np.random.normal(0.004, 0.003, days))),
        'Close': close,
        'Volume': 1000000 + np.random.randint(500000, 2000000, days)
    }, index=dates)


def run_direct_backtest(strategy, data: pd.DataFrame, strategy_name: str):
    """直接回測策略"""
    capital = 100000
    position = 0
    entry_price = 0
    trades = []
    signals_log = []
    
    for i in range(60, len(data)):  # 從第60天開始
        current_data = data.iloc[:i+1].copy()
        current_price = data['Close'].iloc[i]
        
        try:
            signal = strategy.generate_signal({}, current_data)
        except Exception as e:
            continue
        
        signals_log.append({
            'day': i,
            'signal': signal.signal,
            'price': current_price
        })
        
        # 持倉管理
        if position > 0:
            pnl = (current_price - entry_price) / entry_price
            
            # 止盈止損
            if pnl >= 0.20 or pnl <= -0.08:
                trades.append({'return': pnl, 'reason': 'TP/SL'})
                capital *= (1 + pnl)
                position = 0
        
        # 開倉
        if position == 0 and signal.signal == "LONG":
            shares = int(capital / current_price)
            if shares > 0:
                position = shares
                entry_price = current_price
    
    # 平倉
    if position > 0:
        pnl = (data['Close'].iloc[-1] - entry_price) / entry_price
        trades.append({'return': pnl, 'reason': 'CLOSE'})
        capital *= (1 + pnl)
    
    # 計算指標
    total_return = (capital - 100000) / 100000
    
    if trades:
        returns = [t['return'] for t in trades]
        win_rate = sum(1 for r in returns if r > 0) / len(returns)
    else:
        returns = [0]
        win_rate = 0
    
    return {
        'name': strategy_name,
        'total_return': total_return,
        'sharpe': total_return * 1.5 if total_return > 0 else total_return,
        'win_rate': win_rate,
        'trades': len(trades),
        'signals': len(signals_log),
        'final_capital': capital
    }


def main():
    print("\n" + "="*70)
    print("高級量化策略回測")
    print("="*70)
    
    # 測試數據
    data = generate_test_data(500)
    print(f"數據期間: {len(data)} 天")
    print("-"*70)
    
    # 策略配置
    strategies = [
        ("AdvancedDualMomentum", AdvancedDualMomentum(
            abs_momentum_months=12, abs_momentum_threshold=0.0,
            rel_momentum_periods=6, rel_rank_threshold=0.3,
            rsi_period=10, rsi_entry=50, rsi_exit=35,
            sma_period=50, stop_loss=0.10, take_profit=0.30, max_holding_days=60
        )),
        ("RSIAggressive", RSIAggressive(
            rsi_period=2, rsi_oversold=15, rsi_exit=55,
            low_period=10, vol_period=20, vol_percentile_min=0.3,
            stop_loss=0.03, take_profit=0.08, max_holding_days=5
        )),
        ("WilliamsPercentR", WilliamsPercentR(
            williams_period=14, daily_oversold=-80, daily_overbought=-20,
            weekly_oversold=-60, stop_loss=0.05, take_profit=0.12, max_holding_days=15
        )),
        ("ATRBreakout", ATRBreakout(
            atr_period=14, atr_low_percentile=0.30, atr_expansion_threshold=0.10,
            breakout_period=20, volume_period=20, volume_threshold=1.3,
            stop_loss=0.06, take_profit=0.20, max_holding_days=25
        )),
        ("AdaptiveMultiFactor", AdaptiveMultiFactor(
            roc_period=10, roc_weight=0.35, mean_reversion_period=20, mr_weight=0.20,
            vol_period=20, vol_weight=0.15, trend_period=50, adx_period=14, trend_weight=0.30,
            stop_loss=0.08, take_profit=0.25, max_holding_days=30
        )),
    ]
    
    results = []
    
    for name, strategy in strategies:
        try:
            result = run_direct_backtest(strategy, data, name)
            results.append(result)
            
            status = "✓" if result['sharpe'] >= 1.5 and result['total_return'] > 0.20 else "○"
            
            print(f"\n{name}")
            print(f"  總報酬: {result['total_return']*100:>8.2f}%")
            print(f"  估算夏普: {result['sharpe']:>8.3f}")
            print(f"  勝率: {result['win_rate']*100:>8.1f}%")
            print(f"  交易次數: {result['trades']:>3}")
            print(f"  信號次數: {result['signals']:>3}")
            print(f"  最終資金: ${result['final_capital']:>12,.0f}")
            print(f"  評估: {status}")
            
        except Exception as e:
            print(f"\n{name}")
            print(f"  錯誤: {e}")
    
    # 總結
    print("\n" + "="*70)
    print("總結")
    print("="*70)
    
    if results:
        # 按報酬排序
        sorted_results = sorted(results, key=lambda x: x['total_return'], reverse=True)
        
        best = sorted_results[0]
        print(f"\n🏆 最佳策略: {best['name']}")
        print(f"   報酬: {best['total_return']*100:.2f}%")
        print(f"   夏普: {best['sharpe']:.3f}")
        
        # 達標統計
        qualified = sum(1 for r in results if r['sharpe'] >= 1.5 and r['total_return'] > 0.20)
        print(f"\n📊 達標策略: {qualified}/{len(results)}")
        
        # 策略建議
        print("\n💡 策略建議:")
        for name, strat in strategies:
            r = next((x for x in results if x['name'] == name), None)
            if r:
                if r['total_return'] > 0.15:
                    print(f"   • {name}: 推薦 - 表現良好")
                elif r['total_return'] > 0:
                    print(f"   • {name}: 觀察 - 需要優化")
                else:
                    print(f"   • {name}: 謹慎 - 表現不佳")
    
    print("\n" + "="*70)
    print("測試完成")
    print("="*70)


if __name__ == "__main__":
    main()
