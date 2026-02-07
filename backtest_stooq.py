#!/usr/bin/env python3
"""
TradeMaster v2 - 真實數據回測
數據來源: Stooq (免費，繞過 yfinance 限制)
"""
import urllib.request
import ssl
import pandas as pd
import io
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class PositionType(Enum):
    NONE = "none"
    LONG = "long"
    SHORT = "short"


def download_stooq(symbol: str, start_date: str = "20200101", end_date: str = "20251231") -> pd.DataFrame:
    """從 Stooq 下載歷史數據"""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    url = f'https://stooq.com/q/d/l/?s={symbol}.us&d1={start_date}&d2={end_date}&i=d'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req, context=ssl_context, timeout=60) as response:
        df = pd.read_csv(io.StringIO(response.read().decode('utf-8')))
    
    # 處理數據格式
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values('Date').reset_index(drop=True)
    
    return df


def download_all_data(symbols: List[str] = ['AAPL', 'TSLA', 'SPY']) -> Dict[str, pd.DataFrame]:
    """下載所有標的數據"""
    data = {}
    for symbol in symbols:
        print(f"📥 下載 {symbol}...", end=" ")
        try:
            df = download_stooq(symbol)
            if len(df) > 100:
                data[symbol] = df
                print(f"✓ {len(df)} 天")
            else:
                print(f"✗ 數據不足")
        except Exception as e:
            print(f"✗ 失敗: {e}")
    return data


class Signal:
    def __init__(self, signal, confidence=0.5, price=0.0, reason=""):
        self.signal = signal
        self.confidence = confidence
        self.price = price
        self.reason = reason


class Strategy(ABC):
    @abstractmethod
    def generate_signal(self, indicators: dict, data: pd.DataFrame) -> Signal:
        pass


class RSIStrategy(Strategy):
    """RSI 均值回歸策略"""
    def __init__(self, rsi_period=14, oversold=35, overbought=75, 
                 stop_loss=0.10, take_profit=0.08):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, indicators: dict, data: pd.DataFrame) -> Signal:
        close = data['Close']
        cp = float(close.iloc[-1])
        
        if len(close) < self.rsi_period + 5:
            return Signal("HOLD", 0.2, cp, "Warming up")
        
        rsi = indicators['RSI']['rsi'].iloc[-1]
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (cp - self.entry_price) / self.entry_price
            if pnl >= self.take_profit:
                self.position = None
                return Signal("HOLD", 0.8, cp, f"TP +{pnl*100:.1f}%")
            if pnl <= -self.stop_loss:
                self.position = None
                return Signal("HOLD", 0.8, cp, f"SL {pnl*100:.1f}%")
        
        # 進場信號
        if rsi < self.oversold and self.position is None:
            self.position = "LONG"
            self.entry_price = cp
            return Signal("LONG", 0.75, cp, f"RSI={rsi:.0f}")
        
        if rsi > self.overbought and self.position == "LONG":
            self.position = None
            return Signal("HOLD", 0.7, cp, f"RSI={rsi:.0f}")
        
        return Signal("HOLD", 0.3, cp, f"RSI={rsi:.0f}")


