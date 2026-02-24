# Batch Backtest Engine - 批量回測引擎
# 支援多策略、多參數、多標的批量回測

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
import logging
from concurrent.futures import (
    ThreadPoolExecutor,
    ProcessPoolExecutor,
    as_completed,
    wait,
    FIRST_COMPLETED,
    TimeoutError as FuturesTimeoutError,
)
import json
import threading
import time

logger = logging.getLogger(__name__)


# ---------------------------
# ProcessPool worker helpers
# ---------------------------
_WORKER_ENGINE = None


def _get_worker_engine() -> "BatchBacktestEngine":
    """Lazy init a BatchBacktestEngine inside each worker process.

    注意：此 engine 只會存在於 worker process 的記憶體中，用於重用策略註冊與 DB 連線設定。
    """
    global _WORKER_ENGINE
    if _WORKER_ENGINE is None:
        _WORKER_ENGINE = BatchBacktestEngine(max_workers=1)
    return _WORKER_ENGINE


def _process_worker_run_single_task(task: "BacktestTask") -> Dict:
    """Entry for ProcessPoolExecutor.

    不能用 bound method（self._run_single_task）丟進 process，避免 pickling 問題。
    """
    print(f"[BACKTEST] Starting task (worker): strategy={task.strategy_name} symbol={task.symbol} timeframe={task.timeframe}")
    engine = _get_worker_engine()
    # worker 端不使用 main process 的 data_provider（多數情況不可 picklable）
    engine.data_provider = None
    return engine._run_single_task(task)


@dataclass
class BacktestTask:
    """單一回測任務"""
    task_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    start_date: str
    end_date: str
    params: Dict[str, Any]
    
    # 運行結果
    status: str = "pending"  # pending/running/completed/failed
    result: Optional[Dict] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "params": self.params,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "duration_seconds": self.duration_seconds()
        }


@dataclass
class BatchResult:
    """批量回測結果"""
    batch_id: str
    total_tasks: int
    completed: int = 0
    failed: int = 0
    pending: int = 0
    tasks: List[BacktestTask] = field(default_factory=list)
    
    # 聚合指標
    aggregate_metrics: Dict = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def duration_seconds(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.completed / self.total_tasks
    
    def get_results_dataframe(self) -> pd.DataFrame:
        """將結果轉換為 DataFrame"""
        rows = []
        for task in self.tasks:
            if task.result:
                row = {
                    "task_id": task.task_id,
                    "strategy_name": task.strategy_name,
                    "symbol": task.symbol,
                    "timeframe": task.timeframe,
                    "status": task.status,
                    "duration_seconds": task.duration_seconds(),
                }
                row.update(task.result)
                rows.append(row)
        
        return pd.DataFrame(rows)
    
    def to_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "total_tasks": self.total_tasks,
            "completed": self.completed,
            "failed": self.failed,
            "pending": self.pending,
            "success_rate": f"{self.success_rate():.2%}",
            "duration_seconds": self.duration_seconds(),
            "aggregate_metrics": self.aggregate_metrics,
            "tasks": [t.to_dict() for t in self.tasks]
        }


