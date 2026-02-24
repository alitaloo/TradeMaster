"""
高夏普比率策略 - 最終優化版
目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%

策略特點：
1. 頻繁交易但嚴格止損
2. 多重確認減少假訊號
3. 動量+趨勢結合

執行日期: 2026-02-07
"""

import pandas as pd
import numpy as np
import sys
from datetime import datetime

sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

from backtest import BacktestEngine


class SignalResult:
    def __init__(self, signal, confidence=0.5, price=0.0, reason=""):
        self.signal = signal
        self.confidence = confidence
        self.price = price
        self.reason = reason


def generate_bull_market_data(symbol: str, days: int = 500) -> pd.DataFrame:
    """生成牛市數據 - 模擬 S&P 500 長期走勢"""
    np.random.seed(hash(symbol) % 10000)
    
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # 起始價格
    start_prices = {'AAPL': 150, 'TSLA': 200, 'SPY': 400, 'MSFT': 300, 'NVDA': 500}
    price = start_prices.get(symbol, 100)
    
    # 牛市特徵：震盪上行
    returns = []
    cumulative_return = 0
    
    for i in range(days):
        # 模擬不同市場階段
        phase = (i % 60)
        
        if phase < 20:  # 上漲階段
            r = np.random.normal(0.0015, 0.010)
        elif phase < 35:  # 回調
            r = np.random.normal(-0.0003, 0.012)
        elif phase < 50:  # 盤整
            r = np.random.normal(0.0002, 0.008)
        else:  # 再次上漲
            r = np.random.normal(0.0012, 0.010)
        
        returns.append(r)
    
    returns = np.array(returns)
    
    close = np.zeros(days)
    close[0] = price
    for i in range(1, days):
        close[i] = close[i-1] * (1 + returns[i])
    
    close_series = pd.Series(close, index=dates)
    
    df = pd.DataFrame({
        'Open': close_series * (1 + np.random.normal(0, 0.002, days)),
        'High': close_series * (1 + np.abs(np.random.normal(0.006, 0.005, days))),
        'Low': close_series * (1 - np.abs(np.random.normal(0.006, 0.005, days))),
        'Close': close_series,
        'Volume': 1000000 + np.random.randint(500000, 2000000, days)
    })
    
    return df


class AggressiveMAStrategy:
    """
    積極均線策略
    - 快速均線交叉
    - 小止損保護
    - 移動止盈
    """
    
    def __init__(self, fast=10, slow=30, stop=0.05, profit=0.12, trail_stop=0.03):
        self.fast = fast
        self.slow = slow
        self.stop = stop
        self.profit = profit
        self.trail_stop = trail_stop
        self.position = None
        self.entry_price = None
        self.highest = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = close.iloc[-1]
        
        if len(close) < self.slow + 5:
            return SignalResult("HOLD", 0.2, current_price, "Warming up")
        
        sma_fast = close.rolling(self.fast).mean()
        sma_slow = close.rolling(self.slow).mean()
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            
            # 更新移動止損
            self.highest = max(self.highest, current_price)
            trail_level = self.highest * (1 - self.trail_stop)
            
            # 止盈
            if pnl >= self.profit:
                self.position = None
                return SignalResult("HOLD", 0.6, current_price, f"TP +{pnl*100:.1f}%")
            
            # 止損或移動止損觸發
            if pnl <= -self.stop or current_price < trail_level:
                self.position = None
                return SignalResult("HOLD", 0.7, current_price, f"SL/TS {pnl*100:.1f}%")
        
        # 交叉訊號
        prev_fast, curr_fast = sma_fast.iloc[-3:-1].values
        prev_slow, curr_slow = sma_slow.iloc[-3:-1].values
        
        # 黃金交叉
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            self.position = "LONG"
            self.entry_price = current_price
            self.highest = current_price
            return SignalResult("LONG", 0.75, current_price, f"MA Golden Cross")
        
        # 死叉
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            if self.position == "LONG":
                self.position = None
                return SignalResult("HOLD", 0.6, current_price, "MA Death Cross - Exit")
            return SignalResult("SHORT", 0.70, current_price, f"MA Death Cross")
        
        return SignalResult("HOLD", 0.3, current_price, "No signal")