class MACrossoverStrategy(Strategy):
    """MA 交叉策略"""
    def __init__(self, fast=10, slow=20, stop_loss=0.05, take_profit=0.15):
        self.fast = fast
        self.slow = slow
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.position = None
        self.entry_price = None
    
    def generate_signal(self, indicators: dict, data: pd.DataFrame) -> Signal:
        close = data['Close']
        cp = float(close.iloc[-1])
        
        if len(close) < self.slow + 5:
            return Signal("HOLD", 0.2, cp, "Warming up")
        
        ema_fast = close.ewm(span=self.fast, adjust=False).mean().iloc[-1]
        ema_slow = close.ewm(span=self.slow, adjust=False).mean().iloc[-1]
        ema_fast_prev = close.ewm(span=self.fast, adjust=False).mean().iloc[-2]
        ema_slow_prev = close.ewm(span=self.slow, adjust=False).mean().iloc[-2]
        
        # 持倉管理
        if self.position == "LONG" and self.entry_price:
            pnl = (cp - self.entry_price) / self.entry_price
            if pnl >= self.take_profit:
                self.position = None
                return Signal("HOLD", 0.8, cp, f"TP +{pnl*100:.1f}%")
            if pnl <= -self.stop_loss:
                self.position = None
                return Signal("HOLD", 0.8, cp, f"SL {pnl*100:.1f}%")
        
        # 進場信號：黃金交叉
        if ema_fast_prev <= ema_slow_prev and ema_fast > ema_slow and self.position is None:
            self.position = "LONG"
            self.entry_price = cp
            return Signal("LONG", 0.75, cp, f"MA{self.fast}/{self.slow} Golden")
        
        # 出場信號：死亡交叉
        if ema_fast_prev >= ema_slow_prev and ema_fast < ema_slow and self.position == "LONG":
            self.position = None
            return Signal("HOLD", 0.7, cp, f"MA{self.fast}/{self.slow} Death")
        
        return Signal("HOLD", 0.3, cp, "No signal")


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.Series:
    """計算 RSI"""
    close = data['Close']
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def run_backtest(data: pd.DataFrame, strategy: Strategy, symbol: str) -> dict:
    """運行回測"""
    df = data.copy()
    df['RSI'] = calculate_rsi(df)
    
    # 生成信號
    signals = []
    positions = []
    equity = [100000]
    position = None
    
    for i in range(len(df)):
        ind = {'RSI': {'rsi': df['RSI'].iloc[:i+1]}}
        sig = strategy.generate_signal(ind, df.iloc[:i+1])
        signals.append(sig.signal)
        
        if sig.signal == "LONG" and position is None:
            position = {"shares": 100000 / df['Close'].iloc[i], 
                       "entry": df['Close'].iloc[i]}
        elif sig.signal == "HOLD" and position:
            # 檢查止損止盈
            current_price = df['Close'].iloc[i]
            pnl = (current_price - position["entry"]) / position["entry"]
            if pnl <= -strategy.stop_loss or pnl >= strategy.take_profit:
                equity.append(equity[-1] * (1 + pnl))
                position = None
            else:
                equity.append(equity[-1])
        else:
            equity.append(equity[-1])
    
    # 計算指標
    equity_series = pd.Series(equity)
    returns = equity_series.pct_change().dropna()
    
    total_return = (equity[-1] / equity[0]) - 1
    annual_return = total_return * (252 / len(df))
    volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0
    sharpe = annual_return / volatility if volatility > 0 else 0
    
    # 最大回撤
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak
    max_drawdown = abs(drawdown.min())
    
    # 構建參數描述
    if hasattr(strategy, 'rsi_period'):
        params_str = f"RSI({strategy.rsi_period}/{strategy.oversold}/{strategy.overbought})"
    elif hasattr(strategy, 'fast'):
        params_str = f"MA({strategy.fast}/{strategy.slow})"
    else:
        params_str = "Unknown"
    
    return {
        'symbol': symbol,
        'strategy': strategy.__class__.__name__,
        'params': params_str,
        'sharpe': sharpe,
        'return': annual_return,
        'max_dd': max_drawdown,
        'total_trades': sum(1 for s in signals if s in ['LONG']),
        'final_equity': equity[-1]
    }


def run_all_tests():
    """運行所有測試"""
    print("="*70)
    print("🚀 TradeMaster v2 - 真實數據回測 (Stooq)")
    print("="*70)
    
    # 下載數據
    print("\n📥 下載歷史數據...")
    data = download_all_data(['AAPL', 'TSLA', 'SPY'])
    
    if not data:
        print("❌ 無法下載數據")
        return
    
    # 測試策略
    results = []
    
    for symbol, df in data.items():
        print(f"\n📊 {symbol} 回測中...")
        
        # RSI 策略參數測試
        for oversold in [30, 35, 40]:
            for overbought in [70, 75]:
                for sl in [0.08, 0.10]:
                    for tp in [0.08, 0.10, 0.12]:
                        strat = RSIStrategy(oversold=oversold, overbought=overbought, 
                                          stop_loss=sl, take_profit=tp)
                        r = run_backtest(df, strat, symbol)
                        results.append(r)
    
    # MA 策略測試
    for fast, slow in [(5, 15), (10, 20), (10, 30)]:
        for sl in [0.03, 0.05]:
            for tp in [0.15, 0.20]:
                strat = MACrossoverStrategy(fast=fast, slow=slow, stop_loss=sl, take_profit=tp)
                r = run_backtest(df, strat, symbol)
                results.append(r)
    
    # 結果排序
    qualified = [r for r in results if r['sharpe'] > 1.5 and r['return'] > 0.20]
    qualified.sort(key=lambda x: x['sharpe'], reverse=True)
    
    print("\n" + "="*70)
    print("📋 回測結果")
    print("="*70)
    
    print(f"\n✅ 達標策略 (Sharpe > 1.5, Return > 20%): {len(qualified)} 個")
    
    # 保存結果
    df_results = pd.DataFrame(results)
    df_results.to_csv('/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/stooq_backtest_results.csv', index=False)
    print(f"\n💾 結果已保存到: stooq_backtest_results.csv")
    
    return qualified


if __name__ == "__main__":
    run_all_tests()
