#!/usr/bin/env python3
"""
API 模組 - REST API 路由
"""

from .prediction import prediction_bp, init_engine as init_prediction_engine

__all__ = ['prediction_bp', 'init_prediction_engine']
