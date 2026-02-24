# Backtest Module - TradeMaster v2
# 包含策略註冊、批量回測引擎、MySQL記錄
#
# 注意：本專案同時存在 backtest.py (舊版單檔引擎) 與 backtest/ (新版套件)
# 這會造成 `import backtest` 命名衝突。
# 為了向後相容（策略檔常用 `from backtest import PositionType` / `BacktestEngine`），
# 這裡用 importlib 從 backtest.py 載入並 re-export。

from pathlib import Path
import importlib.util

_legacy_path = Path(__file__).resolve().parent.parent / "backtest.py"
_spec = importlib.util.spec_from_file_location("backtest_legacy", str(_legacy_path))
_backtest_legacy = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_backtest_legacy)

# re-export legacy engine/types
BacktestEngine = _backtest_legacy.BacktestEngine
PositionType = getattr(_backtest_legacy, "PositionType", None)
BacktestResult = getattr(_backtest_legacy, "BacktestResult", None)

# Registry - Strategy auto-discovery
from .registry import StrategyRegistry, get_registry
from .strategy_registry import StrategyInfo, discover_strategies, list_strategies

# Batch Engine - Batch backtesting  
from .batch_backtest import BatchBacktestEngine, BacktestTask, BatchResult, create_batch_engine
from .batch_engine import BacktestConfig

# MySQL Recorder - Record to stock_strategies table
from .mysql_recorder import MySQLBacktestRecorder, BacktestRecord, get_recorder, save_backtest_result, save_batch_result

# Database operations
from .database import BacktestDB

# Walk-Forward
from .walkforward import (
    WalkForwardConfig, WindowResult, WalkForwardResult,
    WalkForwardOptimizer, create_walkforward_optimizer, run_walkforward
)

__all__ = [
    # Legacy Engine/Types
    'BacktestEngine',
    'PositionType',
    'BacktestResult',

    # Strategy Registry
    'StrategyRegistry',
    'StrategyInfo',
    'get_registry',
    'discover_strategies',
    'list_strategies',
    
    # Batch Engine
    'BatchBacktestEngine',
    'BacktestTask',
    'BatchResult',
    'create_batch_engine',
    'BacktestConfig',
    
    # MySQL Recorder
    'MySQLBacktestRecorder',
    'BacktestRecord',
    'get_recorder',
    'save_backtest_result',
    'save_batch_result',
    
    # Database
    'BacktestDB',
    
    # Walk-Forward
    'WalkForwardConfig',
    'WindowResult',
    'WalkForwardResult',
    'WalkForwardOptimizer',
    'create_walkforward_optimizer',
    'run_walkforward',
]
