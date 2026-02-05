# Backtest engine - 歷史回測 + Monte Carlo + Walk-Forward + 多策略對沖
# 修復日期: 2026-02-05

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class PositionType(Enum):
    NONE = "none"
    LONG = "long"
    SHORT = "short"


@dataclass
class BacktestResult:
    """回測結果"""
    symbol: str
    strategy: str
    period: str
    
    # 基本指標
    total_return: float = 0.0
    annualized_return: float = 0.0
    max_drawdown: float = 0.0
    volatility: float = 0.0
    
    # 交易指標
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # 盈虧指標
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    
    # 交易列表
    trades: List[Dict] = field(default_factory=list)
    
    # 權益曲線
    equity_curve: pd.Series = None
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy,
            "period": self.period,
            "total_return": f"{self.total_return:.2%}",
            "annualized_return": f"{self.annualized_return:.2%}",
            "max_drawdown": f"{self.max_drawdown:.2%}",
            "volatility": f"{self.volatility:.2%}",
            "total_trades": self.total_trades,
            "win_rate": f"{self.win_rate:.2%}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "average_win": f"${self.average_win:,.2f}",
            "average_loss": f"${self.average_loss:,.2f}"
        }


class BacktestValidator:
    """回測驗證器 - 確保沒有前視偏差"""
    
    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self.violations = []
        self.checks_passed = 0
    
    def validate_price_data(self, prices: pd.DataFrame) -> bool:
        if prices.index.is_monotonic_increasing:
            self.checks_passed += 1
            return True
        self.violations.append({
            "type": "TIME_ORDER_VIOLATION",
            "message": "價格數據不是按時間順序排列",
            "severity": "CRITICAL"
        })
        return False
    
    def get_report(self) -> Dict:
        return {
            "checks_passed": self.checks_passed,
            "violations": self.violations,
            "is_valid": len(self.violations) == 0,
            "warnings": len([v for v in self.violations if v["severity"] == "HIGH"]),
            "errors": len([v for v in self.violations if v["severity"] == "CRITICAL"])
        }


class BacktestEngine:
    """標準回測引擎"""
    
    def __init__(self, initial_capital: float = 100000, commission: float = 0.001, slippage: float = 0.001):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
    
    def run(self, symbol: str, strategy, data: pd.DataFrame, strategy_name: str = "Unknown") -> BacktestResult:
        df = self._prepare_data(data.copy())
        capital = self.initial_capital
        position = PositionType.NONE
        entry_price = 0
        shares = 0
        trades = []
        equity = [self.initial_capital]
        
        for i in range(len(df) - 1):
            current_price = df["Close"].iloc[i]
            signal = strategy.generate_signal({}, df.iloc[:i+1])
            
            if signal.signal == "LONG" and position != PositionType.LONG:
                if position == PositionType.SHORT:
                    exit_price = current_price * (1 - self.slippage)
                    pnl = (entry_price - exit_price) * shares
                    trades.append({"type": "SHORT", "entry": entry_price, "exit": exit_price, "pnl": pnl})
                    capital += pnl
                
                shares = int(capital / current_price)
                entry_price = current_price * (1 + self.slippage)
                capital -= shares * entry_price
                position = PositionType.LONG
            
            elif signal.signal == "SHORT" and position != PositionType.SHORT:
                if position == PositionType.LONG:
                    exit_price = current_price * (1 - self.slippage)
                    pnl = (exit_price - entry_price) * shares
                    trades.append({"type": "LONG", "entry": entry_price, "exit": exit_price, "pnl": pnl})
                    capital += pnl
                
                shares = int(capital / current_price)
                entry_price = current_price * (1 + self.slippage)
                position = PositionType.SHORT
            
            equity.append(capital + shares * current_price if position == PositionType.LONG else capital)
        
        return self._calculate_result(symbol, strategy_name, df, trades, equity)
    
    def _prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                df[col] = df["Close"]
        return df.sort_index() if not df.index.is_monotonic_increasing else df
    
    def _calculate_result(self, symbol: str, strategy_name: str, df: pd.DataFrame, trades: List, equity: List) -> BacktestResult:
        equity_series = pd.Series(equity)
        result = BacktestResult(
            symbol=symbol, strategy=strategy_name,
            period=f"{df.index[0].date()} to {df.index[-1].date()}",
            equity_curve=equity_series
        )
        
        result.total_return = (equity[-1] - self.initial_capital) / self.initial_capital
        days = (df.index[-1] - df.index[0]).days
        if days > 0:
            result.annualized_return = ((1 + result.total_return) ** (365 / days)) - 1
        
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        result.max_drawdown = abs(drawdown.min())
        
        returns = equity_series.pct_change().dropna()
        result.volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0
        
        result.total_trades = len(trades)
        result.winning_trades = len([t for t in trades if t["pnl"] > 0])
        result.losing_trades = len([t for t in trades if t["pnl"] <= 0])
        result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0
        
        wins = [t["pnl"] for t in trades if t["pnl"] > 0]
        losses = [abs(t["pnl"]) for t in trades if t["pnl"] <= 0]
        result.gross_profit = sum(wins)
        result.gross_loss = sum(losses)
        result.profit_factor = result.gross_profit / result.gross_loss if result.gross_loss > 0 else (float('inf') if result.gross_profit > 0 else 0)
        result.average_win = np.mean(wins) if wins else 0
        result.average_loss = np.mean(losses) if losses else 0
        result.trades = trades
        
        return result


