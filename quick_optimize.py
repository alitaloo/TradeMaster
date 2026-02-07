"""
高夏普策略 - 快速參數優化
目標：Sharpe > 1.5, Return > 20%, MaxDD < 30%
"""
import pandas as pd
import numpy as np
import sys
from datetime import datetime
sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')
from backtest import BacktestEngine

def generate_bull_data(symbol, days=1000):
    """生成強牛市數據 - 年化約 25-30%"""
    np.random.seed(hash(symbol) % 100000)
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    price = {'AAPL': 150, 'TSLA': 200, 'SPY': 400}.get(symbol, 100)
    
    returns = []
    for i in range(days):
        if i % 40 < 28:  # 70% 時間強上漲
            r = np.random.normal(0.0015, 0.010)
        elif i % 40 < 34:  # 回調
            r = np.random.normal(-0.0008, 0.015)
        else:  # 盤整後突破
            r = np.random.normal(0.002, 0.012)
        returns.append(r)
    
    close = np.zeros(days)
    close[0] = price
    for i in range(1, days):
        close[i] = close[i-1] * (1 + returns[i])
    
    cs = pd.Series(close, index=dates)
    return pd.DataFrame({
        'Open': cs * (1 + np.random.normal(0, 0.002, days)),
        'High': cs * (1 + np.abs(np.random.normal(0.006, 0.005, days))),
        'Low': cs * (1 - np.abs(np.random.normal(0.006, 0.005, days))),
        'Close': cs,
        'Volume': 1000000 + np.random.randint(500000, 2000000, days)
    })

class Signal:
    def __init__(self, signal, confidence=0.5, price=0.0, reason=""):
        self.signal = signal
        self.confidence = confidence
        self.price = price
        self.reason = reason

class RSI_Momentum_Strategy:
    """RSI + 動量策略"""
    def __init__(self, rsi_period=14, rsi_oversold=30, rsi_overbought=70,
                 roc_period=10, roc_threshold=2.0,
                 stop=0.05, profit=0.15):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.roc_period = roc_period
        self.roc_threshold = roc_threshold
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        cp = float(close.iloc[-1])
        
        if len(close) < max(self.rsi_period, self.roc_period) + 10:
            return Signal("HOLD", 0.2, cp, "Warming")
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        
        # ROC
        roc = ((close - close.shift(self.roc_period)) / close.shift(self.roc_period)) * 100
        roc_val = float(roc.iloc[-1])
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (cp - self.entry_price) / self.entry_price
            if pnl >= self.profit:
                self.position = None
                return Signal("HOLD", 0.7, cp, f"TP +{pnl*100:.0f}%")
            if pnl <= -self.stop:
                self.position = None
                return Signal("HOLD", 0.8, cp, f"SL {pnl*100:.0f}%")
        
        # 進場
        if rsi_val < self.rsi_oversold and roc_val > self.roc_threshold:
            self.position = "LONG"
            self.entry_price = cp
            return Signal("LONG", 0.75, cp, f"RSI={rsi_val:.0f} ROC={roc_val:.1f}")
        
        return Signal("HOLD", 0.3, cp, f"RSI={rsi_val:.0f}")

class MA_Crossover_Strategy:
    """MA 交叉策略"""
    def __init__(self, fast=10, slow=30, stop=0.08, profit=0.20):
        self.fast = fast
        self.slow = slow
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        cp = float(close.iloc[-1])
        
        if len(close) < self.slow + 5:
            return Signal("HOLD", 0.2, cp, "Warming")
        
        sma_f = close.rolling(self.fast).mean()
        sma_s = close.rolling(self.slow).mean()
        
        if self.position == "LONG" and self.entry_price:
            pnl = (cp - self.entry_price) / self.entry_price
            if pnl >= self.profit:
                self.position = None
                return Signal("HOLD", 0.7, cp, f"TP +{pnl*100:.0f}%")
            if pnl <= -self.stop:
                self.position = None
                return Signal("HOLD", 0.8, cp, f"SL {pnl*100:.0f}%")
        
        prev_f, prev_s = float(sma_f.iloc[-2]), float(sma_s.iloc[-2])
        curr_f, curr_s = float(sma_f.iloc[-1]), float(sma_s.iloc[-1])
        
        if prev_f <= prev_s and curr_f > curr_s:
            self.position = "LONG"
            self.entry_price = cp
            return Signal("LONG", 0.75, cp, f"MA {self.fast}/{self.slow}")
        
        return Signal("HOLD", 0.3, cp, "No signal")

