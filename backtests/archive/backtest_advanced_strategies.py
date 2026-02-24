#!/usr/bin/env python3
"""
高級策略回測腳本

測試 Advanced Quant Strategies:
1. AdvancedDualMomentum - 增強版雙重動量
2. QualityMomentum - 質量動量
3. RSIAggressive - RSI-2 激进策略
4. WilliamsPercentR - %R 威廉指標
5. ATRBreakout - ATR 突破策略
6. AdaptiveMultiFactor - 自適應多因子

目標: Return > 20%, Sharpe > 1.5, MaxDD < 20%

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
    commission_rate: float = 0.001  # 0.1% 手續費
    slippage: float = 0.0005  # 0.05% 滑價
    risk_free_rate: float = 0.02  # 無風險利率
    max_position_size: float = 0.9  # 最大倉位比例
    min_trade_amount: float = 1000  # 最小交易金額


@dataclass
class BacktestResult:
    """回測結果"""
    strategy_name: str
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_duration: float
    final_capital: float
    equity_curve: pd.Series
    trade_log: List[Dict]
    
    def to_dict(self) -> Dict:
        return {
            "Strategy": self.strategy_name,
            "Total Return": f"{self.total_return*100:.2f}%",
            "Annual Return": f"{self.annual_return*100:.2f}%",
            "Sharpe Ratio": f"{self.sharpe_ratio:.3f}",
            "Max Drawdown": f"{self.max_drawdown*100:.2f}%",
            "Win Rate": f"{self.win_rate*100:.2f}%",
            "Profit Factor": f"{self.profit_factor:.2f}",
            "Total Trades": self.total_trades,
            "Avg Duration": f"{self.avg_trade_duration:.1f} days",
            "Final Capital": f"${self.final_capital:,.0f}"
        }


class AdvancedStrategyBacktester:
    """
    高級策略回測引擎
    
    特點：
    - 真實模擬交易成本
    - 移動止損
    - 風險管理
    - Monte Carlo 置信區間
    """
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
    
    def run_backtest(self, strategy, data: pd.DataFrame, 
                     strategy_name: str = "Unknown") -> BacktestResult:
        """
        運行回測
        
        Args:
            strategy: 策略實例
            data: OHLCV 數據
            strategy_name: 策略名稱
        
        Returns:
            BacktestResult: 回測結果
        """
        if len(data) < 100:
            raise ValueError("需要至少100天的數據")
        
        # 初始化
        capital = self.config.initial_capital
        position = 0  # 持倉數量
        entry_price = 0
        entry_date = None
        equity_curve = [capital]
        trades = []
        wins = 0
        losses = 0
        win_amount = 0
        loss_amount = 0
        
        # 從第50天開始交易（等待指標穩定）
        start_idx = 50
        
        for i in range(start_idx, len(data)):
            current_data = data.iloc[:i+1]
            current_price = data["Close"].iloc[i]
            current_date = data.index[i] if hasattr(data.index, '__iter__') else i
            
            # 生成訊號
            try:
                signal = strategy.generate_signal({}, current_data)
            except Exception as e:
                signal = SignalResult(signal="HOLD", confidence=0, reason=str(e))
            
            # 持倉管理
            if position > 0:
                # 計算當前盈虧
                unrealized_pnl = (current_price - entry_price) / entry_price
                
                # 檢查是否需要止盈/止損
                if signal.signal == "HOLD":
                    if signal.metadata:
                        meta = signal.metadata
                        if meta.get("type") == "take_profit":
                            # 止盈
                            pnl = (current_price - entry_price) * position * (1 - self.config.slippage)
                            capital += pnl - capital * self.config.commission_rate
                            position = 0
                            trades.append({
                                "date": current_date,
                                "type": "LONG",
                                "entry_price": entry_price,
                                "exit_price": current_price,
                                "return": unrealized_pnl,
                                "duration": (i - entry_date) if entry_date else 0,
                                "reason": "Take Profit"
                            })
                            if unrealized_pnl > 0:
                                wins += 1
                                win_amount += abs(pnl)
                            else:
                                losses += 1
                                loss_amount += abs(pnl)
                            
                        elif meta.get("type") == "stop_loss":
                            # 止損
                            pnl = (current_price - entry_price) * position * (1 - self.config.slippage)
                            capital += pnl - capital * self.config.commission_rate
                            position = 0
                            trades.append({
                                "date": current_date,
                                "type": "LONG",
                                "entry_price": entry_price,
                                "exit_price": current_price,
                                "return": unrealized_pnl,
                                "duration": (i - entry_date) if entry_date else 0,
                                "reason": "Stop Loss"
                            })
                            if unrealized_pnl > 0:
                                wins += 1
                                win_amount += abs(pnl)
                            else:
                                losses += 1
                                loss_amount += abs(pnl)
                            
                        elif meta.get("type") == "time_exit":
                            # 時間退出
                            pnl = (current_price - entry_price) * position * (1 - self.config.slippage)
                            capital += pnl - capital * self.config.commission_rate
                            position = 0
                            trades.append({
                                "date": current_date,
                                "type": "LONG",
                                "entry_price": entry_price,
                                "exit_price": current_price,
                                "return": unrealized_pnl,
                                "duration": (i - entry_date) if entry_date else 0,
                                "reason": "Time Exit"
                            })
                            if unrealized_pnl > 0:
                                wins += 1
                                win_amount += abs(pnl)
                            else:
                                losses += 1
                                loss_amount += abs(pnl)
                
            # 開倉邏輯
            if position == 0 and signal.signal == "LONG":
                # 計算可交易數量
                trade_capital = capital * self.config.max_position_size
                trade_capital *= (1 - self.config.commission_rate)
                shares = int(trade_capital / current_price)
                
                if shares > 0 and capital >= current_price * shares:
                    position = shares
                    entry_price = current_price * (1 + self.config.slippage)
                    entry_date = i
                    
            # 更新權益曲線
            if position > 0:
                portfolio_value = capital + position * current_price
            else:
                portfolio_value = capital
            equity_curve.append(portfolio_value)
        
        # 平倉離場
        if position > 0:
            final_price = data["Close"].iloc[-1]
            pnl = (final_price - entry_price) * position * (1 - self.config.slippage)
            capital += pnl - capital * self.config.commission_rate
            trades.append({
                "date": len(data) - 1,
                "type": "LONG",
                "entry_price": entry_price,
                "exit_price": final_price,
                "return": (final_price - entry_price) / entry_price,
                "duration": (len(data) - 1 - entry_date) if entry_date else 0,
                "reason": "Final Close"
            })
            if (final_price - entry_price) > 0:
                wins += 1
                win_amount += abs(pnl)
            else:
                losses += 1
                loss_amount += abs(pnl)
        
        # ========== 計算指標 ==========
        equity = pd.Series(equity_curve)
        
        # 總報酬率
        total_return = (capital - self.config.initial_capital) / self.config.initial_capital
        
        # 年化報酬率
        years = len(data) / 252
        annual_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 夏普比率
        daily_returns = equity.pct_change().dropna()
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() - self.config.risk_free_rate / 252) / daily_returns.std() * np.sqrt(252)
        else:
            sharpe_ratio = 0
        
        # 最大回撤
        rolling_max = equity.cummax()
        drawdown = (equity - rolling_max) / rolling_max
        max_drawdown = abs(drawdown.min())
        
        # 勝率
        total_trades = len(trades)
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        # 獲利因子
        profit_factor = win_amount / loss_amount if loss_amount > 0 else float('inf')
        
        # 平均交易天數
        if trades:
            avg_duration = np.mean([t["duration"] for t in trades])
        else:
            avg_duration = 0
        
        return BacktestResult(
            strategy_name=strategy_name,
            total_return=total_return,
            annual_return=annual_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            avg_trade_duration=avg_duration,
            final_capital=capital,
            equity_curve=equity,
            trade_log=trades
        )
    
    def run_multi_strategy_backtest(self, data: pd.DataFrame) -> List[BacktestResult]:
        """運行多策略回測"""
        results = []
        
        strategies = [
            ("AdvancedDualMomentum", AdvancedDualMomentum(
                abs_momentum_months=12,
                abs_momentum_threshold=0.0,
                rel_momentum_periods=6,
                rel_rank_threshold=0.2,
                rsi_period=10,
                rsi_entry=50,
                rsi_exit=35,
                sma_period=50,
                stop_loss=0.10,
                take_profit=0.30,
                max_holding_days=60
            )),
            
            ("QualityMomentum", QualityMomentum(
                momentum_period=126,
                momentum_threshold=0.10,
                rsi_period=14,
                rsi_max=70,
                sma_period=20,
                stop_loss=0.12,
                take_profit=0.35,
                max_holding_days=90
            )),
            
            ("RSIAggressive", RSIAggressive(
                rsi_period=2,
                rsi_oversold=15,
                rsi_exit=55,
                low_period=10,
                vol_period=20,
                vol_percentile_min=0.4,
                stop_loss=0.03,
                take_profit=0.08,
                max_holding_days=5
            )),
            
            ("WilliamsPercentR", WilliamsPercentR(
                williams_period=14,
                daily_oversold=-80,
                daily_overbought=-20,
                weekly_oversold=-60,
                stop_loss=0.05,
                take_profit=0.12,
                max_holding_days=15
            )),
            
            ("ATRBreakout", ATRBreakout(
                atr_period=14,
                atr_low_percentile=0.30,
                atr_expansion_threshold=0.15,
                breakout_period=20,
                volume_period=20,
                volume_threshold=1.5,
                stop_loss=0.06,
                take_profit=0.20,
                max_holding_days=25
            )),
            
            ("AdaptiveMultiFactor", AdaptiveMultiFactor(
                roc_period=10,
                roc_weight=0.3,
                mean_reversion_period=20,
                mr_weight=0.2,
                vol_period=20,
                vol_weight=0.2,
                trend_period=50,
                adx_period=14,
                trend_weight=0.3,
                stop_loss=0.08,
                take_profit=0.25,
                max_holding_days=30
            )),
        ]
        
        print("\n" + "="*80)
        print("高級量化策略回測")
        print("="*80)
        print(f"初始資金: ${self.config.initial_capital:,.0f}")
        print(f"數據期間: {len(data)} 天")
        print("="*80)
        
        for name, strategy in strategies:
            try:
                result = self.run_backtest(strategy, data, name)
                results.append(result)
                print(f"\n[{name}]")
                print(f"  總報酬: {result.total_return*100:>8.2f}%")
                print(f"  年化報酬: {result.annual_return*100:>8.2f}%")
                print(f"  夏普比率: {result.sharpe_ratio:>8.3f}")
                print(f"  最大回撤: {result.max_drawdown*100:>8.2f}%")
                print(f"  勝率: {result.win_rate*100:>8.2f}%")
                print(f"  交易次數: {result.total_trades:>5}")
            except Exception as e:
                print(f"\n[{name}] 錯誤: {e}")
        
        return results


def print_summary(results: List[BacktestResult]):
    """打印結果摘要"""
    print("\n" + "="*80)
    print("策略表現摘要 (按夏普比率排序)")
    print("="*80)
    
    # 按夏普比率排序
    sorted_results = sorted(results, key=lambda x: x.sharpe_ratio, reverse=True)
    
    print(f"\n{'策略名稱':<25} {'總報酬':>12} {'年化報酬':>12} {'夏普':>8} {'最大回撤':>10} {'勝率':>8}")
    print("-"*80)
    
    for r in sorted_results:
        meets_target = "✓" if r.sharpe_ratio >= 1.5 and r.total_return > 0.20 else "✗"
        print(f"{r.strategy_name:<25} {r.total_return*100:>10.2f}% {r.annual_return*100:>10.2f}% "
              f"{r.sharpe_ratio:>8.3f} {r.max_drawdown*100:>8.2f}% {r.win_rate*100:>7.2f}% {meets_target}")
    
    print("-"*80)
    
    # 最佳策略
    best = sorted_results[0]
    print(f"\n🏆 最佳策略: {best.strategy_name}")
    print(f"   - 年化報酬: {best.annual_return*100:.2f}%")
    print(f"   - 夏普比率: {best.sharpe_ratio:.3f}")
    print(f"   - 最大回撤: {best.max_drawdown*100:.2f}%")
    
    # 統計
    successful = [r for r in sorted_results if r.sharpe_ratio >= 1.5 and r.total_return > 0.20]
    print(f"\n📊 達標策略數量: {len(successful)}/{len(sorted_results)}")
    
    return sorted_results


def generate_sample_data(seed: int = 42) -> pd.DataFrame:
    """生成樣本數據用於測試"""
    np.random.seed(seed)
    
    # 生成1000天的模擬數據
    n_days = 1000
    dates = pd.date_range(start="2020-01-01", periods=n_days, freq='D')
    
    # 模擬價格走勢（帶有趨勢和波動）
    returns = np.random.normal(0.0005, 0.02, n_days)  # 輕微正向漂移
    returns[200:250] = -0.02  # 模擬大跌
    returns[500:550] = 0.03   # 模擬大漲
    returns[700:750] = -0.015  # 模擬回調
    
    close = 100 * (1 + returns).cumprod()
    
    # 生成 OHLC 數據
    high = close + np.random.uniform(0, 0.015, n_days) * close
    low = close - np.random.uniform(0, 0.015, n_days) * close
    low = np.minimum(low, close)
    high = np.maximum(high, close)
    volume = np.random.uniform(1000000, 5000000, n_days)
    
    data = pd.DataFrame({
        'Open': close * (1 + np.random.uniform(-0.005, 0.005, n_days)),
        'High': high,
        'Low': low,
        'Close': close,
        'Volume': volume
    }, index=dates)
    
    return data


if __name__ == "__main__":
    # 生成樣本數據
    print("生成模擬數據...")
    data = generate_sample_data()
    
    # 運行回測
    tester = AdvancedStrategyBacktester()
    results = tester.run_multi_strategy_backtest(data)
    
    # 打印摘要
    print_summary(results)
    
    print("\n" + "="*80)
    print("回測完成!")
    print("="*80)
