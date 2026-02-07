#!/usr/bin/env python3
"""
策略包裝器 - 讓新策略與現有回測框架兼容

Author: TradeMaster Pro
Date: 2026-02-07
"""

import sys
sys.path.insert(0, '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2')

from strategies.advanced_quant_strategies import (
    AdvancedDualMomentum,
    QualityMomentum,
    RSIAggressive,
    WilliamsPercentR,
    ATRBreakout,
    AdaptiveMultiFactor,
    SignalResult,
)


class StrategyWrapper:
    """策略包裝器 - 統一接口"""
    
    def __init__(self, strategy_name: str, **kwargs):
        self.strategy_name = strategy_name
        self.kwargs = kwargs
        
        # 策略類別映射
        strategy_classes = {
            "AdvancedDualMomentum": AdvancedDualMomentum,
            "QualityMomentum": QualityMomentum,
            "RSIAggressive": RSIAggressive,
            "WilliamsPercentR": WilliamsPercentR,
            "ATRBreakout": ATRBreakout,
            "AdaptiveMultiFactor": AdaptiveMultiFactor,
        }
        
        strategy_class = strategy_classes.get(strategy_name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy_name}")
        
        # 過濾有效參數
        valid_params = {}
        import inspect
        sig = inspect.signature(strategy_class.__init__)
        param_names = list(sig.parameters.keys())[1:]  # 排除 self
        
        for k, v in kwargs.items():
            if k in param_names:
                valid_params[k] = v
        
        self.strategy = strategy_class(**valid_params)
    
    def generate_signal(self, ind, data):
        """生成信號 - 兼容舊接口"""
        result = self.strategy.generate_signal(ind, data)
        
        # 轉換為舊格式
        return {
            'signal': result.signal,
            'confidence': result.confidence,
            'price': result.price,
            'reason': result.reason,
            'metadata': result.metadata or {}
        }


def run_strategy_test():
    """運行策略測試"""
    from backtest import BacktestEngine, calculate_indicators
    import pandas as pd
    import numpy as np
    from datetime import datetime
    
    print("\n" + "="*70)
    print("高級策略回測測試")
    print("="*70)
    
    # 測試策略 - 每個策略使用正確的參數
    test_strategies = [
        ("AdvancedDualMomentum", {
            "abs_momentum_months": 12,
            "abs_momentum_threshold": 0.0,
            "rel_momentum_periods": 6,
            "rel_rank_threshold": 0.3,
            "rsi_period": 10,
            "rsi_entry": 50,
            "rsi_exit": 35,
            "sma_period": 50,
            "stop_loss": 0.10,
            "take_profit": 0.30,
            "max_holding_days": 60
        }),
        ("ATRBreakout", {
            "atr_period": 14,
            "atr_low_percentile": 0.30,
            "atr_expansion_threshold": 0.10,
            "breakout_period": 20,
            "volume_period": 20,
            "volume_threshold": 1.3,
            "stop_loss": 0.06,
            "take_profit": 0.20,
            "max_holding_days": 25
        }),
        ("AdaptiveMultiFactor", {
            "roc_period": 10,
            "roc_weight": 0.35,
            "mean_reversion_period": 20,
            "mr_weight": 0.20,
            "vol_period": 20,
            "vol_weight": 0.15,
            "trend_period": 50,
            "adx_period": 14,
            "trend_weight": 0.30,
            "stop_loss": 0.08,
            "take_profit": 0.25,
            "max_holding_days": 30
        }),
    ]
    
    # 生成測試數據
    def generate_test_data(days=500):
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        # 趨勢數據
        returns = []
        for i in range(days):
            if i % 50 < 35:
                r = np.random.normal(0.0012, 0.008)  # 上漲
            else:
                r = np.random.normal(-0.0005, 0.012)  # 回調
            returns.append(r)
        
        close = 100 * np.cumprod(1 + np.array(returns))
        
        return pd.DataFrame({
            'Open': close * (1 + np.random.normal(0, 0.001, days)),
            'High': close * (1 + np.abs(np.random.normal(0.004, 0.003, days))),
            'Low': close * (1 - np.abs(np.random.normal(0.004, 0.003, days))),
            'Close': close,
            'Volume': 1000000 + np.random.randint(500000, 2000000, days)
        }, index=dates)
    
    data = generate_test_data()
    ind = calculate_indicators(data)
    
    # 運行回測
    engine = BacktestEngine(
        initial_capital=100000,
        commission=0.001,
        slippage=0.0005,
        kelly_fraction=0.25
    )
    
    for name, params in test_strategies:
        print(f"\n[{name}]")
        try:
            strategy = StrategyWrapper(name, **params)
            result = engine.run("TEST", strategy, data, name)
            
            print(f"  總報酬: {result.total_return*100:.2f}%")
            print(f"  年化報酬: {result.annual_return*100:.2f}%")
            print(f"  夏普比率: {result.sharpe_ratio:.3f}")
            print(f"  最大回撤: {result.max_drawdown*100:.2f}%")
            print(f"  交易次數: {result.total_trades}")
            
            # 評估
            meets = "✓" if result.sharpe_ratio >= 1.5 and result.total_return > 0.20 else "○"
            print(f"  評估: {meets}")
            
        except Exception as e:
            print(f"  錯誤: {e}")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    run_strategy_test()
