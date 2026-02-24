#!/usr/bin/env python3
"""
高級策略回測腳本 v2

使用更真實的市場模擬數據
測試策略在真實市場環境中的表現

Author: TradeMaster Pro
Date: 2026-02-07
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

# 導入策略
from strategies.advanced_quant_strategies import (
    AdvancedDualMomentum,
    QualityMomentum,
    RSIAggressive,
    WilliamsPercentR,
    ATRBreakout,
    AdaptiveMultiFactor,
    SignalResult
)


@dataclass
class BacktestConfig:
    """回測配置"""
    initial_capital: float = 100000
    commission_rate: float = 0.0005  # 0.05% 手續費
    slippage: float = 0.0002  # 0.02% 滑價
    risk_free_rate: float = 0.02
    max_position_size: float = 1.0
    min_trade_amount: float = 1000


class RealisticMarketSimulator:
    """
    現實市場模擬器
    
    生成更真實的市場數據，包含：
    - 趨勢行情
    - 震盪行情
    - 突破行情
    - 急跌反彈
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
    
    def generate_trending_market(self, n_days: int = 500) -> pd.DataFrame:
        """生成趨勢市場數據"""
        np.random.seed(self.seed)
        dates = pd.date_range(start="2020-01-01", periods=n_days, freq='D')
        
        # 趨勢上漲
        trend = np.linspace(0, 0.0008, n_days)  # 輕微上升趨勢
        noise = np.random.normal(0, 0.012, n_days)
        returns = trend + noise
        
        # 添加一些回調
        returns[150:170] -= 0.02
        returns[300:320] -= 0.015
        
        close = 100 * np.cumprod(1 + returns)
        
        high = close * (1 + np.abs(np.random.normal(0.008, 0.005, n_days)))
        low = close * (1 - np.abs(np.random.normal(0.008, 0.005, n_days)))
        volume = np.random.uniform(1000000, 3000000, n_days)
        
        return self._create_dataframe(dates, close, high, low, volume)
    
    def generate_volatile_market(self, n_days: int = 500) -> pd.DataFrame:
        """生成高波動市場數據"""
        np.random.seed(self.seed + 1)
        dates = pd.date_range(start="2020-01-01", periods=n_days, freq='D')
        
        # 高波動，無明顯趨勢
        returns = np.random.normal(0, 0.025, n_days)
        
        # 急跌急漲
        returns[100:105] = -0.04  # 急跌
        returns[106:115] = 0.03  # 反彈
        returns[300:305] = -0.05  # 再次急跌
        returns[306:320] = 0.04   # 強勁反彈
        
        close = 100 * np.cumprod(1 + returns)
        
        high = close * (1 + np.abs(np.random.normal(0.015, 0.01, n_days)))
        low = close * (1 - np.abs(np.random.normal(0.015, 0.01, n_days)))
        volume = np.random.uniform(1500000, 5000000, n_days)
        
        return self._create_dataframe(dates, close, high, low, volume)
    
    def generate_breakout_market(self, n_days: int = 500) -> pd.DataFrame:
        """生成突破市場數據"""
        np.random.seed(self.seed + 2)
        dates = pd.date_range(start="2020-01-01", periods=n_days, freq='D')
        
        # 盤整後突破
        returns = np.random.normal(0, 0.008, n_days)
        
        # 盤整期
        returns[1:150] = np.random.normal(0, 0.005, 149)
        
        # 向上突破
        returns[150:180] = 0.012  # 突破上漲
        returns[180:250] = 0.005  # 持續上漲
        
        # 回調
        returns[250:270] = -0.008
        
        # 再次上漲
        returns[270:350] = 0.008
        
        close = 100 * np.cumprod(1 + returns)
        
        high = close * (1 + np.abs(np.random.normal(0.01, 0.008, n_days)))
        low = close * (1 - np.abs(np.random.normal(0.01, 0.008, n_days)))
        volume = np.random.uniform(1000000, 4000000, n_days)
        
        # 突破時放量
        volume[150:180] *= 2
        
        return self._create_dataframe(dates, close, high, low, volume)
    
    def generate_mixed_market(self, n_days: int = 1000) -> pd.DataFrame:
        """生成混合市場數據（最接近真實）"""
        np.random.seed(self.seed + 3)
        dates = pd.date_range(start="2020-01-01", periods=n_days, freq='D')
        
        # 不同階段
        returns = np.zeros(n_days)
        
        # Phase 1: 趨勢上漲 (1-200)
        returns[1:200] = np.random.normal(0.0006, 0.01, 199)
        
        # Phase 2: 震盪 (200-400)
        returns[200:400] = np.random.normal(0, 0.015, 200)
        
        # Phase 3: 急跌 (400-420)
        returns[400:420] = np.random.normal(-0.015, 0.02, 20) - 0.02
        
        # Phase 4: 反彈 (420-500)
        returns[420:500] = np.random.normal(0.012, 0.015, 80)
        
        # Phase 5: 盤整突破 (500-700)
        returns[500:650] = np.random.normal(0, 0.008, 150)
        returns[650:700] = 0.015  # 突破
        
        # Phase 6: 持續上漲 (700-850)
        returns[700:850] = np.random.normal(0.0008, 0.012, 150)
        
        # Phase 7: 回調 (850-1000)
        returns[850:1000] = np.random.normal(-0.003, 0.015, 150)
        
        close = 100 * np.cumprod(1 + returns)
        
        high = close * (1 + np.abs(np.random.normal(0.012, 0.01, n_days)))
        low = close * (1 - np.abs(np.random.normal(0.012, 0.01, n_days)))
        volume = np.random.uniform(1000000, 4000000, n_days)
        
        # 事件時放量
        volume[400:420] *= 2.5  # 急跌放量
        volume[650:700] *= 2     # 突破放量
        
        return self._create_dataframe(dates, close, high, low, volume)
    
    def _create_dataframe(self, dates, close, high, low, volume) -> pd.DataFrame:
        """創建 DataFrame"""
        return pd.DataFrame({
            'Open': close * (1 + np.random.uniform(-0.003, 0.003, len(close))),
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': volume
        }, index=dates)