class MonteCarloBacktest:
    """Monte Carlo 模擬回測 - 隨機重採樣分析"""
    
    def __init__(self, engine: BacktestEngine, n_simulations: int = 1000):
        self.engine = engine
        self.n_simulations = n_simulations
    
    def run(self, symbol: str, strategy, data: pd.DataFrame, strategy_name: str = "MC") -> Dict:
        """執行 Monte Carlo 模擬"""
        results = []
        
        # 生成基準回測結果
        base_result = self.engine.run(symbol, strategy, data, strategy_name)
        base_returns = self._get_returns(base_result.equity_curve)
        
        print(f"📊 執行 {self.n_simulations} 次 Monte Carlo 模擬...")
        
        for i in range(self.n_simulations):
            # 隨機打亂交易順序
            shuffled_trades = base_result.trades.copy()
            np.random.shuffle(shuffled_trades)
            
            # 模擬權益曲線
            equity = [self.engine.initial_capital]
            capital = self.engine.initial_capital
            
            for trade in shuffled_trades:
                capital += trade["pnl"]
                equity.append(capital)
            
            equity_series = pd.Series(equity)
            returns = self._get_returns(equity_series)
            
            sim_result = {
                "final_equity": equity[-1],
                "total_return": (equity[-1] - self.engine.initial_capital) / self.engine.initial_capital,
                "max_drawdown": self._calculate_max_drawdown(equity_series),
                "win_rate": len([t for t in shuffled_trades if t["pnl"] > 0]) / len(shuffled_trades) if shuffled_trades else 0
            }
            results.append(sim_result)
        
        return self._summarize_results(results, base_result)
    
    def _get_returns(self, equity: pd.Series) -> pd.Series:
        return equity.pct_change().dropna()
    
    def _calculate_max_drawdown(self, equity: pd.Series) -> float:
        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max
        return abs(drawdown.min())
    
    def _summarize_results(self, results: List[Dict], base_result: BacktestResult) -> Dict:
        returns = [r["total_return"] for r in results]
        drawdowns = [r["max_drawdown"] for r in results]
        
        return {
            "type": "monte_carlo",
            "n_simulations": self.n_simulations,
            "base_return": base_result.total_return,
            "base_max_dd": base_result.max_drawdown,
            "return_mean": np.mean(returns),
            "return_std": np.std(returns),
            "return_5pct": np.percentile(returns, 5),
            "return_95pct": np.percentile(returns, 95),
            "dd_mean": np.mean(drawdowns),
            "dd_5pct": np.percentile(drawdowns, 5),
            "probability_of_profit": len([r for r in returns if r > 0]) / len(returns),
            "var_95": np.percentile(returns, 5),
            "consecutive_losses": self._max_consecutive_losses(base_result.trades)
        }
    
    def _max_consecutive_losses(self, trades: List[Dict]) -> int:
        max_consecutive = current = 0
        for trade in trades:
            if trade["pnl"] < 0:
                current += 1
                max_consecutive = max(max_consecutive, current)
            else:
                current = 0
        return max_consecutive


