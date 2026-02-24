# Walk-Forward Optimization Module
# 實現滑窗式前向優化，用於策略參數優化和驗證

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
from itertools import product

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Walk-Forward 配置"""
    in_sample_days: int = 252       # IS 區間天數 (約1年)
    out_sample_days: int = 63       # OOS 區間天數 (約3個月)
    mode: str = "rolling"           # rolling/expanding
    min_is_trades: int = 20        # IS 區間最小交易次數
    min_oos_trades: int = 10       # OOS 區間最小交易次數
    metric: str = "sharpe"          # 優化目標: sharpe/sortino/return/drawdown
    
    def __post_init__(self):
        valid_modes = ["rolling", "expanding"]
        valid_metrics = ["sharpe", "sortino", "return", "drawdown", "profit_factor"]
        
        if self.mode not in valid_modes:
            raise ValueError(f"mode must be one of {valid_modes}")
        if self.metric not in valid_metrics:
            raise ValueError(f"metric must be one of {valid_metrics}")


@dataclass
class WindowResult:
    """單一窗口結果"""
    window_index: int
    is_start_date: str
    is_end_date: str
    oos_start_date: str
    oos_end_date: str
    
    # 數據範圍
    is_data: pd.DataFrame = field(default_factory=list)
    oos_data: pd.DataFrame = field(default_factory=list)
    
    # 指標
    is_metrics: Dict = field(default_factory=dict)
    oos_metrics: Dict = field(default_factory=dict)
    
    # 優化參數
    optimized_params: Dict = field(default_factory=dict)
    
    # 穩健性標記
    is_robust: bool = False
    robustness_score: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "window_index": self.window_index,
            "is_period": f"{self.is_start_date} to {self.is_end_date}",
            "oos_period": f"{self.oos_start_date} to {self.oos_end_date}",
            "is_metrics": self.is_metrics,
            "oos_metrics": self.oos_metrics,
            "optimized_params": self.optimized_params,
            "is_robust": self.is_robust,
            "robustness_score": self.robustness_score
        }


@dataclass
class WalkForwardResult:
    """Walk-Forward 結果"""
    config: WalkForwardConfig
    
    # 窗口結果
    windows: List[WindowResult] = field(default_factory=list)
    
    # 最終參數
    final_params: Dict = field(default_factory=dict)
    
    # 聚合指標
    aggregate_is_metrics: Dict = field(default_factory=dict)
    aggregate_oos_metrics: Dict = field(default_factory=dict)
    
    # 穩健性評估
    overall_robustness: float = 0.0
    is_stable: bool = False
    
    # 運行信息
    total_windows: int = 0
    robust_windows: int = 0
    run_timestamp: str = ""
    
    def to_dict(self) -> dict:
        return {
            "config": {
                "in_sample_days": self.config.in_sample_days,
                "out_sample_days": self.config.out_sample_days,
                "mode": self.config.mode,
                "metric": self.config.metric
            },
            "total_windows": self.total_windows,
            "robust_windows": self.robust_windows,
            "overall_robustness": f"{self.overall_robustness:.2%}",
            "is_stable": self.is_stable,
            "final_params": self.final_params,
            "aggregate_is_metrics": self.aggregate_is_metrics,
            "aggregate_oos_metrics": self.aggregate_oos_metrics,
            "windows": [w.to_dict() for w in self.windows]
        }
    
    def get_best_params(self) -> Dict:
        """獲取最佳參數（基於最穩定的窗口）"""
        if not self.windows:
            return {}
        
        # 按穩健性得分排序
        sorted_windows = sorted(
            self.windows, 
            key=lambda w: w.robustness_score, 
            reverse=True
        )
        
        # 選擇最穩定的參數
        best_window = sorted_windows[0]
        return best_window.optimized_params
    
    def get_consensus_params(self) -> Dict:
        """獲取共識參數（多數窗口選擇的參數）"""
        if not self.windows:
            return {}
        
        # 收集所有參數組合
        param_combinations = []
        for w in self.windows:
            if w.optimized_params:
                # 將字典轉換為可哈希的元組
                param_tuple = tuple(sorted(w.optimized_params.items()))
                param_combinations.append(param_tuple)
        
        if not param_combinations:
            return {}
        
        # 計算最常見的參數組合
        from collections import Counter
        param_counts = Counter(param_combinations)
        most_common = param_counts.most_common(1)[0][0]
        
        return dict(most_common)


class WalkForwardOptimizer:
    """Walk-Forward 優化器"""
    
    def __init__(
        self,
        config: WalkForwardConfig,
        backtest_engine,
        param_grid: Dict[str, List[Any]],
        metric_function: Optional[Callable] = None
    ):
        """
        初始化 Walk-Forward 優化器
        
        Args:
            config: WalkForwardConfig 配置
            backtest_engine: BacktestEngine 實例
            param_grid: 參數網格，格式為 {param_name: [values]}
            metric_function: 自定義指標函數，默認使用 sharpe
        """
        self.config = config
        self.backtest_engine = backtest_engine
        self.param_grid = param_grid
        self.metric_function = metric_function or self._default_metric
        
        # 生成所有參數組合
        self._param_combinations = self._generate_param_combinations()
        
        logger.info(
            f"Walk-Forward Optimizer initialized: "
            f"IS={config.in_sample_days}d, OOS={config.out_sample_days}d, "
            f"mode={config.mode}, {len(self._param_combinations)} param combinations"
        )
    
    def _generate_param_combinations(self) -> List[Dict]:
        """生成所有參數組合"""
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())
        
        combinations = []
        for combo in product(*values):
            param_dict = dict(zip(keys, combo))
            combinations.append(param_dict)
        
        return combinations
    
    def _default_metric(self, backtest_result) -> float:
        """默認指標計算（Sharpe Ratio）"""
        if not backtest_result:
            return -999.0
        
        # 根據配置選擇優化目標
        if self.config.metric == "sharpe":
            # 使用已計算的夏普比率（如果有）
            return getattr(backtest_result, 'sharpe_ratio', 0) or 0
        
        elif self.config.metric == "sortino":
            # Sortino Ratio: 只考慮下行風險
            if hasattr(backtest_result, 'downside_deviation') and backtest_result.downside_deviation > 0:
                return backtest_result.annualized_return / backtest_result.downside_deviation
            return 0
        
        elif self.config.metric == "return":
            return backtest_result.total_return
        
        elif self.config.metric == "drawdown":
            # 最大化回撤（取負值，这样最大化就等于最小化）
            return -backtest_result.max_drawdown
        
        elif self.config.metric == "profit_factor":
            return backtest_result.profit_factor
        
        return 0
    
    def _calculate_robustness_score(
        self,
        is_metrics: Dict,
        oos_metrics: Dict
    ) -> float:
        """
        計算穩健性得分
        比較 IS 和 OOS 區間的表現差異
        """
        if not is_metrics or not oos_metrics:
            return 0.0
        
        # 計算多個維度的穩健性
        scores = []
        
        # 1. 回報衰減率 (Decay Ratio)
        # OOS return / IS return，理想值接近 1
        is_return = is_metrics.get('total_return', 0)
        oos_return = oos_metrics.get('total_return', 0)
        
        if is_return > 0 and oos_return > 0:
            decay_ratio = oos_return / is_return
            # 衰減在 50%-100% 之間為佳
            if 0.5 <= decay_ratio <= 1.0:
                scores.append(decay_ratio)
            elif decay_ratio > 1.0:
                scores.append(1.0)  # OOS 更好，給滿分
            else:
                scores.append(max(0, decay_ratio))  # 衰減低於 50%
        
        # 2. 夏普比率維持率
        is_sharpe = is_metrics.get('sharpe_ratio', 0)
        oos_sharpe = oos_metrics.get('sharpe_ratio', 0)
        
        if is_sharpe > 0 and oos_sharpe > 0:
            sharpe_ratio = oos_sharpe / is_sharpe
            scores.append(min(1.0, sharpe_ratio))
        
        # 3. 交易穩定性
        is_trades = is_metrics.get('total_trades', 0)
        oos_trades = oos_metrics.get('total_trades', 0)
        
        if is_trades > self.config.min_is_trades and oos_trades > self.config.min_oos_trades:
            trade_ratio = min(is_trades, oos_trades) / max(is_trades, oos_trades)
            scores.append(trade_ratio)
        
        # 返回平均得分
        return np.mean(scores) if scores else 0.0
    
    def _create_strategy_with_params(
        self,
        base_strategy,
        params: Dict
    ):
        """創建帶有指定參數的策略副本"""
        import copy
        strategy = copy.copy(base_strategy)
        
        # 更新策略參數
        if hasattr(strategy, 'parameters'):
            strategy.parameters.update(params)
        elif hasattr(strategy, 'params'):
            strategy.params.update(params)
        else:
            # 嘗試直接設置屬性
            for key, value in params.items():
                setattr(strategy, key, value)
        
        return strategy
    
    def _calculate_metrics_summary(self, result) -> Dict:
        """從 BacktestResult 計算指標摘要"""
        return {
            'total_return': result.total_return,
            'annualized_return': result.annualized_return,
            'max_drawdown': result.max_drawdown,
            'volatility': result.volatility,
            'sharpe_ratio': getattr(result, 'sharpe_ratio', 
                        result.annualized_return / result.volatility if result.volatility > 0 else 0),
            'sortino_ratio': getattr(result, 'sortino_ratio', 0),
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'average_win': result.average_win,
            'average_loss': result.average_loss,
            'kelly_position': result.kelly_position
        }
    
    def optimize_window(
        self,
        is_data: pd.DataFrame,
        oos_data: pd.DataFrame,
        strategy
    ) -> WindowResult:
        """
        優化單個窗口
        
        Args:
            is_data: In-Sample 數據
            oos_data: Out-of-Sample 數據
            strategy: 基礎策略實例
            
        Returns:
            WindowResult: 窗口結果
        """
        window_result = WindowResult(
            window_index=0,
            is_start_date=str(is_data.index[0].date()) if hasattr(is_data.index[0], 'date') else str(is_data.index[0]),
            is_end_date=str(is_data.index[-1].date()) if hasattr(is_data.index[-1], 'date') else str(is_data.index[-1]),
            oos_start_date=str(oos_data.index[0].date()) if hasattr(oos_data.index[0], 'date') else str(oos_data.index[0]),
            oos_end_date=str(oos_data.index[-1].date()) if hasattr(oos_data.index[-1], 'date') else str(oos_data.index[-1]),
            is_data=is_data,
            oos_data=oos_data
        )
        
        best_params = {}
        best_is_score = -999.0
        
        # 網格搜索
        for params in self._param_combinations:
            # 創建帶參數的策略
            try:
                test_strategy = self._create_strategy_with_params(strategy, params)
            except Exception as e:
                logger.warning(f"Failed to create strategy with params {params}: {e}")
                continue
            
            # IS 區間回測
            try:
                is_result = self.backtest_engine.run(
                    symbol="WALKFORWARD",
                    strategy=test_strategy,
                    data=is_data,
                    strategy_name="IS_Test"
                )
                
                # 檢查最小交易次數
                if is_result.total_trades < self.config.min_is_trades:
                    continue
                
                # 計算指標
                is_metrics = self._calculate_metrics_summary(is_result)
                is_score = self.metric_function(is_result)
                
            except Exception as e:
                logger.debug(f"IS backtest failed for params {params}: {e}")
                continue
            
            # 追蹤最佳參數
            if is_score > best_is_score:
                best_is_score = is_score
                best_params = params.copy()
                window_result.is_metrics = is_metrics
        
        # 如果沒有找到有效參數，使用默認值
        if not best_params:
            logger.warning("No valid parameters found, using defaults")
            best_params = {k: v[0] for k, v in self.param_grid.items()}
        
        window_result.optimized_params = best_params
        
        # OOS 區間驗證
        try:
            oos_strategy = self._create_strategy_with_params(strategy, best_params)
            oos_result = self.backtest_engine.run(
                symbol="WALKFORWARD",
                strategy=oos_strategy,
                data=oos_data,
                strategy_name="OOS_Test"
            )
            
            window_result.oos_metrics = self._calculate_metrics_summary(oos_result)
            
            # 檢查最小交易次數
            if oos_result.total_trades >= self.config.min_oos_trades:
                window_result.is_robust = True
            
        except Exception as e:
            logger.warning(f"OOS validation failed: {e}")
        
        # 計算穩健性得分
        window_result.robustness_score = self._calculate_robustness_score(
            window_result.is_metrics,
            window_result.oos_metrics
        )
        
        return window_result
    
    def run(
        self,
        data: pd.DataFrame,
        strategy,
        progress_callback: Optional[Callable] = None
    ) -> WalkForwardResult:
        """
        執行 Walk-Forward 優化
        
        Args:
            data: 歷史價格數據
            strategy: 基礎策略實例
            progress_callback: 進度回調函數
            
        Returns:
            WalkForwardResult: 完整結果
        """
        result = WalkForwardResult(
            config=self.config,
            run_timestamp=datetime.now().isoformat()
        )
        
        # 計算窗口數量
        total_days = len(data)
        step_days = self.config.out_sample_days
        
        if total_days < self.config.in_sample_days + self.config.out_sample_days:
            raise ValueError(
                f"Insufficient data: need at least "
                f"{self.config.in_sample_days + self.config.out_sample_days} days, "
                f"got {total_days}"
            )
        
        num_windows = (total_days - self.config.in_sample_days) // step_days
        
        logger.info(
            f"Starting Walk-Forward optimization: "
            f"{num_windows} windows, {total_days} total days"
        )
        
        # 根據模式設置起始位置
        if self.config.mode == "rolling":
            # Rolling: 每個窗口從上一次結束位置開始
            start_idx = 0
        else:
            # Expanding: 起始於 0
            start_idx = 0
        
        current_start = 0
        
        for i in range(num_windows):
            # 計算當前窗口的數據範圍
            if self.config.mode == "rolling":
                is_start = current_start
            else:  # expanding
                is_start = 0
            
            is_end = is_start + self.config.in_sample_days
            oos_start = is_end
            oos_end = oos_start + self.config.out_sample_days
            
            # 確保不超過數據範圍
            if oos_end > len(data):
                logger.info(f"Reached end of data at window {i}")
                break
            
            # 獲取數據切片
            is_data = data.iloc[is_start:is_end].copy()
            oos_data = data.iloc[oos_start:oos_end].copy()
            
            # 執行優化
            logger.info(
                f"Window {i+1}/{num_windows}: "
                f"IS={is_start}:{is_end}, OOS={oos_start}:{oos_end}"
            )
            
            window_result = self.optimize_window(is_data, oos_data, strategy)
            window_result.window_index = i
            
            result.windows.append(window_result)
            
            # 更新進度
            if progress_callback:
                progress_callback(i + 1, num_windows)
            
            # 滾動模式：移動窗口
            if self.config.mode == "rolling":
                current_start = oos_start
        
        # 聚合結果
        result.total_windows = len(result.windows)
        result.robust_windows = sum(1 for w in result.windows if w.is_robust)
        
        # 計算聚合指標
        if result.windows:
            # IS 指標聚合
            is_returns = [w.is_metrics.get('total_return', 0) for w in result.windows if w.is_metrics]
            result.aggregate_is_metrics = {
                'mean_return': np.mean(is_returns) if is_returns else 0,
                'std_return': np.std(is_returns) if is_returns else 0,
                'min_return': np.min(is_returns) if is_returns else 0,
                'max_return': np.max(is_returns) if is_returns else 0
            }
            
            # OOS 指標聚合
            oos_returns = [w.oos_metrics.get('total_return', 0) for w in result.windows if w.oos_metrics]
            result.aggregate_oos_metrics = {
                'mean_return': np.mean(oos_returns) if oos_returns else 0,
                'std_return': np.std(oos_returns) if oos_returns else 0,
                'min_return': np.min(oos_returns) if oos_returns else 0,
                'max_return': np.max(oos_returns) if oos_returns else 0
            }
            
            # 總體穩健性
            robustness_scores = [w.robustness_score for w in result.windows]
            result.overall_robustness = np.mean(robustness_scores) if robustness_scores else 0
            
            # 穩定性判斷：至少 50% 窗口穩健
            result.is_stable = result.robust_windows >= result.total_windows * 0.5
        
        # 計算最終參數
        result.final_params = result.get_consensus_params()
        
        # 如果共識參數为空，使用最佳参数
        if not result.final_params:
            result.final_params = result.get_best_params()
        
        logger.info(
            f"Walk-Forward complete: {result.total_windows} windows, "
            f"{result.robust_windows} robust, stability={result.overall_robustness:.1%}"
        )
        
        return result


def create_walkforward_optimizer(
    in_sample_days: int = 252,
    out_sample_days: int = 63,
    mode: str = "rolling",
    metric: str = "sharpe",
    backtest_engine=None,
    param_grid: Dict[str, List[Any]] = None,
    min_is_trades: int = 20,
    min_oos_trades: int = 10
) -> WalkForwardOptimizer:
    """
    工廠函數：創建 Walk-Forward 優化器
    
    Args:
        in_sample_days: In-Sample 天數
        out_sample_days: Out-of-Sample 天數
        mode: 模式 (rolling/expanding)
        metric: 優化目標
        backtest_engine: BacktestEngine 實例
        param_grid: 參數網格
        min_is_trades: IS 最小交易次數
        min_oos_trades: OOS 最小交易次數
        
    Returns:
        WalkForwardOptimizer: 優化器實例
    """
    config = WalkForwardConfig(
        in_sample_days=in_sample_days,
        out_sample_days=out_sample_days,
        mode=mode,
        metric=metric,
        min_is_trades=min_is_trades,
        min_oos_trades=min_oos_trades
    )
    
    return WalkForwardOptimizer(
        config=config,
        backtest_engine=backtest_engine,
        param_grid=param_grid or {}
    )


# 便捷函數：快速執行 Walk-Forward
def run_walkforward(
    data: pd.DataFrame,
    strategy,
    backtest_engine,
    param_grid: Dict[str, List[Any]],
    in_sample_days: int = 252,
    out_sample_days: int = 63,
    mode: str = "rolling",
    metric: str = "sharpe"
) -> WalkForwardResult:
    """
    快速執行 Walk-Forward 優化
    
    Example:
        >>> import importlib.util
        >>> # 載入 BacktestEngine (因為 backtest.py 與 backtest/ 套件衝突)
        >>> spec = importlib.util.spec_from_file_location("backtest_mod", "backtest.py")
        >>> backtest_mod = importlib.util.module_from_spec(spec)
        >>> spec.loader.exec_module(backtest_mod)
        >>> BacktestEngine = backtest_mod.BacktestEngine
        >>> 
        >>> from backtest.walkforward import run_walkforward
        >>> 
        >>> engine = BacktestEngine(initial_capital=100000)
        >>> param_grid = {
        ...     'rsi_period': [14, 21, 28],
        ...     'rsi_overbought': [70, 80, 90],
        ...     'rsi_oversold': [10, 20, 30]
        ... }
        >>> 
        >>> result = run_walkforward(
        ...     data=price_data,
        ...     strategy=MyStrategy(),
        ...     backtest_engine=engine,
        ...     param_grid=param_grid,
        ...     in_sample_days=252,
        ...     out_sample_days=63
        ... )
        >>> 
        >>> print(result.final_params)
    """
    optimizer = create_walkforward_optimizer(
        in_sample_days=in_sample_days,
        out_sample_days=out_sample_days,
        mode=mode,
        metric=metric,
        backtest_engine=backtest_engine,
        param_grid=param_grid
    )
    
    return optimizer.run(data, strategy)


def get_backtest_engine(project_root: str = None) -> Any:
    """
    輔助函數：正確載入 BacktestEngine
    
    因為 backtest.py 與 backtest/ 套件存在命名衝突，
    需要使用此函數來正確載入 BacktestEngine
    
    Args:
        project_root: 項目根目錄路徑，默認自動檢測
        
    Returns:
        BacktestEngine 類
    """
    import importlib.util
    import os
    
    if project_root is None:
        # 自動檢測項目根目錄
        current = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current)  # backtest/ -> project root
    
    backtest_file = os.path.join(project_root, 'backtest.py')
    
    if not os.path.exists(backtest_file):
        raise FileNotFoundError(f"backtest.py not found at {backtest_file}")
    
    spec = importlib.util.spec_from_file_location("backtest_module", backtest_file)
    backtest_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backtest_module)
    
    return backtest_module.BacktestEngine


# 預設參數網格生成器
def generate_param_grid(**param_ranges) -> Dict[str, List[Any]]:
    """
    生成參數網格
    
    Example:
        >>> param_grid = generate_param_grid(
        ...     rsi_period=[14, 21, 28],
        ...     rsi_oversold=[20, 30, 40],
        ...     rsi_overbought=[60, 70, 80]
        ... )
        >>> # 產生 3x3x3 = 27 種組合
        
    Args:
        **param_ranges: 參數名稱 -> 值列表
        
    Returns:
        參數網格字典
    """
    return dict(param_ranges)