class ImprovedBacktester:
    """改進的回測引擎"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
    
    def run_strategy(self, strategy, data: pd.DataFrame, 
                     strategy_name: str) -> Dict:
        """運行單一策略回測"""
        
        capital = self.config.initial_capital
        position = 0
        entry_price = 0
        trades = []
        equity = [capital]
        
        start_idx = max(50, 20)  # 等待指標穩定
        
        for i in range(start_idx, len(data)):
            current_data = data.iloc[:i+1]
            current_price = data["Close"].iloc[i]
            
            # 生成信號
            try:
                signal = strategy.generate_signal({}, current_data)
            except:
                signal = SignalResult(signal="HOLD")
            
            # 持倉管理
            if position > 0:
                unrealized = (current_price - entry_price) / entry_price
                
                # 檢查退出信號
                if signal.signal == "HOLD" and signal.metadata:
                    meta = signal.metadata
                    
                    if meta.get("type") == "take_profit":
                        pnl = unrealized * position * capital
                        capital += pnl * (1 - self.config.commission_rate)
                        trades.append({
                            'return': unrealized,
                            'duration': i - (trades[-1]['entry_idx'] if trades else i)
                        })
                        position = 0
                    
                    elif meta.get("type") == "stop_loss":
                        pnl = unrealized * position * capital
                        capital += pnl * (1 - self.config.commission_rate)
                        trades.append({
                            'return': unrealized,
                            'duration': i - (trades[-1]['entry_idx'] if trades else i)
                        })
                        position = 0
            
            # 開倉
            if position == 0 and signal.signal == "LONG":
                shares = int((capital * self.config.max_position_size) / current_price)
                if shares > 0:
                    position = shares
                    entry_price = current_price * (1 + self.config.slippage)
                    if trades:
                        trades[-1]['entry_idx'] = i
            
            # 更新權益
            portfolio_value = capital + position * current_price
            equity.append(portfolio_value)
        
        # 最終平倉
        if position > 0:
            final_price = data["Close"].iloc[-1]
            unrealized = (final_price - entry_price) / entry_price
            pnl = unrealized * position * capital
            capital += pnl * (1 - self.config.commission_rate)
            if trades:
                trades[-1]['return'] = unrealized
        
        # 計算指標
        equity = np.array(equity)
        returns = np.diff(equity) / equity[:-1]
        
        total_return = (capital - self.config.initial_capital) / self.config.initial_capital
        years = len(data) / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) - self.config.risk_free_rate / 252) / np.std(returns) * np.sqrt(252)
        else:
            sharpe = 0
        
        rolling_max = np.maximum.accumulate(equity)
        drawdown = (equity - rolling_max) / rolling_max
        max_drawdown = abs(min(drawdown))
        
        if trades:
            win_rate = sum(1 for t in trades if t['return'] > 0) / len(trades)
            avg_duration = np.mean([t['duration'] for t in trades])
        else:
            win_rate = 0
            avg_duration = 0
        
        return {
            'strategy': strategy_name,
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe': sharpe,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'trades': len(trades),
            'avg_duration': avg_duration,
            'final_capital': capital
        }


def run_all_tests():
    """運行所有測試"""
    print("\n" + "="*80)
    print("高級量化策略回測 v2 - 真實市場模擬")
    print("="*80)
    
    simulator = RealisticMarketSimulator()
    tester = ImprovedBacktester()
    
    # 測試場景
    scenarios = [
        ("趨勢市場", simulator.generate_trending_market),
        ("高波動市場", simulator.generate_volatile_market),
        ("突破市場", simulator.generate_breakout_market),
        ("混合市場", simulator.generate_mixed_market),
    ]
    
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
            roc_period=10, roc_weight=0.35,
            mean_reversion_period=20, mr_weight=0.20,
            vol_period=20, vol_weight=0.15,
            trend_period=50, adx_period=14, trend_weight=0.30,
            stop_loss=0.08, take_profit=0.25, max_holding_days=30
        )),
    ]
    
    all_results = {}
    
    for scenario_name, generate_data in scenarios:
        print(f"\n{'='*60}")
        print(f"場景: {scenario_name}")
        print(f"{'='*60}")
        
        data = generate_data()
        results = []
        
        for name, strategy in strategies:
            result = tester.run_strategy(strategy, data, name)
            results.append(result)
            all_results.setdefault(name, []).append(result)
            
            meets_target = "✓" if result['sharpe'] >= 1.5 and result['total_return'] > 0.20 else "○" if result['sharpe'] >= 1.0 else "✗"
            
            print(f"\n[{name}] {meets_target}")
            print(f"  總報酬: {result['total_return']*100:>8.2f}%")
            print(f"  年化報酬: {result['annual_return']*100:>8.2f}%")
            print(f"  夏普比率: {result['sharpe']:>8.3f}")
            print(f"  最大回撤: {result['max_drawdown']*100:>8.2f}%")
            print(f"  勝率: {result['win_rate']*100:>8.2f}%")
            print(f"  交易次數: {result['trades']:>5}")
    
    # 總結
    print("\n" + "="*80)
    print("策略總結")
    print("="*80)
    
    summary_data = []
    for name, results in all_results.items():
        avg_return = np.mean([r['total_return'] for r in results])
        avg_sharpe = np.mean([r['sharpe'] for r in results])
        avg_maxdd = np.mean([r['max_drawdown'] for r in results])
        avg_winrate = np.mean([r['win_rate'] for r in results])
        
        summary_data.append({
            'strategy': name,
            'avg_return': avg_return,
            'avg_sharpe': avg_sharpe,
            'avg_maxdd': avg_maxdd,
            'avg_winrate': avg_winrate
        })
    
    # 按夏普排序
    summary_data.sort(key=lambda x: x['avg_sharpe'], reverse=True)
    
    print(f"\n{'策略名稱':<25} {'平均報酬':>12} {'平均夏普':>10} {'平均回撤':>10} {'平均勝率':>10}")
    print("-"*70)
    
    for s in summary_data:
        meets = "✓" if s['avg_sharpe'] >= 1.5 and s['avg_return'] > 0.20 else "○"
        print(f"{s['strategy']:<25} {s['avg_return']*100:>10.2f}% {s['avg_sharpe']:>10.3f} "
              f"{s['avg_maxdd']*100:>8.2f}% {s['avg_winrate']*100:>9.2f}% {meets}")
    
    # 最佳策略
    best = summary_data[0]
    print(f"\n🏆 最佳策略: {best['strategy']}")
    print(f"   平均報酬: {best['avg_return']*100:.2f}%")
    print(f"   平均夏普: {best['avg_sharpe']:.3f}")
    
    # 達標統計
    qualified = sum(1 for s in summary_data if s['avg_sharpe'] >= 1.5 and s['avg_return'] > 0.20)
    print(f"\n📊 達標策略數量: {qualified}/{len(summary_data)}")
    
    return all_results


if __name__ == "__main__":
    run_all_tests()