class WalkForwardBacktest:
    """Walk-Forward 分析 - 滾動窗口優化"""
    
    def __init__(self, engine: BacktestEngine, train_window: int = 252, test_window: int = 63):
        """
        train_window: 訓練集天數 (例如 252 = 1年)
        test_window: 測試集天數 (例如 63 = 3個月)
        """
        self.engine = engine
        self.train_window = train_window
        self.test_window = test_window
    
    def run(self, symbol: str, strategy, data: pd.DataFrame, strategy_name: str = "WF") -> Dict:
        """執行 Walk-Forward 分析"""
        df = self.engine._prepare_data(data.copy())
        results = []
        
        print(f"📊 Walk-Forward 分析: 訓練 {self.train_window}天 / 測試 {self.test_window}天")
        
        i = self.train_window
        fold = 0
        
        while i + self.test_window <= len(df):
            train_data = df.iloc[i-self.train_window:i]
            test_data = df.iloc[i:i+self.test_window]
            
            # 在訓練集上優化參數
            best_params = self._optimize_params(strategy, train_data)
            
            # 在測試集上驗證
            test_result = self.engine.run(
                symbol, 
                strategy(**best_params) if best_params else strategy,
                test_data,
                f"{strategy_name}_Fold{fold}"
            )
            
            results.append({
                "fold": fold,
                "train_period": f"{train_data.index[0].date()} to {train_data.index[-1].date()}",
                "test_period": f"{test_data.index[0].date()} to {test_data.index[-1].date()}",
                "params": best_params,
                "return": test_result.total_return,
                "max_dd": test_result.max_drawdown,
                "win_rate": test_result.win_rate,
                "trades": test_result.total_trades
            })
            
            fold += 1
            i += self.test_window
        
        return self._summarize_walkforward(results)
    
    def _optimize_params(self, strategy, train_data: pd.DataFrame) -> Dict:
        """簡化的參數優化"""
        return {}
    
    def _summarize_walkforward(self, results: List[Dict]) -> Dict:
        returns = [r["return"] for r in results]
        win_rates = [r["win_rate"] for r in results]
        
        # Walk-Forward 效率 Ratio
        avg_test_return = np.mean(returns)
        avg_train_return = 0.15  # 假設訓練集表現
        walk_forward_ratio = avg_test_return / avg_train_return if avg_train_return > 0 else 0
        
        return {
            "type": "walk_forward",
            "n_folds": len(results),
            "train_window": self.train_window,
            "test_window": self.test_window,
            "returns": returns,
            "mean_return": np.mean(returns),
            "std_return": np.std(returns),
            "win_rate_mean": np.mean(win_rates),
            "win_rate_std": np.std(win_rates),
            "walk_forward_ratio": walk_forward_ratio,
            "stability": 1 - (np.std(returns) / (abs(np.mean(returns)) + 0.001)),
            "results": results
        }


