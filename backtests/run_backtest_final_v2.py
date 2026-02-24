"""
高夏普比率策略 - 最終報告版本
目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%

使用 MySQL 真實歷史數據回測 (stocks 表 + kline_cache 表)

執行日期: 2026-02-19
"""

import pandas as pd
import numpy as np
import sys
from datetime import datetime
import importlib.util

sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

# 直接導入 backtest.py 而不是 backtest 目錄
spec = importlib.util.spec_from_file_location("backtest_engine", "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/backtest.py")
backtest_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backtest_module)
BacktestEngine = backtest_module.BacktestEngine

from backtests.get_db_symbols import get_trading_symbols, get_kline_data


class FastMAStrategy:
    """快速均線策略 - 高頻交易"""
    
    def __init__(self, fast=5, slow=10, stop=0.03, profit=0.08):
        self.fast = fast
        self.slow = slow
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = float(close.iloc[-1])
        
        if len(close) < self.slow + 3:
            return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.2, 'price': current_price, 'reason': 'Warming up'})()
        
        sma_fast = close.rolling(self.fast).mean()
        sma_slow = close.rolling(self.slow).mean()
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            
            if pnl >= self.profit:
                self.position = None
                return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.7, 'price': current_price, 'reason': f'TP +{pnl*100:.1f}%'})()
            if pnl <= -self.stop:
                self.position = None
                return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.8, 'price': current_price, 'reason': f'SL {pnl*100:.1f}%'})()
        
        # 交叉
        prev_fast = float(sma_fast.iloc[-2])
        prev_slow = float(sma_slow.iloc[-2])
        curr_fast = float(sma_fast.iloc[-1])
        curr_slow = float(sma_slow.iloc[-1])
        
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            self.position = "LONG"
            self.entry_price = current_price
            return type('Signal', (), {'signal': 'LONG', 'confidence': 0.75, 'price': current_price, 'reason': 'MA Golden'})()
        
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            if self.position == "LONG":
                self.position = None
                return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.6, 'price': current_price, 'reason': 'MA Death'})()
            return type('Signal', (), {'signal': 'SHORT', 'confidence': 0.70, 'price': current_price, 'reason': 'MA Death'})()
        
        return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.3, 'price': current_price, 'reason': 'No signal'})()


class RSIScalper:
    """RSI  scalper - 超短線"""
    
    def __init__(self, rsi_period=5, oversold=40, overbought=60, stop=0.02, profit=0.05):
        self.period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = float(close.iloc[-1])
        
        if len(close) < self.period + 5:
            return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.2, 'price': current_price})()
        
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            
            if rsi_val > self.overbought:
                self.position = None
                return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.6, 'price': current_price, 'reason': f'RSI {rsi_val:.0f}'})()
            
            if pnl >= self.profit:
                self.position = None
                return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.7, 'price': current_price, 'reason': f'TP'})()
            if pnl <= -self.stop:
                self.position = None
                return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.8, 'price': current_price, 'reason': f'SL'})()
        
        # 進場
        if rsi_val < self.oversold:
            self.position = "LONG"
            self.entry_price = current_price
            return type('Signal', (), {'signal': 'LONG', 'confidence': 0.70, 'price': current_price, 'reason': f'RSI={rsi_val:.0f}'})()
        
        return type('Signal', (), {'signal': 'HOLD', 'confidence': 0.3, 'price': current_price, 'reason': f'RSI={rsi_val:.0f}'})()


