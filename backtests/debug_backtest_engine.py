#!/usr/bin/env python3
"""
回測引擎 Debug 腳本 - 排查異常數據
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


def debug_engine_step_by_step():
    """逐步調試回測引擎"""
    print("="*80)
    print("🚀 逐步調試回測引擎")
    print("="*80)
    
    # 載入 TSLA 數據
    data = load_data("TSLA").tail(500).copy()
    print(f"\n📊 數據: {len(data)} 天")
    print(f"   價格範圍: ${data['Close'].min():.2f} ~ ${data['Close'].max():.2f}")
    
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
    
    strategy = registry.get_strategy("MACDTrend")()
    
    # 計算指標
    all_indicators = calculate_indicators(data)
    
    # 手動執行回測邏輯，debug 每一步
    df = engine._prepare_data(data.copy())
    
    print(f"\n📋 準備數據:")
    print(f"   行數: {len(df)}")
    print(f"   日期範圍: {df.index[0]} ~ {df.index[-1]}")
    
    # 測試凱利計算
    print(f"\n🎯 測試凱利倉位計算...")
    capital = engine.initial_capital
    position = "none"
    entry_price = 0
    shares = 0
    trades = []
    equity = [engine.initial_capital]
    
    for i in range(len(df) - 1):
        current_price = df["Close"].iloc[i]
        current_date = df.index[i]
        
        # 準備指標
        ind = {}
        for ind_name, ind_values in all_indicators.items():
            ind[ind_name] = {}
            for key, series in ind_values.items():
                if hasattr(series, 'iloc'):
                    ind[ind_name][key] = series.iloc[:i+1].reset_index(drop=True)
                else:
                    ind[ind_name][key] = series
        
        signal = strategy.generate_signal(ind, df.iloc[:i+1])
        
        # 交易邏輯
        if signal.signal == "LONG" and position != "long":
            if position == "short":
                # 平倉 short
                exit_price = current_price * (1 - engine.slippage)
                pnl = (entry_price - exit_price) * shares
                trades.append({
                    "type": "SHORT",
                    "entry": entry_price,
                    "exit": exit_price,
                    "shares": shares,
                    "pnl": pnl
                })
                capital += pnl
            
            # 開倉 long
            kelly = 0.5  # 簡化
            position_capital = capital * kelly
            shares = int(position_capital / current_price)
            entry_price = current_price * (1 + engine.slippage)
            capital -= shares * entry_price
            position = "long"
            
            trades.append({
                "type": "LONG_ENTRY",
                "price": entry_price,
                "shares": shares
            })
        
        elif signal.signal == "SHORT" and position != "short":
            if position == "long":
                # 平倉 long
                exit_price = current_price * (1 - engine.slippage)
                pnl = (exit_price - entry_price) * shares
                trades.append({
                    "type": "LONG",
                    "entry": entry_price,
                    "exit": exit_price,
                    "shares": shares,
                    "pnl": pnl
                })
                capital += pnl
            
            # 開倉 short
            kelly = 0.5
            position_capital = capital * kelly
            shares = int(position_capital / current_price)
            entry_price = current_price * (1 - engine.slippage)
            capital += shares * entry_price
            position = "short"
            
            trades.append({
                "type": "SHORT_ENTRY",
                "price": entry_price,
                "shares": shares
            })
        
        # 更新權益
        if position == "long":
            equity.append(capital + shares * current_price)
        elif position == "short":
            unrealized_pnl = shares * (entry_price - current_price)
            equity.append(capital + unrealized_pnl)
        else:
            equity.append(capital)
        
        # Debug 前 10 筆權益變化
        if i < 10:
            print(f"   Day {i}: ${equity[-1]:.2f} | {position} | ${current_price:.2f}")
    
    print(f"\n📊 權益曲線分析:")
    print(f"   初始資金: ${equity[0]:.2f}")
    print(f"   最終資金: ${equity[-1]:.2f}")
    print(f"   最低點: ${min(equity):.2f}")
    print(f"   最高點: ${max(equity):.2f}")
    
    # 計算報酬率
    total_return = (equity[-1] - equity[0]) / equity[0]
    print(f"\n💰 總報酬: {total_return:.2%}")
    
    # 計算最大回撤
    equity_series = pd.Series(equity)
    rolling_max = equity_series.expanding().max()
    drawdown = (equity_series - rolling_max) / rolling_max
    max_drawdown = abs(drawdown.min())
    print(f"📉 最大回撤: {max_drawdown:.2%}")
    
    # Debug 交易
    print(f"\n💰 交易分析:")
    print(f"   總交易數: {len(trades)}")
    
    # 分類交易
    entries = [t for t in trades if 'ENTRY' in t.get('type', '')]
    exits = [t for t in trades if 'ENTRY' not in t.get('type', '')]
    
    print(f"   進場記錄: {len(entries)}")
    print(f"   平倉交易: {len(exits)}")
    
    # 計算勝率
    if exits:
        wins = [t for t in exits if t.get('pnl', 0) > 0]
        losses = [t for t in exits if t.get('pnl', 0) <= 0]
        print(f"   盈利: {len(wins)}")
        print(f"   虧損: {len(losses)}")
        win_rate = len(wins) / len(exits) if exits else 0
        print(f"   勝率: {win_rate:.2%}")
    
    # 檢查異常
    print(f"\n🔍 異常檢查:")
    if total_return < -100:
        print(f"   ⚠️ 報酬率異常: {total_return:.2%}")
    if max_drawdown > 100:
        print(f"   ⚠️ 最大回撤異常: {max_drawdown:.2%}")
    if any(e < 0 for e in equity):
        print(f"   ⚠️ 權益出現負值!")
        negative_days = [i for i, e in enumerate(equity) if e < 0]
        print(f"   負值天數: {negative_days[:5]}")
    
    # 打印前 5 筆和後 5 筆交易
    print(f"\n📝 前 5 筆交易:")
    for i, t in enumerate(trades[:5]):
        print(f"   {i+1}. {t}")
    
    print(f"\n📝 後 5 筆交易:")
    for i, t in enumerate(trades[-5:]):
        print(f"   {len(trades)-4+i}. {t}")


def debug_calculate_result():
    """調試 _calculate_result 函數"""
    print("\n" + "="*80)
    print("🔧 調試 _calculate_result 函數")
    print("="*80)
    
    # 模擬權益曲線
    initial_capital = 100000
    
    # 正常情況
    equity_normal = [100000, 105000, 103000, 108000, 110000]
    
    # 異常情況 1: 權益歸零
    equity_zero = [100000, 50000, 0, 0, 0]
    
    # 異常情況 2: 權益為負
    equity_negative = [100000, 50000, -10000, -50000, -100000]
    
    def calculate(equity_list, name):
        print(f"\n📊 {name}:")
        equity_series = pd.Series(equity_list)
        
        total_return = (equity_list[-1] - equity_list[0]) / equity_list[0]
        print(f"   總報酬: {total_return:.2%}")
        
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_dd = abs(drawdown.min())
        print(f"   最大回撤: {max_dd:.2%}")
        
        # 檢查問題
        if equity_list[-1] < 0:
            print(f"   ⚠️ 最終權益為負: {equity_list[-1]}")
        if total_return < -100:
            print(f"   ⚠️ 報酬率低於 -100%")
    
    calculate(equity_normal, "正常情況")
    calculate(equity_zero, "權益歸零")
    calculate(equity_negative, "權益為負")


def debug_trade_pnl():
    """調試交易 PnL 計算"""
    print("\n" + "="*80)
    print("💰 調試交易 PnL 計算")
    print("="*80)
    
    # 模擬交易
    trades = [
        {"type": "LONG", "entry": 100, "exit": 110, "shares": 100, "pnl": 1000},
        {"type": "LONG", "entry": 110, "exit": 105, "shares": 100, "pnl": -500},
        {"type": "SHORT", "entry": 105, "exit": 100, "shares": 100, "pnl": 500},
    ]
    
    print(f"\n📝 交易列表:")
    for i, t in enumerate(trades):
        print(f"   {i+1}. {t}")
    
    # 計算勝率
    wins = [t for t in trades if t.get('pnl', 0) > 0]
    losses = [t for t in trades if t.get('pnl', 0) <= 0]
    
    win_rate = len(wins) / len(trades) if trades else 0
    print(f"\n📊 勝率: {win_rate:.2%}")
    
    # 計算盈虧比
    avg_win = np.mean([t['pnl'] for t in wins]) if wins else 0
    avg_loss = abs(np.mean([t['pnl'] for t in losses])) if losses else 0
    
    profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')
    print(f"   平均盈利: ${avg_win:.2f}")
    print(f"   平均虧損: ${avg_loss:.2f}")
    print(f"   盈虧比: {profit_factor:.2f}")


def main():
    print("="*80)
    print("🐛 回測引擎 Debug - 排查異常數據")
    print("="*80)
    
    debug_engine_step_by_step()
    debug_calculate_result()
    debug_trade_pnl()
    
    print("\n" + "="*80)
    print("✅ Debug 完成")
    print("="*80)


if __name__ == "__main__":
    main()