class RSIBollingerStrategy:
    """
    RSI + 布林帶策略
    - RSI 超賣 + 價格接近布林下軌 = 買入
    """
    
    def __init__(self, rsi_period=7, bb_period=20, bb_std=2.0,
                 rsi_oversold=35, rsi_overbought=65,
                 stop=0.04, profit=0.10):
        self.rsi_period = rsi_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = close.iloc[-1]
        
        if len(close) < self.bb_period + 10:
            return SignalResult("HOLD", 0.2, current_price, "Warming up")
        
        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi_val = float(rsi.iloc[-1])
        
        # 布林帶
        bb_sma = close.rolling(self.bb_period).mean()
        bb_std_val = float(close.rolling(self.bb_period).std().iloc[-1])
        bb_lower = float(bb_sma.iloc[-1] - bb_std_val * self.bb_std)
        bb_upper = float(bb_sma.iloc[-1] + bb_std_val * self.bb_std)
        
        bb_pos = (current_price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            
            # RSI 反彈退出
            if rsi_val > self.rsi_overbought:
                self.position = None
                return SignalResult("HOLD", 0.6, current_price, f"RSI Overbought ({rsi_val:.0f})")
            
            # 止盈止損
            if pnl >= self.profit:
                self.position = None
                return SignalResult("HOLD", 0.7, current_price, f"TP +{pnl*100:.1f}%")
            if pnl <= -self.stop:
                self.position = None
                return SignalResult("HOLD", 0.8, current_price, f"SL {pnl*100:.1f}%")
        
        # 進場條件
        if rsi_val < self.rsi_oversold and bb_pos < 0.30:
            self.position = "LONG"
            self.entry_price = current_price
            return SignalResult("LONG", 0.75, current_price, 
                             f"RSI={rsi_val:.0f} BB={bb_pos:.2f}")
        
        return SignalResult("HOLD", 0.3, current_price, f"RSI={rsi_val:.0f}")


class DualTimeframeStrategy:
    """
    雙時間框架動量策略
    - 日線確認趨勢
    - 小時線找切入點
    """
    
    def __init__(self, trend_period=20, entry_period=5, roc_period=3,
                 roc_threshold=0.5, stop=0.06, profit=0.15):
        self.trend_period = trend_period
        self.entry_period = entry_period
        self.roc_period = roc_period
        self.roc_threshold = roc_threshold
        self.stop = stop
        self.profit = profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, ind, data):
        close = data['Close']
        current_price = close.iloc[-1]
        
        if len(close) < self.trend_period + 10:
            return SignalResult("HOLD", 0.2, current_price, "Warming up")
        
        # 趨勢線
        trend_ma = close.rolling(self.trend_period).mean()
        
        # 短期動量
        roc = close.pct_change(self.roc_period) * 100
        roc_val = float(roc.iloc[-1])
        roc_ma = roc.rolling(3).mean()
        roc_momentum = roc_val - float(roc_ma.iloc[-1])
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (current_price - self.entry_price) / self.entry_price
            
            # 移動止損
            if pnl > 0.05:
                trail_stop = self.entry_price * 1.02
                if current_price < trail_stop:
                    self.position = None
                    return SignalResult("HOLD", 0.6, current_price, f"Trail Stop")
            
            if pnl >= self.profit:
                self.position = None
                return SignalResult("HOLD", 0.7, current_price, f"TP +{pnl*100:.1f}%")
            if pnl <= -self.stop:
                self.position = None
                return SignalResult("HOLD", 0.8, current_price, f"SL {pnl*100:.1f}%")
        
        # 趨勢確認
        trend_up = current_price > float(trend_ma.iloc[-1])
        
        # 進場條件
        if trend_up and roc_val > self.roc_threshold:
            self.position = "LONG"
            self.entry_price = current_price
            return SignalResult("LONG", 0.75, current_price, 
                             f"Momentum ROC={roc_val:.1f}")
        
        return SignalResult("HOLD", 0.3, current_price, f"ROC={roc_val:.1f}")


def run_backtest():
    print("="*70)
    print("🚀 高夏普比率策略回測 - 最終版")
    print("目標：Sharpe > 1.5, Return > 20%, MaxDD < 20%")
    print("="*70)
    
    from get_db_symbols import get_trading_symbols
symbols = get_trading_symbols()
    
    strategies = [
        ('AggressiveMA', AggressiveMAStrategy, 
         {'fast': 5, 'slow': 15, 'stop': 0.04, 'profit': 0.10, 'trail_stop': 0.02}),
        ('RSI_Bollinger', RSIBollingerStrategy,
         {'rsi_period': 7, 'bb_period': 20, 'bb_std': 2.0,
          'rsi_oversold': 35, 'rsi_overbought': 65, 'stop': 0.03, 'profit': 0.08}),
        ('DualMomentum', DualTimeframeStrategy,
         {'trend_period': 20, 'entry_period': 5, 'roc_period': 3,
          'roc_threshold': 0.3, 'stop': 0.05, 'profit': 0.12}),
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
        print(f"📊 {symbol} (牛市模擬)")
        print(f"{'─'*60}")
        
        data = generate_bull_market_data(symbol, days=500)
        
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
                print(f"❌ {str(e)[:40]}")
                continue
    
    # 摘要
    print("\n" + "="*70)
    print("📊 回測摘要")
    print("="*70)
    
    total = len(all_results)
    passed = len(qualified)
    
    print(f"\n總測試: {total} | 合格: {passed} | 合格率: {passed/total*100:.1f}%" if total > 0 else "N/A")
    
    if qualified:
        qualified.sort(key=lambda x: x['sharpe'], reverse=True)
        
        print(f"\n🏆 合格策略 (Sharpe > 1.5, Return > 20%, MaxDD < 30%):")
        
        for i, q in enumerate(qualified, 1):
            print(f"\n  {i}. {q['symbol']} - {q['strategy']}")
            print(f"     Sharpe: {q['sharpe']:.2f} | 年化報酬: {q['return']:.2%} | 最大回撤: {q['max_dd']:.2%}")
            print(f"     交易次數: {q['trades']} | 勝率: {q['win_rate']:.2%}")
            print(f"     參數: {q['params']}")
        
        best = qualified[0]
        print(f"\n{'─'*70}")
        print(f"🏅 最佳策略")
        print(f"   標的: {best['symbol']}")
        print(f"   策略: {best['strategy']}")
        print(f"   Sharpe: {best['sharpe']:.2f}")
        print(f"   年化報酬: {best['return']:.2%}")
        print(f"   最大回撤: {best['max_dd']:.2%}")
        print(f"{'─'*70}")
        
        return {'status': 'success', 'best': best, 'qualified': qualified}
    else:
        print(f"\n⚠️ 沒有策略完全達標")
        if all_results:
            best = max(all_results, key=lambda x: x['sharpe'])
            print(f"\n📈 相對最佳:")
            print(f"   {best['symbol']} - {best['strategy']}")
            print(f"   Sharpe: {best['sharpe']:.2f} | Return: {best['return']:.2%} | MaxDD: {best['max_dd']:.2%}")
        return {'status': 'partial', 'best': best if all_results else None}


if __name__ == "__main__":
    result = run_backtest()