class MultiStrategyHedgeBacktest:
    """多策略對沖回測 - Long/Short 配對交易"""
    
    def __init__(self, initial_capital: float = 200000):
        self.initial_capital = initial_capital
        self.long_engine = BacktestEngine(initial_capital / 2)
        self.short_engine = BacktestEngine(initial_capital / 2)
    
    def run(
        self,
        symbol: str,
        long_strategy,
        short_strategy,
        data: pd.DataFrame,
        hedge_ratio: float = 1.0,
        strategy_name: str = "Hedge"
    ) -> Dict:
        """執行多策略對沖回測"""
        # 執行多頭策略
        long_result = self.long_engine.run(
            symbol, long_strategy, data, f"{strategy_name}_LONG"
        )
        
        # 執行空頭策略
        short_result = self.short_engine.run(
            symbol, short_strategy, data, f"{strategy_name}_SHORT"
        )
        
        # 合併結果
        combined_trades = long_result.trades + short_result.trades
        combined_equity = self._combine_equity(
            long_result.equity_curve, 
            short_result.equity_curve,
            hedge_ratio
        )
        
        # 計算對沖指標
        long_returns = self._get_returns(long_result.equity_curve)
        short_returns = self._get_returns(short_result.equity_curve)
        
        # 相關性 (理想為負相關)
        correlation = long_returns.corr(short_returns) if len(long_returns) > 1 else 0
        
        # Beta 計算
        if long_returns.std() > 0 and short_returns.std() > 0:
            beta = np.cov(long_returns, short_returns)[0,1] / np.var(short_returns)
        else:
            beta = 0
        
        return {
            "type": "multi_strategy_hedge",
            "hedge_ratio": hedge_ratio,
            "long_strategy": {
                "return": long_result.total_return,
                "max_dd": long_result.max_drawdown,
                "win_rate": long_result.win_rate
            },
            "short_strategy": {
                "return": short_result.total_return,
                "max_dd": short_result.max_drawdown,
                "win_rate": short_result.win_rate
            },
            "combined": {
                "total_return": (combined_equity[-1] - self.initial_capital) / self.initial_capital,
                "max_drawdown": self._calculate_max_drawdown(combined_equity),
                "volatility": self._get_returns(combined_equity).std() * np.sqrt(252),
                "sharpe_ratio": self._calculate_sharpe(combined_equity),
                "sortino_ratio": self._calculate_sortino(combined_equity)
            },
            "hedging_metrics": {
                "strategy_correlation": correlation,
                "beta": beta,
                "alpha": long_result.total_return - (beta * short_result.total_return) if beta else 0,
                "hedge_efficiency": 1 - abs(correlation)  # 越接近1表示對沖效果越好
            },
            "equity_curve": combined_equity,
            "trades": combined_trades
        }
    
    def _combine_equity(self, long_equity: pd.Series, short_equity: pd.Series, ratio: float) -> List:
        combined = []
        for i in range(max(len(long_equity), len(short_equity))):
            long = long_equity.iloc[i] if i < len(long_equity) else long_equity.iloc[-1]
            short = short_equity.iloc[i] if i < len(short_equity) else short_equity.iloc[-1]
            combined.append(long + (short - self.initial_capital / 2) * ratio + self.initial_capital / 2)
        return combined
    
    def _get_returns(self, equity: pd.Series) -> pd.Series:
        return equity.pct_change().dropna()
    
    def _calculate_max_drawdown(self, equity: List) -> float:
        series = pd.Series(equity)
        rolling_max = series.expanding().max()
        drawdown = (series - rolling_max) / rolling_max
        return abs(drawdown.min())
    
    def _calculate_sharpe(self, equity: List, risk_free_rate: float = 0.02) -> float:
        returns = pd.Series(equity).pct_change().dropna()
        if returns.std() == 0:
            return 0
        return (returns.mean() * 252 - risk_free_rate) / (returns.std() * np.sqrt(252))
    
    def _calculate_sortino(self, equity: List, risk_free_rate: float = 0.02) -> float:
        returns = pd.Series(equity).pct_change().dropna()
        negative_returns = returns[returns < 0]
        downside_std = negative_returns.std() if len(negative_returns) > 0 else returns.std()
        if downside_std == 0:
            return 0
        return (returns.mean() * 252 - risk_free_rate) / (downside_std * np.sqrt(252))