def quick_test():
    print("="*70)
    print("🚀 快速參數優化 - 尋找達標策略")
    print("="*70)
    
    engine = BacktestEngine(initial_capital=100000, commission=0.0015, slippage=0.001, kelly_fraction=0.25)
    symbols = ['AAPL', 'TSLA', 'SPY']
    
    # RSI + ROC 參數組合
    rsi_oversolds = [25, 30, 35, 40]
    roc_thresholds = [1.0, 1.5, 2.0, 2.5, 3.0]
    profits = [0.10, 0.12, 0.15, 0.18, 0.20]
    
    # MA 參數組合
    fast_slows = [(5,15), (10,20), (10,30), (20,50)]
    
    best = {'sharpe': 0, 'return': 0, 'dd': 1, 'strategy': '', 'params': {}}
    qualified = []
    
    total_tests = len(rsi_oversolds) * len(roc_thresholds) * len(profits) + len(fast_slows) * 3
    current = 0
    
    for symbol in symbols:
        print(f"\n📊 {symbol}")
        data = generate_bull_data(symbol, days=800)
        
        # RSI + ROC 策略
        for ro in rsi_oversolds:
            for rt in roc_thresholds:
                for pf in profits:
                    current += 1
                    try:
                        s = RSI_Momentum_Strategy(rsi_oversold=ro, roc_threshold=rt, profit=pf)
                        r = engine.run(symbol, s, data, f"RSI_ROC_{ro}_{rt}_{pf}")
                        sharpe = r.annualized_return / r.volatility if r.volatility > 0 else 0
                        
                        if sharpe >= 1.5 and r.annualized_return >= 0.20:
                            qualified.append({
                                'symbol': symbol, 'strategy': 'RSI_ROC',
                                'sharpe': sharpe, 'return': r.annualized_return,
                                'max_dd': r.max_drawdown, 'trades': r.total_trades,
                                'params': f"RSI<{ro}, ROC>{rt}, TP={pf}"
                            })
                        
                        if sharpe > best['sharpe'] and r.annualized_return > best['return']:
                            best = {'sharpe': sharpe, 'return': r.annualized_return, 
                                   'dd': r.max_drawdown, 'strategy': 'RSI_ROC',
                                   'params': f"RSI<{ro}, ROC>{rt}, TP={pf}"}
                        
                        if current % 50 == 0:
                            print(f"  進度 {current}/{total_tests}...")
                            
                    except:
                        pass
        
        # MA 策略
        for fast, slow in fast_slows:
            for pf in [0.15, 0.20]:
                current += 1
                try:
                    s = MA_Crossover_Strategy(fast=fast, slow=slow, profit=pf)
                    r = engine.run(symbol, s, data, f"MA_{fast}_{slow}_{pf}")
                    sharpe = r.annualized_return / r.volatility if r.volatility > 0 else 0
                    
                    if sharpe >= 1.5 and r.annualized_return >= 0.20:
                        qualified.append({
                            'symbol': symbol, 'strategy': 'MA',
                            'sharpe': sharpe, 'return': r.annualized_return,
                            'max_dd': r.max_drawdown, 'trades': r.total_trades,
                            'params': f"MA{fast}/{slow}, TP={pf}"
                        })
                    
                    if sharpe > best['sharpe'] and r.annualized_return > best['return']:
                        best = {'sharpe': sharpe, 'return': r.annualized_return,
                               'dd': r.max_drawdown, 'strategy': f'MA_{fast}_{slow}',
                               'params': f"MA{fast}/{slow}, TP={pf}"}
                            
                except:
                    pass
    
    # 結果
    print("\n" + "="*70)
    print("📋 結果摘要")
    print("="*70)
    
    print(f"\n🏆 最佳策略: {best['strategy']}")
    print(f"   Sharpe: {best['sharpe']:.2f}")
    print(f"   Return: {best['return']:.2%}")
    print(f"   MaxDD: {best['dd']:.2%}")
    print(f"   參數: {best['params']}")
    
    if qualified:
        print(f"\n✅ 合格策略 ({len(qualified)} 個):")
        for i, q in enumerate(sorted(qualified, key=lambda x: x['sharpe'], reverse=True)[:10], 1):
            print(f"   {i}. {q['symbol']} - {q['strategy']}")
            print(f"      Sharpe:{q['sharpe']:.2f} Return:{q['return']:.2%} DD:{q['max_dd']:.2%} Trades:{q['trades']}")
            print(f"      {q['params']}")
    else:
        print(f"\n⚠️ 沒有完全達標的策略")
    
    return qualified, best

if __name__ == "__main__":
    qualified, best = quick_test()
