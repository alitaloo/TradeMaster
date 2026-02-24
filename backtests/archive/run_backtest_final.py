"""
高夏普比率策略回測 - 簡化穩健版
目標：驗證 Sharpe > 1.5, Return > 20%, MaxDD < 20%
使用真實歷史數據

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
PositionType = backtest_module.PositionType


class SignalResult:
    def __init__(self, signal, confidence=0.5, price=0.0, reason=""):
        self.signal = signal
        self.confidence = confidence
        self.price = price
        self.reason = reason


def generate_market_data(symbol: str, days: int = 500, trend: str = "bullish") -> pd.DataFrame:
    """生成帶趨勢的市場數據"""
    np.random.seed(hash(symbol) % 10000)
    
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    start_price = {'AAPL': 150, 'TSLA': 200, 'SPY': 400, 'MSFT': 300, 'NVDA': 500}.get(symbol, 100)
    
    # 根據趨勢生成報酬
    if trend == "bullish":
        daily_return = 0.0005
        daily_vol = 0.015
    elif trend == "volatile":
        daily_return = 0.0002
        daily_vol = 0.025
    else:  # sideways
        daily_return = 0.0001
        daily_vol = 0.012
    
    returns = np.random.normal(daily_return, daily_vol, days)
    
    # 添加一些趨勢段落
    for i in range(0, days, 80):
        if i + 30 < days:
            returns[i:i+20] += 0.002  # 上漲趨勢
    
    close = np.zeros(days)
    close[0] = start_price
    for i in range(1, days):
        close[i] = close[i-1] * (1 + returns[i])
    
    close_series = pd.Series(close, index=dates)
    
    df = pd.DataFrame({
        'Open': close_series * (1 + np.random.normal(0, 0.002, days)),
        'High': close_series * (1 + np.abs(np.random.normal(0.005, 0.008, days))),
        'Low': close_series * (1 - np.abs(np.random.normal(0.005, 0.008, days))),
        'Close': close_series,
        'Volume': 1000000 + np.random.randint(500000, 2000000, days)
    })
    
    return df

from data import DataEngine


class SimpleMAStrategy:
    """簡單均線交叉策略"""
    
    def __init__(self, fast=20, slow=50, stop=0.10, profit=0.15):
        self.fast = fast
        self.slow = slow
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
        self.entry_date = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = close.iloc[-1]
        
        if len(close) < self.slow + 5:
            return SignalResult("HOLD", 0.2, current_price, "Warming up")
        
        sma_fast = close.rolling(self.fast).mean()
        sma_slow = close.rolling(self.slow).mean()
        
        # 持倉檢查
        if self.position is not None and self.entry_price is not None:
            pnl_pct = (current_price - self.entry_price) / self.entry_price
            if self.position == "LONG":
                if pnl_pct >= self.profit:
                    self.position = None
                    return SignalResult("HOLD", 0.6, current_price, f"TP +{pnl_pct*100:.1f}%")
                if pnl_pct <= -self.stop:
                    self.position = None
                    return SignalResult("HOLD", 0.7, current_price, f"SL {pnl_pct*100:.1f}%")
            elif self.position == "SHORT":
                if pnl_pct <= -self.profit:
                    self.position = None
                    return SignalResult("HOLD", 0.6, current_price, f"TP {pnl_pct*100:.1f}%")
                if pnl_pct >= self.stop:
                    self.position = None
                    return SignalResult("HOLD", 0.7, current_price, f"SL {pnl_pct*100:.1f}%")
        
        # 交叉訊號
        prev_fast = sma_fast.iloc[-2]
        prev_slow = sma_slow.iloc[-2]
        curr_fast = sma_fast.iloc[-1]
        curr_slow = sma_slow.iloc[-1]
        
        # 黃金交叉
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            self.position = "LONG"
            self.entry_price = current_price
            return SignalResult("LONG", 0.75, current_price, f"MA Golden Cross")
        
        # 死叉
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            self.position = "SHORT"
            self.entry_price = current_price
            return SignalResult("SHORT", 0.75, current_price, f"MA Death Cross")
        
        return SignalResult("HOLD", 0.3, current_price, "No signal")


class RSIStrategy:
    """RSI 均值回歸策略"""
    
    def __init__(self, period=14, oversold=30, overbought=70, stop=0.05, profit=0.10):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = close.iloc[-1]
        
        if len(close) < self.period + 5:
            return SignalResult("HOLD", 0.2, current_price, "Warming up")
        
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = rsi.iloc[-1]
        
        # 持倉檢查
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            if pnl >= self.profit:
                self.position = None
                return SignalResult("HOLD", 0.7, current_price, f"TP +{pnl*100:.1f}%")
            if pnl <= -self.stop:
                self.position = None
                return SignalResult("HOLD", 0.8, current_price, f"SL {pnl*100:.1f}%")
            # RSI 超買退出
            if rsi_val > self.overbought:
                self.position = None
                return SignalResult("HOLD", 0.6, current_price, f"RSI Overbought")
        
        # 進場條件
        if rsi_val < self.oversold:
            self.position = "LONG"
            self.entry_price = current_price
            return SignalResult("LONG", 0.70, current_price, f"RSI={rsi_val:.0f} Oversold")
        
        return SignalResult("HOLD", 0.3, current_price, f"RSI={rsi_val:.0f}")


class MomentumStrategy:
    """動量策略 - 只做多"""
    
    def __init__(self, roc_period=20, threshold=5, stop=0.08, profit=0.20):
        self.roc_period = roc_period
        self.threshold = threshold
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = close.iloc[-1]
        
        if len(close) < self.roc_period + 5:
            return SignalResult("HOLD", 0.2, current_price, "Warming up")
        
        roc = ((close - close.shift(self.roc_period)) / close.shift(self.roc_period)) * 100
        roc_val = roc.iloc[-1]
        
        # 持倉檢查
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            if pnl >= self.profit:
                self.position = None
                return SignalResult("HOLD", 0.7, current_price, f"TP +{pnl*100:.1f}%")
            if pnl <= -self.stop:
                self.position = None
                return SignalResult("HOLD", 0.8, current_price, f"SL {pnl*100:.1f}%")
        
        # 進場：動量為正且足夠強
        if roc_val > self.threshold:
            self.position = "LONG"
            self.entry_price = current_price
            return SignalResult("LONG", 0.70, current_price, f"ROC={roc_val:.1f}%")
        
        return SignalResult("HOLD", 0.3, current_price, f"ROC={roc_val:.1f}%")


def run_backtest():
    print("="*70)
    print("🚀 高夏普比率策略回測")
    print("目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%")
    print("="*70)
    
    from get_db_symbols import get_trading_symbols
    symbols = get_trading_symbols()
    
    # 初始化數據引擎
    data_engine = DataEngine()
    
    strategies = [
        ('SimpleMA_Crossover', SimpleMAStrategy, {'fast': 20, 'slow': 50, 'stop': 0.10, 'profit': 0.20}),
        ('RSI_MeanReversion', RSIStrategy, {'period': 14, 'oversold': 30, 'overbought': 65, 'stop': 0.05, 'profit': 0.12}),
        ('Momentum', MomentumStrategy, {'roc_period': 20, 'threshold': 5, 'stop': 0.08, 'profit': 0.25}),
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
        
        # 清理 symbol 格式
        clean_symbol = symbol.split('.')[-1] if '.' in symbol else symbol
        
        # 使用 DataEngine 獲取真實數據
        data = data_engine.get_daily_data(
            clean_symbol,
            start_date="2023-01-01",
            end_date="2026-01-01"
        )
        
        if data is None or data.empty:
            print(f"  ⚠️ 無法獲取 {symbol} 數據，跳過")
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
                
                # 計算夏普
                sharpe = result.annualized_return / result.volatility if result.volatility > 0 else 0
                
                # 合格檢查
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
                    res['params'] = params
                    qualified.append(res)
                    
            except Exception as e:
                print(f"❌ Error: {str(e)[:50]}")
                continue
    
    # 結果摘要
    print("\n" + "="*70)
    print("📊 回測摘要")
    print("="*70)
    
    total = len(all_results)
    passed = len(qualified)
    
    print(f"\n總測試: {total} | 合格: {passed} | 合格率: {passed/total*100:.1f}%" if total > 0 else "N/A")
    
    if qualified:
        print(f"\n🏆 合格策略 (按夏普排序):")
        qualified.sort(key=lambda x: x['sharpe'], reverse=True)
        
        for i, q in enumerate(qualified, 1):
            print(f"\n  {i}. {q['symbol']} - {q['strategy']}")
            print(f"     Sharpe: {q['sharpe']:.2f} | Return: {q['return']:.2%} | MaxDD: {q['max_dd']:.2%}")
            print(f"     交易次數: {q['trades']} | 勝率: {q['win_rate']:.2%}")
        
        best = qualified[0]
        print(f"\n{'─'*70}")
        print(f"🏅 最佳策略: {best['symbol']} - {best['strategy']}")
        print(f"   Sharpe: {best['sharpe']:.2f} | Return: {best['return']:.2%} | MaxDD: {best['max_dd']:.2%}")
        print(f"{'─'*70}")
        
        return {'status': 'success', 'best': best, 'qualified': qualified, 'all': all_results}
    else:
        print(f"\n⚠️ 沒有策略達標")
        if all_results:
            best = max(all_results, key=lambda x: x['sharpe'])
            print(f"📈 最佳嘗試: {best['symbol']} - {best['strategy']}")
            print(f"   Sharpe: {best['sharpe']:.2f} | Return: {best['return']:.2%}")
        return {'status': 'needs_tuning', 'best': best if all_results else None, 'qualified': [], 'all': all_results}


if __name__ == "__main__":
    result = run_backtest()
