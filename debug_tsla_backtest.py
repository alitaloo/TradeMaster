#!/usr/bin/env python3
"""
TSLA 單股票回測 Debug 腳本
功能：詳細檢查指標計算、策略信號、交易執行
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


def load_tsla_data():
    """載入 TSLA 數據"""
    csv_path = PROJECT_DIR / "data" / "historical" / "TSLA.csv"
    df = pd.read_csv(csv_path, index_col=0)
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    # 只取最近 500 天數據來加速測試
    df = df.tail(500).copy()
    
    print(f"📊 載入 TSLA 數據: {len(df)} 天")
    print(f"   日期範圍: {df.index[0].date()} ~ {df.index[-1].date()}")
    print(f"   價格範圍: ${df['Close'].min():.2f} ~ ${df['Close'].max():.2f}")
    
    return df


def debug_indicators(data):
    """Debug 指標計算"""
    print("\n" + "="*80)
    print("🔍 指標計算 Debug")
    print("="*80)
    
    indicators = calculate_indicators(data)
    
    for name, values in indicators.items():
        print(f"\n📈 {name}:")
        latest = data.index[-1]
        for key, series in values.items():
            val = series.iloc[-1] if len(series) > 0 else float('nan')
            print(f"   {key}: {val:.4f}" if not pd.isna(val) else f"   {key}: NaN")
    
    return indicators


def debug_strategies():
    """Debug 策略"""
    print("\n" + "="*80)
    print("🎯 策略 Debug")
    print("="*80)
    
    registry = PluginRegistry()
    strategies_path = PROJECT_DIR / "strategies"
    
    for category in strategies_path.iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    strategies = list(registry.list_strategies())
    print(f"\n發現 {len(strategies)} 個策略:")
    for name, meta in strategies:
        print(f"   - {name} ({meta.category})")
    
    return strategies


def analyze_signal_quality(data, signals):
    """分析信號質量 - 看信號後的走勢"""
    print("\n" + "="*80)
    print("📊 信號質量分析")
    print("="*80)
    
    long_signals = [s for s in signals if s['signal'] == 'LONG']
    short_signals = [s for s in signals if s['signal'] == 'SHORT']
    
    def analyze_future_returns(signal_list, signal_type):
        """分析信號後的未來收益"""
        if not signal_list:
            return
        
        print(f"\n🔹 {signal_type} 信號分析 ({len(signal_list)} 個信號):")
        
        future_returns = []
        for s in signal_list:
            idx = data.index.get_loc(s['date'])
            # 看信號後 1, 5, 10, 20 天的收益
            for days in [1, 5, 10, 20]:
                if idx + days < len(data):
                    future_price = data['Close'].iloc[idx + days]
                    ret = (future_price - s['close']) / s['close'] * 100
                    future_returns.append({
                        'days': days,
                        'return': ret
                    })
        
        # 統計
        for days in [1, 5, 10, 20]:
            day_returns = [r['return'] for r in future_returns if r['days'] == days]
            if day_returns:
                avg_ret = np.mean(day_returns)
                win_rate = len([r for r in day_returns if r > 0]) / len(day_returns) * 100
                print(f"   {days}天後: 平均 {avg_ret:+.2f}% | 勝率 {win_rate:.1f}%")
    
    analyze_future_returns(long_signals, "LONG")
    analyze_future_returns(short_signals, "SHORT")


def debug_single_strategy(symbol, data, strategy_name, strategy_cls):
    """Debug 單一策略"""
    print("\n" + "="*80)
    print(f"🔬 策略測試: {strategy_name}")
    print("="*80)
    
    # 創建引擎
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.001,
        kelly_fraction=0.5
    )
    
    # 創建策略 (無參數)
    try:
        strategy = strategy_cls()
    except TypeError:
        # 嘗試常見參數
        try:
            strategy = strategy_cls(period=14)
        except:
            try:
                strategy = strategy_cls(short_period=12, long_period=26)
            except:
                strategy = strategy_cls()
    
    # 計算指標
    all_indicators = calculate_indicators(data)
    
    # 打印前 10 個信號
    print(f"\n📊 生成信號 (前20個):")
    signals = []
    for i in range(14, min(100, len(data))):  # 從第14天開始確保指標穩定
        try:
            # 準備指標數據
            ind = {}
            for ind_name, ind_values in all_indicators.items():
                ind[ind_name] = {}
                for key, series in ind_values.items():
                    if hasattr(series, 'iloc'):
                        ind[ind_name][key] = series.iloc[:i+1].reset_index(drop=True)
                    else:
                        ind[ind_name][key] = series
            
            signal = strategy.generate_signal(ind, data.iloc[:i+1])
            date = data.index[i]
            close_price = data['Close'].iloc[i]
            
            signals.append({
                'date': date,
                'signal': signal.signal,
                'confidence': signal.confidence,
                'close': close_price,
                'reason': signal.reason
            })
            
            if len(signals) <= 20:
                print(f"   {date.date()} | {signal.signal:>5} | {signal.confidence:.2f} | {signal.reason[:30]}")
                
        except Exception as e:
            print(f"   ✗ 錯誤 @ {data.index[i].date()}: {e}")
            continue
    
    # 信號統計
    if signals:
        long_signals = [s for s in signals if s['signal'] == 'LONG']
        short_signals = [s for s in signals if s['signal'] == 'SHORT']
        hold_signals = [s for s in signals if s['signal'] == 'HOLD']
        
        print(f"\n📈 信號統計:")
        print(f"   LONG:  {len(long_signals)}")
        print(f"   SHORT: {len(short_signals)}")
        print(f"   HOLD:  {len(hold_signals)}")
    
    # 分析信號質量
    analyze_signal_quality(data, signals)
    
    # 運行完整回測
    print(f"\n🚀 運行回測...")
    try:
        result = engine.run(symbol, strategy, data, strategy_name)
        
        print(f"\n📋 回測結果:")
        print(f"   總回報: {result.total_return:.2%}")
        print(f"   年化回報: {result.annualized_return:.2%}")
        print(f"   最大回撤: {result.max_drawdown:.2%}")
        print(f"   總交易次數: {result.total_trades}")
        print(f"   勝率: {result.win_rate:.2%}")
        print(f"   盈虧比: {result.profit_factor:.2f}")
        
        # 詳細交易記錄
        print(f"\n💰 交易記錄:")
        if hasattr(result, 'trades') and result.trades:
            for i, trade in enumerate(result.trades[:10]):
                print(f"   {i+1}. {trade}")
            if len(result.trades) > 10:
                print(f"   ... 共 {len(result.trades)} 筆交易")
        else:
            print(f"   ⚠️ 沒有交易記錄")
            
        return result, result.trades if hasattr(result, 'trades') else []
        
    except Exception as e:
        print(f"   ✗ 回測錯誤: {e}")
        import traceback
        traceback.print_exc()
        return None, []


def debug_trades(trades):
    """Debug 交易"""
    print("\n" + "="*80)
    print("💰 交易 Debug")
    print("="*80)
    
    if not trades:
        print("\n   ⚠️ 沒有交易記錄")
        return
    
    print(f"\n   總交易數: {len(trades)}")
    
    # 按類型分類（修復：使用正確的類型名稱）
    entries = [t for t in trades if 'ENTRY' in t.get('type', '')]
    exits = [t for t in trades if 'ENTRY' not in t.get('type', '') and 'pnl' in t]
    
    long_trades = [t for t in exits if t.get('type') == 'LONG']
    short_trades = [t for t in exits if t.get('type') == 'SHORT']
    
    print(f"   進場記錄: {len(entries)}")
    print(f"   平倉交易: {len(exits)}")
    print(f"   多頭平倉: {len(long_trades)}")
    print(f"   空頭平倉: {len(short_trades)}")
    
    # 打印前 5 筆平倉交易
    print(f"\n   前 5 筆平倉交易:")
    for i, t in enumerate(exits[:5]):
        pnl = t.get('net_pnl', 0)
        pnl_str = f"+${pnl:.2f}" if pnl > 0 else f"-${abs(pnl):.2f}"
        print(f"   {i+1}. {t['type']} | {t['entry_date']}→{t['exit_date']} | {pnl_str} | {t['return_pct']:.2f}%")
    
    # 計算交易統計
    if exits:
        profits = [t.get('net_pnl', 0) for t in exits]
        winning = [p for p in profits if p > 0]
        losing = [p for p in profits if p <= 0]
        
        print(f"\n   盈利交易: {len(winning)}")
        print(f"   虧損交易: {len(losing)}")
        if winning:
            print(f"   平均盈利: ${np.mean(winning):.2f}")
            print(f"   最大盈利: ${max(winning):.2f}")
        if losing:
            print(f"   平均虧損: ${np.mean(losing):.2f}")
            print(f"   最大虧損: ${min(losing):.2f}")


def main():
    print("="*80)
    print("🚀 TSLA 單股票回測 Debug")
    print("="*80)
    
    # 1. 載入數據
    data = load_tsla_data()
    
    # 2. Debug 指標
    indicators = debug_indicators(data)
    
    # 3. Debug 策略
    strategies = debug_strategies()
    
    # 4. 測試前 3 個策略
    registry = PluginRegistry()
    strategies_path = PROJECT_DIR / "strategies"
    for category in strategies_path.iterdir():
        if category.is_dir():
            registry.discover_plugins(str(category))
    
    test_strategies = ['MACDTrend', 'RSI_BB_Squeeze', 'Dual_Moving_Average_Crossover']
    
    for strategy_name in test_strategies:
        strategy_cls = registry.get_strategy(strategy_name)
        if strategy_cls:
            result, trades = debug_single_strategy("TSLA", data, strategy_name, strategy_cls)
            debug_trades(trades)
        else:
            print(f"\n⚠️ 找不到策略: {strategy_name}")
    
    print("\n" + "="*80)
    print("✅ Debug 完成")
    print("="*80)


if __name__ == "__main__":
    main()
