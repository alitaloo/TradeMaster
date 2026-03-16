#!/usr/bin/env python3
"""
API 模組 - REST API 路由
"""

from .prediction import prediction_bp, init_engine as init_prediction_engine
# NOTE: file-based signals.py is deprecated; DB-based signals_bp.py is the single source of truth
# from .signals import signals_bp  # REMOVED in Stage 1
from .backtests import backtests_bp
from .strategies import strategies_bp
from .portfolio import portfolio_bp
from .stocks import stocks_bp
from .kline import kline_bp
from .futu_kline import futu_bp

__all__ = [
    'prediction_bp', 
    'init_prediction_engine',
    'backtests_bp',
    'strategies_bp',
    'portfolio_bp',
    'stocks_bp',
    'kline_bp',
    'futu_bp'
]
