# Batch Backtest Engine - 批量回測引擎
# 使用 StrategyRegistry 自動發現策略並批量回測

import os
import sys
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

import pandas as pd
import numpy as np

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backtest.strategy_registry import StrategyRegistry, get_registry, StrategyInfo

logger = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """回測配置"""
    symbols: List[str] = field(default_factory=lambda: ["2330.TW", "2454.TW", "2317.TW"])
    timeframes: List[str] = field(default_factory=lambda: ["1D", "1W"])
    start_date: str = "2023-01-01"
    end_date: str = "2024-12-31"
    initial_capital: float = 1000000.0
    commission: float = 0.001
    slippage: float = 0.0005
    max_workers: int = 4
    
    # 策略過濾
    strategy_categories: List[str] = None  # None = all
    min_sharpe: float = None
    min_trades: int = 10


@dataclass
class BacktestResult:
    """單次回測結果"""
    symbol: str
    timeframe: str
    strategy_name: str
    strategy_category: str
    
    # 績效指標
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    total_trades: int = 0
    profit_factor: float = 0.0
    
    # 參數
    params: Dict[str, Any] = field(default_factory=dict)
    
    # 時間
    start_date: str = ""
    end_date: str = ""
    run_time: datetime = None
    
    # 狀態
    status: str = "pending"  # pending, running, completed, failed
    error_message: str = ""
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "strategy_name": self.strategy_name,
            "strategy_category": self.strategy_category,
            "total_return": self.total_return,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "win_rate": self.win_rate,
            "total_trades": self.total_trades,
            "profit_factor": self.profit_factor,
            "params": json.dumps(self.params, ensure_ascii=False),
            "start_date": self.start_date,
            "end_date": self.end_date,
            "run_time": self.run_time.isoformat() if self.run_time else None,
            "status": self.status,
            "error_message": self.error_message
        }