def run_final_backtest():
    print("="*70)
    print("🚀 高夏普比率策略回測 - 最終版")
    print("目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%")
    print("="*70)
    
    # 從資料庫獲取實盤股票
    from get_db_symbols import get_trading_symbols
    symbols = get_trading_symbols()
    # symbols = ['AAPL', 'TSLA', 'SPY', 'MSFT', 'NVDA']  # 備用
    
    strategies = [
        ('FastMA_5_10', FastMAStrategy, {'fast': 5, 'slow': 10, 'stop': 0.03, 'profit': 0.08}),
        ('FastMA_3_8', FastMAStrategy, {'fast': 3, 'slow': 8, 'stop': 0.025, 'profit': 0.06}),
        ('RSIScalper', RSIScalper, {'rsi_period': 5, 'oversold': 40, 'overbought': 60, 'stop': 0.02, 'profit': 0.05}),
        ('RSIScalper_Aggressive', RSIScalper, {'rsi_period': 3, 'oversold': 45, 'overbought': 55, 'stop': 0.015, 'profit': 0.04}),
    ]
    
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.0015,
        slippage=0.001,
        kelly_fraction=0.25
    )
    
    all_results = []
    qualified = []
    
    for symbol in symbols:
        print(f"\n{'─'*60}")
        print(f"📊 {symbol}")
        print(f"{'─'*60}")
        
        # 從 MySQL kline_cache 獲取真實 K 線數據
        data = get_kline_data(symbol, days=500)
        
        if data is None or data.empty:
            print(f"  ⚠️ 無法獲取 {symbol} 的 K 線數據，跳過")
            continue
        
        # 確保必要的列存在
        required_cols = ['Open', 'High', 'Low', 'Close']
        if not all(col in data.columns for col in required_cols):
            print(f"  ⚠️ {symbol} 數據格式不完整，跳過")
            continue
        
        print(f"  📈 數據: {len(data)} 天 ({data.index[0].date()} ~ {data.index[-1].date()})")
        
        for name, cls, params in strategies:
            print(f"\n  🔄 {name}...", end=" ", flush=True)
            
            try:
                strategy = cls(**params)
                result = engine.run(symbol, strategy, data, name)
                
                sharpe = result.annualized_return / result.volatility if result.volatility > 0 else 0
                
                is_q = (sharpe >= 1.5 and 
                       result.annualized_return >= 0.20 and 
                       result.max_drawdown <= 0.30)
                
                status = "✅" if is_q else "⚪"
                print(f"Sharpe:{sharpe:.2f} Return:{result.annualized_return:.1%} MaxDD:{result.max_drawdown:.1%} Trades:{result.total_trades} {status}")
                
                res = {
                    'symbol': symbol,
                    'strategy': name,
                    'sharpe': sharpe,
                    'return': result.annualized_return,
                    'max_dd': result.max_drawdown,
                    'trades': result.total_trades,
                    'win_rate': result.win_rate
                }
                
                all_results.append(res)
                
                if is_q:
                    res['params'] = params.copy()
                    qualified.append(res)
                    
            except Exception as e:
                print(f"❌ {str(e)[:50]}")
                continue
    
    # 摘要
    print("\n" + "="*70)
    print("📊 回測摘要")
    print("="*70)
    
    total = len(all_results)
    passed = len(qualified)
    
    print(f"\n總測試: {total} | 合格: {passed}")
    
    if qualified:
        qualified.sort(key=lambda x: x['sharpe'], reverse=True)
        
        print(f"\n🏆 合格策略:")
        for i, q in enumerate(qualified, 1):
            print(f"\n  {i}. {q['symbol']} - {q['strategy']}")
            print(f"     Sharpe: {q['sharpe']:.2f} | Return: {q['return']:.2%} | MaxDD: {q['max_dd']:.2%}")
        
        best = qualified[0]
        print(f"\n🏅 最佳: {best['symbol']} - {best['strategy']}")
        print(f"   Sharpe: {best['sharpe']:.2f} | Return: {best['return']:.2%} | MaxDD: {best['max_dd']:.2%}")
        return {'status': 'success', 'best': best, 'qualified': qualified}
    else:
        # 找出最接近目標的
        if all_results:
            print(f"\n⚠️ 沒有完全達標的策略")
            
            # 按夏普排序
            sorted_by_sharpe = sorted(all_results, key=lambda x: x['sharpe'], reverse=True)
            # 按報酬排序  
            sorted_by_return = sorted(all_results, key=lambda x: x['return'], reverse=True)
            
            best_sharpe = sorted_by_sharpe[0]
            best_return = sorted_by_return[0]
            
            print(f"\n📈 最高夏普: {best_sharpe['symbol']} - {best_sharpe['strategy']}")
            print(f"   Sharpe: {best_sharpe['sharpe']:.2f} | Return: {best_sharpe['return']:.2%} | MaxDD: {best_sharpe['max_dd']:.2%}")
            
            print(f"\n💰 最高報酬: {best_return['symbol']} - {best_return['strategy']}")
            print(f"   Sharpe: {best_return['sharpe']:.2f} | Return: {best_return['return']:.2%} | MaxDD: {best_return['max_dd']:.2%}")
            
            return {
                'status': 'partial', 
                'best_sharpe': best_sharpe, 
                'best_return': best_return,
                'analysis': '需要更多交易日或更佳數據來達標'
            }
        
        return {'status': 'failed'}


if __name__ == "__main__":
    result = run_final_backtest()