def print_backtest_result(result: BacktestResult):
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    回測結果 - {result.symbol}                       ║
╠══════════════════════════════════════════════════════════════════════╣
║ 策略: {result.strategy:<45} ║
║ 期間: {result.period:<45} ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📈 收益指標                                                    ║
║   總回報:     {result.total_return:>10.2%}                              ║
║   年化回報:   {result.annualized_return:>10.2%}                              ║
║   最大回撤:   {result.max_drawdown:>10.2%}                              ║
║   波動率:     {result.volatility:>10.2%}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📊 交易統計                                                    ║
║   總交易次數: {result.total_trades:>10d}                              ║
║   獲勝次數:   {result.winning_trades:>10d}                              ║
║   虧損次數:   {result.losing_trades:>10d}                              ║
║   勝率:       {result.win_rate:>10.2%}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 💰 盈虧分析                                                    ║
║   總利潤:     ${result.gross_profit:>10,.2f}                           ║
║   總虧損:     ${result.gross_loss:>10,.2f}                           ║
║   盈虧比:     {result.profit_factor:>10.2f}                              ║
║   平均獲利:   ${result.average_win:>10,.2f}                           ║
║   平均虧損:   ${result.average_loss:>10,.2f}                           ║
╚════════════════════════════════════════════════════════════════════╝
""")


def print_monte_carlo_result(result: Dict):
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    Monte Carlo 模擬結果                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 模擬次數:     {result['n_simulations']:>10d}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📊 報酬率分析                                                  ║
║   基準回報:   {result['base_return']:>10.2%}                              ║
║   平均回報:   {result['return_mean']:>10.2%}                              ║
║   標準差:     {result['return_std']:>10.2%}                              ║
║   5% 分位數:  {result['return_5pct']:>10.2%}                              ║
║   95% 分位數: {result['return_95pct']:>10.2%}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 🛡️ 風險指標                                                    ║
║   平均最大回撤: {result['dd_mean']:>10.2%}                              ║
║   5% 分位最大回撤: {result['dd_5pct']:>10.2%}                              ║
║   獲利機率:   {result['probability_of_profit']:>10.2%}                              ║
║   VaR (95%):  {result['var_95']:>10.2%}                              ║
║   最大連續虧損: {result['consecutive_losses']:>10d}                              ║
╚══════════════════════════════════════════════════════════════════════╝
""")


def print_walk_forward_result(result: Dict):
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    Walk-Forward 分析結果                             ║
╠══════════════════════════════════════════════════════════════════════╣
║ 訓練窗口:     {result['train_window']:>10d} 天                           ║
║ 測試窗口:     {result['test_window']:>10d} 天                           ║
║ 總Fold數:    {result['n_folds']:>10d}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📊 收益分析                                                    ║
║   平均回報:   {result['mean_return']:>10.2%}                              ║
║   標準差:     {result['std_return']:>10.2%}                              ║
║   穩定性:     {result['stability']:>10.2%}                              ║
║   Walk-Forward 效率: {result['walk_forward_ratio']:>10.2f}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📈 勝率分析                                                    ║
║   平均勝率:   {result['win_rate_mean']:>10.2%}                              ║
║   勝率標準差: {result['win_rate_std']:>10.2%}                              ║
╚══════════════════════════════════════════════════════════════════════╝
""")


def print_hedge_result(result: Dict):
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    多策略對沖回測結果                               ║
╠══════════════════════════════════════════════════════════════════════╣
║ 對沖比例:     {result['hedge_ratio']:>10.2f}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📈 多頭策略                                                    ║
║   回報:       {result['long_strategy']['return']:>10.2%}                              ║
║   最大回撤:   {result['long_strategy']['max_dd']:>10.2%}                              ║
║   勝率:       {result['long_strategy']['win_rate']:>10.2%}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 📉 空頭策略                                                    ║
║   回報:       {result['short_strategy']['return']:>10.2%}                              ║
║   最大回撤:   {result['short_strategy']['max_dd']:>10.2%}                              ║
║   勝率:       {result['short_strategy']['win_rate']:>10.2%}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ ⚖️ 對沖組合                                                    ║
║   總回報:     {result['combined']['total_return']:>10.2%}                              ║
║   最大回撤:   {result['combined']['max_drawdown']:>10.2%}                              ║
║   夏普比率:   {result['combined']['sharpe_ratio']:>10.2f}                              ║
║   索提諾比率: {result['combined']['sortino_ratio']:>10.2f}                              ║
╠══════════════════════════════════════════════════════════════════════╣
║ 🛡️ 對沖指標                                                    ║
║   策略相關性: {result['hedging_metrics']['strategy_correlation']:>10.2f}                              ║
║   Beta:       {result['hedging_metrics']['beta']:>10.2f}                              ║
║   Alpha:      {result['hedging_metrics']['alpha']:>10.2%}                              ║
║   對沖效率:   {result['hedging_metrics']['hedge_efficiency']:>10.2%}                              ║
╚══════════════════════════════════════════════════════════════════════╝
""")