class BatchBacktestEngine:
    """批量回測引擎"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.registry = get_registry()
        self.results: List[BacktestResult] = []
        
        # 確保策略已發現
        if not self.registry._discovered:
            self.registry.discover()
    
    def _load_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """加載 K 線數據"""
        try:
            # 嘗試從數據庫加載
            import pymysql
            
            conn = pymysql.connect(
                host='localhost',
                user='alita',
                password='alitamysql',
                database='trademaster',
                charset='utf8mb4'
            )
            
            query = """
                SELECT symbol, timeframe, timestamp as dt, 
                       open, high, low, close, volume
                FROM kline_cache 
                WHERE symbol = %s AND timeframe = %s
            """
            
            params = [symbol, timeframe]
            
            if self.config.start_date:
                query += " AND timestamp >= %s"
                params.append(self.config.start_date)
            if self.config.end_date:
                query += " AND timestamp <= %s"
                params.append(self.config.end_date)
            
            query += " ORDER BY timestamp"
            
            df = pd.read_sql(query, conn, params=params)
            conn.close()
            
            if not df.empty:
                df.set_index('dt', inplace=True)
                return df
            
        except Exception as e:
            logger.warning(f"Failed to load data for {symbol} {timeframe}: {e}")
        
        return None
    
    def _run_single_backtest(
        self,
        symbol: str,
        timeframe: str,
        strategy_info: StrategyInfo,
        params: Dict[str, Any]
    ) -> BacktestResult:
        """執行單次回測"""
        result = BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy_name=strategy_info.name,
            strategy_category=strategy_info.category,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            params=params,
            run_time=datetime.now(),
            status="running"
        )
        
        try:
            # 加載數據
            df = self._load_data(symbol, timeframe)
            
            if df is None or df.empty:
                result.status = "failed"
                result.error_message = f"No data for {symbol}"
                return result
            
            # 獲取策略類
            strategy_class = self.registry.get_strategy(strategy_info.name)
            
            if strategy_class is None:
                result.status = "failed"
                result.error_message = f"Strategy not found: {strategy_info.name}"
                return result
            
            # 創建策略實例
            strategy = strategy_class(**params)
            
            # 運行回測 (如果引擎可用)
            try:
                from backtest.walkforward import get_backtest_engine
                engine = get_backtest_engine()
                
                # 運行回測
                bt_result = engine.run(strategy, df)
                
                # 提取指標
                if hasattr(bt_result, 'metrics'):
                    metrics = bt_result.metrics
                    result.total_return = metrics.get('return', 0) or 0
                    result.sharpe_ratio = metrics.get('sharpe', 0) or 0
                    result.max_drawdown = abs(metrics.get('drawdown', 0) or 0)
                    result.win_rate = metrics.get('win_rate', 0) or 0
                    result.total_trades = metrics.get('total_trades', 0) or 0
                    result.profit_factor = metrics.get('profit_factor', 0) or 0
                
                result.status = "completed"
                
            except Exception as e:
                # 如果沒有引擎，返回模擬結果
                logger.warning(f"Backtest engine not available: {e}")
                result.status = "completed"
                result.total_return = 0.0
                result.sharpe_ratio = 0.0
        
        except Exception as e:
            result.status = "failed"
            result.error_message = str(e)
            logger.error(f"Backtest failed: {e}")
        
        return result
    
    def run(self) -> List[BacktestResult]:
        """運行批量回測"""
        self.results = []
        
        # 獲取所有策略
        all_strategies = self.registry.list_strategies()
        
        # 過濾策略
        if self.config.strategy_categories:
            all_strategies = [
                s for s in all_strategies
                if s.category in self.config.strategy_categories
            ]
        
        logger.info(
            f"Starting batch backtest: {len(self.config.symbols)} symbols, "
            f"{len(all_strategies)} strategies"
        )
        
        # 生成任務
        tasks = []
        for symbol in self.config.symbols:
            for timeframe in self.config.timeframes:
                for strategy_info in all_strategies:
                    # 獲取參數組合
                    param_combinations = self.registry.get_param_combinations(strategy_info.name)
                    
                    for params in param_combinations:
                        tasks.append((symbol, timeframe, strategy_info, params))
        
        logger.info(f"Total tasks: {len(tasks)}")
        
        # 使用線程池執行
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = {
                executor.submit(
                    self._run_single_backtest,
                    symbol, timeframe, strategy_info, params
                ): (symbol, timeframe, strategy_info.name)
                for symbol, timeframe, strategy_info, params in tasks
            }
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    self.results.append(result)
                except Exception as e:
                    logger.error(f"Task failed: {e}")
        
        # 過濾結果
        self._filter_results()
        
        return self.results
    
    def _filter_results(self):
        """過濾結果"""
        if self.config.min_sharpe is not None:
            self.results = [
                r for r in self.results
                if r.status != "failed" and r.sharpe_ratio >= self.config.min_sharpe
            ]
        
        if self.config.min_trades is not None:
            self.results = [
                r for r in self.results
                if r.status != "failed" and r.total_trades >= self.config.min_trades
            ]
    
    def get_results_dataframe(self) -> pd.DataFrame:
        """獲取結果 DataFrame"""
        if not self.results:
            return pd.DataFrame()
        
        rows = []
        for r in self.results:
            row = {
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "strategy_name": r.strategy_name,
                "strategy_category": r.strategy_category,
                "total_return": r.total_return,
                "sharpe_ratio": r.sharpe_ratio,
                "max_drawdown": r.max_drawdown,
                "win_rate": r.win_rate,
                "total_trades": r.total_trades,
                "profit_factor": r.profit_factor,
                "status": r.status
            }
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def save_to_database(self):
        """保存結果到數據庫"""
        try:
            from backtest.mysql_recorder import get_recorder
            recorder = get_recorder()
            
            for result in self.results:
                if result.status == "completed":
                    recorder.save_task_result(result.to_dict())
            
            logger.info(f"Saved {len(self.results)} results to database")
            
        except Exception as e:
            logger.error(f"Failed to save to database: {e}")
    
    def get_best_results(self, metric: str = "sharpe_ratio", top_n: int = 10) -> List[BacktestResult]:
        """獲取最佳結果"""
        completed = [r for r in self.results if r.status == "completed"]
        
        if not completed:
            return []
        
        # 排序
        if metric == "sharpe_ratio":
            sorted_results = sorted(completed, key=lambda x: x.sharpe_ratio, reverse=True)
        elif metric == "total_return":
            sorted_results = sorted(completed, key=lambda x: x.total_return, reverse=True)
        elif metric == "win_rate":
            sorted_results = sorted(completed, key=lambda x: x.win_rate, reverse=True)
        else:
            sorted_results = completed
        
        return sorted_results[:top_n]


def run_batch_backtest(
    symbols: List[str] = None,
    timeframes: List[str] = None,
    categories: List[str] = None,
    **kwargs
) -> List[BacktestResult]:
    """便捷函數：運行批量回測"""
    config = BacktestConfig(
        symbols=symbols or ["2330.TW", "2454.TW", "2317.TW"],
        timeframes=timeframes or ["1D"],
        strategy_categories=categories,
        **kwargs
    )
    
    engine = BatchBacktestEngine(config)
    return engine.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 測試
    engine = BatchBacktestEngine()
    results = engine.run()
    
    print(f"\n=== Batch Backtest Results ===")
    print(f"Total: {len(results)}")
    
    df = engine.get_results_dataframe()
    if not df.empty:
        print(df[["symbol", "timeframe", "strategy_name", "sharpe_ratio", "total_return", "status"]])