class BatchBacktestEngine:
    """批量回測引擎"""
    
    def __init__(
        self,
        backtest_engine=None,
        data_provider=None,
        max_workers: int = 4,
        timeout: int = 300,
        executor_type: str = "process",  # thread|process
        engine_type: str = "walkforward",  # walkforward|simple|vectorized
        progress_every: int = 100,
    ):
        """
        初始化批量回測引擎
        
        Args:
            backtest_engine: BacktestEngine 實例，如果為 None 需要通過 load_backtest_engine 加載
            data_provider: 數據提供器，回調獲取 K 線數據
            max_workers: 最大並發 worker 數
            timeout: 單個任務超時秒數
            executor_type: 執行器類型（thread|process）
            engine_type: 引擎類型（walkforward|simple|vectorized）
            progress_every: 每完成 N 個 task 輸出一次進度（0 表示不輸出）
        """
        self.backtest_engine = backtest_engine
        self.data_provider = data_provider
        self.max_workers = max_workers
        self.timeout = timeout
        self.executor_type = executor_type
        self.engine_type = engine_type
        self.progress_every = progress_every

        # K線資料快取：避免每個 task 都打一次 MySQL
        # key = (symbol, timeframe, start_date, end_date)
        self._data_cache: Dict[tuple, pd.DataFrame] = {}
        self._data_cache_lock = threading.Lock()
        
        # 策略註冊表
        self._strategy_registry = None
        
        logger.info(
            "BatchBacktestEngine initialized: "
            f"executor_type={self.executor_type}, max_workers={max_workers}, timeout={timeout}s, "
            f"progress_every={self.progress_every}"
        )
    
    def _get_strategy_registry(self):
        """獲取策略註冊表"""
        if self._strategy_registry is None:
            try:
                from ..strategies.registry import get_registry
                self._strategy_registry = get_registry()
            except ImportError:
                from .strategy_registry import get_registry
                self._strategy_registry = get_registry()
        return self._strategy_registry
    
    def _get_backtest_engine(self):
        """獲取或加載 BacktestEngine"""
        if self.backtest_engine is None:
            if self.engine_type == "simple":
                # Use simple backtest engine (no walkforward)
                import importlib.util
                import os
                backtest_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backtest.py')
                spec = importlib.util.spec_from_file_location("backtest_module", backtest_file)
                backtest_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(backtest_module)
                engine_class = backtest_module.BacktestEngine
            elif self.engine_type == "vectorized":
                # Use vectorized backtest engine (fast)
                import importlib.util
                import os
                vectorized_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backtest_vectorized.py')
                spec = importlib.util.spec_from_file_location("vectorized_module", vectorized_file)
                vectorized_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(vectorized_module)
                engine_class = vectorized_module.VectorizedBacktestEngine
            else:
                # Use walkforward engine (with param optimization)
                from .walkforward import get_backtest_engine
                engine_class = get_backtest_engine()
            
            # Instantiate the engine with default parameters
            self.backtest_engine = engine_class(
                initial_capital=100000,
                commission=0.0015,
                slippage=0.001,
                kelly_fraction=0.25
            )
        return self.backtest_engine
    
    def create_tasks(
        self,
        strategies: Union[str, List[str]],
        symbols: List[str],
        timeframes: Union[str, List[str]] = ["1d"],
        param_grids: Optional[Dict[str, Dict[str, List[Any]]]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[BacktestTask]:
        """
        創建批量回測任務
        
        Args:
            strategies: 策略名稱或列表
            symbols: 股票代碼列表
            timeframes: 時間框架列表
            param_grids: 參數網格，格式為 {strategy_name: {param: [values]}}
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            BacktestTask 列表
        """
        # Normalize strategies
        if isinstance(strategies, str):
            strategies = [strategies]
        
        # Normalize timeframes
        if isinstance(timeframes, str):
            timeframes = [timeframes]
        
        # Get param grids for each strategy
        if param_grids is None:
            param_grids = {}
        
        tasks = []
        task_counter = 0
        
        for strategy_name in strategies:
            # Get param grid for this strategy
            strategy_param_grid = param_grids.get(strategy_name, {})
            
            # Generate all param combinations
            if strategy_param_grid:
                param_combinations = self._generate_param_combinations(strategy_param_grid)
            else:
                param_combinations = [{}]
            
            for symbol in symbols:
                for timeframe in timeframes:
                    for params in param_combinations:
                        task_id = f"task_{task_counter:04d}"
                        task = BacktestTask(
                            task_id=task_id,
                            strategy_name=strategy_name,
                            symbol=symbol,
                            timeframe=timeframe,
                            start_date=start_date or "",
                            end_date=end_date or "",
                            params=params
                        )
                        tasks.append(task)
                        task_counter += 1
        
        logger.info(f"Created {len(tasks)} backtest tasks")
        return tasks
    
    def _generate_param_combinations(self, param_grid: Dict[str, List[Any]]) -> List[Dict]:
        """生成參數組合"""
        from itertools import product
        
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        
        combinations = []
        for combo in product(*values):
            combinations.append(dict(zip(keys, combo)))
        
        return combinations
    
    def run_batch(
        self,
        tasks: List[BacktestTask],
        batch_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None
    ) -> BatchResult:
        """
        執行批量回測
        
        Args:
            tasks: 回測任務列表
            batch_id: 批次 ID
            progress_callback: 進度回調函數
            
        Returns:
            BatchResult 結果
        """
        if batch_id is None:
            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        result = BatchResult(
            batch_id=batch_id,
            total_tasks=len(tasks),
            pending=len(tasks),
            start_time=datetime.now()
        )
        
        # Initialize tasks in result
        result.tasks = tasks
        
        logger.info(f"Starting batch {batch_id} with {len(tasks)} tasks")
        
        def _maybe_print_progress(force: bool = False):
            if self.progress_every is None or self.progress_every <= 0:
                return
            done = result.completed + result.failed
            if (not force) and (done % self.progress_every != 0):
                return

            elapsed = (datetime.now() - result.start_time).total_seconds() if result.start_time else 0.0
            rate = done / elapsed if elapsed > 0 else 0.0
            remaining = result.total_tasks - done
            eta = remaining / rate if rate > 0 else float('inf')

            eta_str = f"{eta:.1f}s" if np.isfinite(eta) else "NA"
            print(
                f"[batch {batch_id}] progress: {done}/{result.total_tasks} "
                f"(completed={result.completed}, failed={result.failed}, pending={result.pending}) "
                f"elapsed={elapsed:.1f}s ETA={eta_str}",
                flush=True,
            )

        # Decide executor type
        executor_type = (self.executor_type or "thread").lower()
        if executor_type not in ("thread", "process"):
            raise ValueError(f"Invalid executor_type: {self.executor_type}")

        # data_provider 通常不可 picklable；若使用 process 模式，強制回到 thread 模式
        if executor_type == "process" and self.data_provider is not None:
            logger.warning(
                "executor_type=process with data_provider is not supported (likely not picklable). "
                "Falling back to thread mode."
            )
            executor_type = "thread"

        # Mark all tasks running
        for task in tasks:
            task.start_time = datetime.now()
            task.status = "running"

        ExecutorCls = ProcessPoolExecutor if executor_type == "process" else ThreadPoolExecutor

        # Submit & collect with timeout protection (per-task)
        with ExecutorCls(max_workers=self.max_workers) as executor:
            future_to_task: Dict[Any, BacktestTask] = {}
            future_start_ts: Dict[Any, float] = {}

            for task in tasks:
                if executor_type == "process":
                    future = executor.submit(_process_worker_run_single_task, task)
                else:
                    future = executor.submit(self._run_single_task, task)
                future_to_task[future] = task
                future_start_ts[future] = time.monotonic()

            pending_futures = set(future_to_task.keys())

            while pending_futures:
                done, not_done = wait(pending_futures, timeout=1.0, return_when=FIRST_COMPLETED)

                # Handle newly completed
                for future in done:
                    pending_futures.discard(future)
                    task = future_to_task[future]

                    try:
                        task_result = future.result()
                        if task_result is not None:
                            task.status = "completed"
                            task.result = task_result
                            result.completed += 1
                        else:
                            task.status = "failed"
                            task.error = "No result returned"
                            result.failed += 1
                    except Exception as e:
                        task.status = "failed"
                        task.error = str(e)
                        result.failed += 1
                        logger.error(f"Task {task.task_id} failed: {e}")

                    task.end_time = datetime.now()
                    result.pending = len(tasks) - result.completed - result.failed

                    if progress_callback:
                        progress_callback(result)
                    _maybe_print_progress(force=False)

                # Timeout check for still-running tasks
                now = time.monotonic()
                timed_out = []
                for future in list(not_done):
                    start_ts = future_start_ts.get(future, now)
                    if (now - start_ts) > self.timeout:
                        timed_out.append(future)

                for future in timed_out:
                    pending_futures.discard(future)
                    task = future_to_task[future]

                    # best-effort cancel; if already running, cancel() will be False
                    try:
                        future.cancel()
                    except Exception:
                        pass

                    task.status = "failed"
                    task.error = f"Timeout after {self.timeout}s"
                    task.end_time = datetime.now()
                    result.failed += 1
                    result.pending = len(tasks) - result.completed - result.failed
                    logger.error(f"Task {task.task_id} timeout after {self.timeout}s")

                    if progress_callback:
                        progress_callback(result)
                    _maybe_print_progress(force=True)

            # do not block on potentially-hung tasks (best effort)
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # cancel_futures not available on older python
                executor.shutdown(wait=False)

        result.end_time = datetime.now()
        _maybe_print_progress(force=True)
        
        # Calculate aggregate metrics
        result.aggregate_metrics = self._calculate_aggregate_metrics(result)
        
        logger.info(
            f"Batch {batch_id} completed: "
            f"{result.completed}/{result.total_tasks} succeeded "
            f"in {result.duration_seconds():.1f}s"
        )
        
        return result
    
    def _run_single_task(self, task: BacktestTask) -> Optional[Dict]:
        """執行單個回測任務"""
        print(f"[BACKTEST] Starting task: strategy={task.strategy_name} symbol={task.symbol} timeframe={task.timeframe}")
        try:
            # Get backtest engine
            engine = self._get_backtest_engine()
            
            # Get strategy
            registry = self._get_strategy_registry()
            strategy_class = registry.get_strategy(task.strategy_name)
            
            if strategy_class is None:
                raise ValueError(f"Strategy not found: {task.strategy_name}")
            
            # Get data from provider
            if self.data_provider:
                df = self.data_provider(
                    task.symbol,
                    task.timeframe,
                    task.start_date,
                    task.end_date
                )
            else:
                # Use default data loading
                df = self._load_data(task.symbol, task.timeframe, task.start_date, task.end_date)
            
            if df is None or df.empty:
                raise ValueError(f"No data for {task.symbol} {task.timeframe}")
            
            # Run backtest
            strategy = strategy_class(**task.params)
            result = engine.run(task.symbol, strategy, df, task.strategy_name)
            
            # Extract metrics
            metrics = self._extract_metrics(result)
            metrics["task_id"] = task.task_id
            
            return metrics
            
        except Exception as e:
            logger.error(f"Task {task.task_id} error: {e}")
            raise
    
    def _load_data(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str
    ) -> Optional[pd.DataFrame]:
        """加載 K 線數據（預設實現）"""

        cache_key = (symbol, timeframe, start_date or "", end_date or "")
        with self._data_cache_lock:
            cached = self._data_cache.get(cache_key)
        if cached is not None:
            # 回傳 copy 避免策略在 df 上做 inplace 操作造成互相污染
            return cached.copy()

        # Try to load from database
        try:
            import pymysql
            
            conn = pymysql.connect(
                host='localhost',
                user='alita',
                password='alitamysql',
                database='trademaster',
                charset='utf8mb4'
            )
            
            query = """
                SELECT symbol, interval_val as timeframe, timestamp as dt, 
                       open_price as open, high_price as high, low_price as low, close_price as close, volume
                FROM kline_cache 
                WHERE symbol = %s AND interval_val = %s
            """
            
            params = [symbol, timeframe]
            
            if start_date:
                query += " AND timestamp >= %s"
                params.append(start_date)
            if end_date:
                query += " AND timestamp <= %s"
                params.append(end_date)
            
            query += " ORDER BY timestamp"
            
            df = pd.read_sql(query, conn, params=params)
            conn.close()
            
            if not df.empty:
                # Rename columns to match backtest engine expectations (capitalized)
                df = df.rename(columns={
                    'open': 'Open', 
                    'high': 'High', 
                    'low': 'Low', 
                    'close': 'Close',
                    'volume': 'Volume'
                })
                # Set index (timestamp 欄位在 DB 可能有秒/微秒混合格式)
                df['dt'] = pd.to_datetime(df['dt'], errors='coerce', format='mixed')
                df = df.dropna(subset=['dt'])
                if df.empty:
                    return None
                df.set_index('dt', inplace=True)
                # Drop symbol and timeframe columns as they're not needed for backtest
                df = df.drop(columns=['symbol', 'timeframe'], errors='ignore')

                # cache
                with self._data_cache_lock:
                    self._data_cache[cache_key] = df

                return df.copy()
            
        except Exception as e:
            logger.warning(f"Failed to load data from DB: {e}")
        
        return None
    
    def _extract_metrics(self, result) -> Dict:
        """從回測結果提取指標"""
        metrics = {}
        
        if hasattr(result, 'metrics'):
            metrics = result.metrics.copy() if isinstance(result.metrics, dict) else {}
        
        if hasattr(result, 'total_return'):
            metrics['total_return'] = result.total_return
        if hasattr(result, 'annualized_return'):
            metrics['annualized_return'] = result.annualized_return
        if hasattr(result, 'volatility'):
            metrics['volatility'] = result.volatility
            # Calculate sharpe ratio if we have return and volatility
            if hasattr(result, 'annualized_return') and result.volatility > 0:
                metrics['sharpe_ratio'] = result.annualized_return / result.volatility
        if hasattr(result, 'max_drawdown'):
            metrics['max_drawdown'] = result.max_drawdown
        if hasattr(result, 'win_rate'):
            metrics['win_rate'] = result.win_rate
        if hasattr(result, 'total_trades'):
            metrics['total_trades'] = result.total_trades
        if hasattr(result, 'profit_factor'):
            metrics['profit_factor'] = result.profit_factor
        
        return metrics
    
    def _calculate_aggregate_metrics(self, result: BatchResult) -> Dict:
        """計算聚合指標"""
        if not result.tasks:
            return {}
        
        completed_results = [t.result for t in result.tasks if t.result]
        
        if not completed_results:
            return {}
        
        # Calculate averages
        numeric_keys = set()
        for r in completed_results:
            numeric_keys.update(k for k, v in r.items() if isinstance(v, (int, float)))
        
        aggregate = {}
        for key in numeric_keys:
            values = [r[key] for r in completed_results if key in r and r[key] is not None]
            if values:
                aggregate[f"avg_{key}"] = np.mean(values)
                aggregate[f"min_{key}"] = np.min(values)
                aggregate[f"max_{key}"] = np.max(values)
                aggregate[f"std_{key}"] = np.std(values)
        
        return aggregate
    
    def run_single(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str = "1d",
        params: Optional[Dict[str, Any]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Optional[Dict]:
        """
        運行單次回測
        
        Args:
            strategy_name: 策略名稱
            symbol: 股票代碼
            timeframe: 時間框架
            params: 策略參數
            start_date: 開始日期
            end_date: 結束日期
            
        Returns:
            回測結果指標
        """
        tasks = self.create_tasks(
            strategies=[strategy_name],
            symbols=[symbol],
            timeframes=[timeframe],
            param_grids={strategy_name: params} if params else None,
            start_date=start_date,
            end_date=end_date
        )
        
        if not tasks:
            return None
        
        task = tasks[0]
        task.start_time = datetime.now()
        task.status = "running"
        
        try:
            result = self._run_single_task(task)
            task.status = "completed"
            task.result = result
            return result
        except Exception as e:
            task.status = "failed"
            task.error = str(e)
            return None
        finally:
            task.end_time = datetime.now()


def create_batch_engine(
    max_workers: int = 4,
    timeout: int = 300,
    executor_type: str = "process",
    progress_every: int = 100,
) -> BatchBacktestEngine:
    """工廠函數：創建批量回測引擎"""
    return BatchBacktestEngine(
        max_workers=max_workers,
        timeout=timeout,
        executor_type=executor_type,
        progress_every=progress_every,
    )
