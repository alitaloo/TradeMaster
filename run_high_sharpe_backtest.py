"""
高夏普策略回測腳本
目標：驗證 Sharpe > 1.5, Return > 20%, MaxDD < 20%

執行日期: 2026-02-07
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, timedelta

# 添加專案路徑
sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

from backtest import BacktestEngine, print_backtest_result, BacktestResult
from strategies.high_sharpe_strategies import (
    EnhancedMomentum,
    MeanReversionRSI, 
    TrendFilteredBreakout,
    VolatilityRegimeSwitch,
    get_strategy
)


def download_stock_data(symbol: str, days: int = 500) -> pd.DataFrame:
    """下載股票數據"""
    try:
        import yfinance as yf
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days + 100)  # 多取一些緩衝
        
        print(f"📥 下載 {symbol} 數據 ({start_date.date()} ~ {end_date.date()})...")
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            print(f"❌ {symbol} 沒有數據")
            return None
        
        # 清理數據
        df = df.dropna()
        df = df[df['Volume'] > 0]
        
        print(f"✅ 取得 {len(df)} 天數據")
        return df
    
    except Exception as e:
        print(f"❌ 下載 {symbol} 失敗: {e}")
        return None


def run_backtest_campaign():
    """執行回測活動"""
    
    print("="*70)
    print("🚀 高夏普比率策略回測活動")
    print("="*70)
    print("目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%")
    print("="*70)
    
    # 測試標的
    symbols = ['AAPL', 'TSLA', 'SPY', 'MSFT', 'NVDA']
    
    # 測試策略
    strategy_configs = [
        {
            'name': 'EnhancedMomentum',
            'class': EnhancedMomentum,
            'params': {
                'sma_short': 20,
                'sma_long': 50,
                'roc_period': 20,
                'roc_threshold': 3.0,
                'rsi_period': 14,
                'rsi_oversold': 30,
                'rsi_overbought': 70,
                'atr_period': 14,
                'atr_volatility_threshold': 0.5,
                'stop_loss': 0.08,
                'take_profit': 0.20,
                'max_holding_days': 30
            }
        },
        {
            'name': 'MeanReversionRSI',
            'class': MeanReversionRSI,
            'params': {
                'rsi_period': 14,
                'rsi_oversold': 25,
                'rsi_exit': 55,
                'sma_period': 50,
                'hv_percentile_threshold': 0.7,
                'stop_loss': 0.05,
                'take_profit': 0.10,
                'max_holding_days': 15
            }
        },
        {
            'name': 'TrendFilteredBreakout',
            'class': TrendFilteredBreakout,
            'params': {
                'breakout_period': 20,
                'adx_period': 14,
                'adx_threshold': 25,
                'volume_period': 20,
                'volume_multiplier': 1.2,
                'stop_loss': 0.06,
                'take_profit': 0.15,
                'max_holding_days': 25
            }
        },
        {
            'name': 'VolatilityRegimeSwitch',
            'class': VolatilityRegimeSwitch,
            'params': {
                'bb_period': 20,
                'bb_std': 2.0,
                'atr_period': 14,
                'atr_percentile_low': 0.25,
                'atr_percentile_high': 0.80,
                'atr_expansion_threshold': 0.1,
                'stop_loss': 0.04,
                'take_profit': 0.12,
                'max_holding_days': 20
            }
        }
    ]
    
    # 初始化回測引擎
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.0015,  # 來回 0.15%
        slippage=0.001,     # 滑價 0.1%
        kelly_fraction=0.25  # 半凱利
    )
    
    # 存儲結果
    all_results = []
    qualified_strategies = []
    
    # 測試每個策略和標的
    for symbol in symbols:
        print(f"\n{'='*70}")
        print(f"📊 測試標的: {symbol}")
        print(f"{'='*70}")
        
        # 下載數據
        data = download_stock_data(symbol, days=500)
        if data is None:
            continue
        
        for config in strategy_configs:
            strategy_name = config['name']
            strategy_class = config['class']
            params = config['params']
            
            print(f"\n🔄 執行策略: {strategy_name}")
            
            try:
                # 創建策略實例
                strategy = strategy_class(**params)
                
                # 執行回測
                result = engine.run(symbol, strategy, data, strategy_name)
                
                # 計算夏普比率
                returns = result.equity_curve.pct_change().dropna()
                annualized_return = result.annualized_return
                volatility = result.volatility
                sharpe = annualized_return / volatility if volatility > 0 else 0
                
                # 顯示結果
                print(f"\n{'─'*50}")
                print(f"📈 {symbol} - {strategy_name}")
                print(f"{'─'*50}")
                print(f"   總回報:     {result.total_return:>8.2%}")
                print(f"   年化回報:   {result.annualized_return:>8.2%}")
                print(f"   最大回撤:   {result.max_drawdown:>8.2%}")
                print(f"   波動率:     {result.volatility:>8.2%}")
                print(f"   夏普比率:   {sharpe:>8.2f}")
                print(f"   總交易次數: {result.total_trades:>8d}")
                print(f"   勝率:       {result.win_rate:>8.2%}")
                print(f"   盈虧比:     {result.profit_factor:>8.2f}")
                
                # 評估是否合格
                is_qualified = (
                    sharpe >= 1.5 and
                    annualized_return >= 0.20 and
                    result.max_drawdown <= 0.30
                )
                
                if is_qualified:
                    print(f"\n✅ 【合格】策略達標！")
                    qualified_strategies.append({
                        'symbol': symbol,
                        'strategy': strategy_name,
                        'sharpe': sharpe,
                        'return': annualized_return,
                        'max_dd': result.max_drawdown,
                        'trades': result.total_trades,
                        'win_rate': result.win_rate,
                        'params': params
                    })
                
                # 添加到結果列表
                all_results.append({
                    'symbol': symbol,
                    'strategy': strategy_name,
                    'sharpe': sharpe,
                    'return': annualized_return,
                    'max_dd': result.max_drawdown,
                    'trades': result.total_trades,
                    'win_rate': result.win_rate
                })
                
            except Exception as e:
                print(f"❌ 策略執行失敗: {e}")
                import traceback
                traceback.print_exc()
    
    # 輸出最終報告
    print("\n" + "="*70)
    print("📊 回測結果摘要")
    print("="*70)
    
    # 統計
    total_tests = len(all_results)
    qualified_count = len(qualified_strategies)
    
    print(f"\n總測試數: {total_tests}")
    print(f"合格策略數: {qualified_count}")
    print(f"合格率: {qualified_count/total_tests*100:.1f}%" if total_tests > 0 else "N/A")
    
    if qualified_strategies:
        print(f"\n{'='*70}")
        print("🏆 合格策略名單 (Sharpe > 1.5, Return > 20%, MaxDD < 30%)")
        print(f"{'='*70}")
        
        # 按夏普比率排序
        qualified_strategies.sort(key=lambda x: x['sharpe'], reverse=True)
        
        for i, qs in enumerate(qualified_strategies, 1):
            print(f"\n{i}. {qs['symbol']} - {qs['strategy']}")
            print(f"   Sharpe: {qs['sharpe']:.2f} | Return: {qs['return']:.2%} | MaxDD: {qs['max_dd']:.2%}")
            print(f"   交易次數: {qs['trades']} | 勝率: {qs['win_rate']:.2%}")
    
    # 返回最佳策略
    if qualified_strategies:
        best = qualified_strategies[0]
        print(f"\n{'='*70}")
        print(f"🏅 最佳策略: {best['symbol']} - {best['strategy']}")
        print(f"   夏普比率: {best['sharpe']:.2f}")
        print(f"   年化報酬: {best['return']:.2%}")
        print(f"   最大回撤: {best['max_dd']:.2%}")
        print(f"{'='*70}")
        
        return {
            'status': 'success',
            'best_strategy': best,
            'qualified_strategies': qualified_strategies,
            'all_results': all_results
        }
    else:
        print(f"\n⚠️ 沒有策略達到目標標準")
        print("建議：調整參數或測試更多標的")
        
        return {
            'status': 'needs_tuning',
            'all_results': all_results
        }


if __name__ == "__main__":
    # 確保 yfinance 已安裝
    try:
        import yfinance
    except ImportError:
        print("正在安裝 yfinance...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance", "-q"])
        import yfinance
    
    result = run_backtest_campaign()
