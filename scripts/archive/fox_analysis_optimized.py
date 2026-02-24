#!/usr/bin/env python3
"""
Fox Analysis Script - OPTIMIZED VERSION
Fox 分析腳本 - 讀取持倉、新聞權重、市場數據，執行風控，計算信心度，寫入交易信號
自動判斷冬令時/夏令時
三週期共振策略：5m, 1h, 1d 三個週期同時出現信號才執行

用法:
    python fox_analysis.py [--dry-run]

API Base: http://localhost:8080/api/v1
"""

import requests
import json
import logging
import os
import sys
import mysql.connector
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import argparse

# 導入市場時間判斷模組
try:
    from market_hours import should_update_kline, is_dst_us
    HAS_MARKET_HOURS = True
except ImportError:
    HAS_MARKET_HOURS = False

# 繞過代理設定 (本機調用不需要代理)
os.environ.setdefault('NO_PROXY', 'localhost,127.0.0.1')

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# API 配置
API_BASE = 'http://localhost:8080/api/v1'

# 風控參數
RISK_PARAMS = {
    'VIX_THRESHOLD': 30.0,        # VIX 閾值，超過則風險高
    'MARKET_DROP_THRESHOLD': -3.0, # 市場跌幅閾值，超過則風險高
    'NEWS_WEIGHT_THRESHOLD': 5,    # 新聞權重閾值，超過則異常
    'MIN_CONFIDENCE': 0.6,         # 最低信心度閾值
    'HIGH_CONFIDENCE': 0.8,        # 高信心度閾值
    'STOP_LOSS_PCT': 5.0,          # 止損百分比
}

# 數據庫配置 - 從統一配置導入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from config.database import MYSQL_CONFIG as DB_CONFIG
except ImportError:
    # 備用配置
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster'
    }

# 股票策略緩存
_stock_strategy_cache = {}
_cache_loaded = False


def load_stock_strategies() -> dict:
    """從 MySQL 加載股票最佳策略"""
    global _stock_strategy_cache, _cache_loaded
    
    if _cache_loaded:
        return _stock_strategy_cache
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT symbol, timeframe, indicator, params
            FROM stock_strategies
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        for row in rows:
            symbol = row['symbol']
            tf = row['timeframe']
            indicator = row['indicator']
            params_json = row['params']
            
            # 解析參數
            if isinstance(params_json, str):
                import json
                params_extra = json.loads(params_json)
            else:
                params_extra = params_json or {}
            
            # 根據指標類型設置默認參數
            params = get_indicator_params(indicator)
            params.update(params_extra)
            
            if symbol not in _stock_strategy_cache:
                _stock_strategy_cache[symbol] = {}
            
            _stock_strategy_cache[symbol][tf] = {
                'indicator': indicator,
                'params': params
            }
        
        _cache_loaded = True
        logger.info(f"✅ 已從 MySQL 加載 {len(_stock_strategy_cache)} 支股票的策略配置")
        
    except Exception as e:
        logger.error(f"❌ 加載股票策略失敗: {e}")
        # 使用默認配置
        _stock_strategy_cache = {}
    
    return _stock_strategy_cache


def get_indicator_params(indicator: str) -> dict:
    """根據指標名稱返回默認參數"""
    params_map = {
        'RSI': {'period': 14, 'oversold': 30, 'overbought': 70},
        'RSI_7': {'period': 7, 'oversold': 25, 'overbought': 75},
        'MACD': {'fast': 12, 'slow': 26, 'signal': 9},
        'SMA_Cross': {'fast': 10, 'slow': 50},
        'EMA_Cross': {'fast': 12, 'slow': 26},
        'Bollinger': {'period': 20, 'std': 2},
        'Stochastic': {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80},
        'CCI': {'period': 20, 'oversold': -100, 'overbought': 100},
        'Williams_R': {'period': 14, 'oversold': -80, 'overbought': -20},
        # 組合策略參數
        'RSI+MACD': {'period': 14, 'fast': 12, 'slow': 26},
        'RSI+BB': {'period': 14, 'bb_period': 20},
        'RSI+STOCH': {'period': 14, 'k_period': 14},
        'MACD+SMA': {'fast': 12, 'slow': 26, 'fast_ma': 10, 'slow_ma': 50},
        'MACD+EMA': {'fast': 12, 'slow': 26, 'fast_ema': 12, 'slow_ema': 26},
        'BB+STOCH': {'bb_period': 20, 'k_period': 14},
        'CCI+WR': {'cci_period': 20, 'wr_period': 14},
        'RSI+MACD+BB': {'period': 14, 'fast': 12, 'slow': 26, 'bb_period': 20},
    }
    return params_map.get(indicator, {})


def get_stock_strategy(symbol: str, timeframe: str) -> dict:
    """獲取單支股票指定週期的最佳策略"""
    strategies = load_stock_strategies()
    
    # 嘗試獲取該股票的策略
    if symbol in strategies and timeframe in strategies[symbol]:
        return strategies[symbol][timeframe]
    
    # 回退到默認配置
    default_config = {
        '5m': {'indicator': 'RSI', 'params': {'period': 14, 'oversold': 30, 'overbought': 70}},
        '1h': {'indicator': 'Stochastic', 'params': {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80}},
        '1d': {'indicator': 'Bollinger', 'params': {'period': 20, 'std': 2}},
    }
    return default_config.get(timeframe, {'indicator': 'RSI', 'params': {}})


# 保持向後兼容的默認配置
TIMEFRAME_CONFIG = {
    '5m': {'indicator': 'RSI', 'params': {'period': 14, 'oversold': 30, 'overbought': 70}},
    '1h': {'indicator': 'Stochastic', 'params': {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80}},
    '1d': {'indicator': 'Bollinger', 'params': {'period': 20, 'std': 2}},
}


def api_get(endpoint: str, params: dict = None) -> dict:
    """發送 GET 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


def api_post(endpoint: str, data: dict) -> dict:
    """發送 POST 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.post(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


# ==================== 統一指標計算模組 ====================

class IndicatorCalculator:
    """
    統一指標計算器 - 整合所有指標計算邏輯
    解決代碼重複問題，提供詳細日誌輸出
    """
    
    # 指標數值緩存 (用於日誌記錄)
    _indicator_values: Dict[str, float] = {}
    
    @classmethod
    def reset_values(cls):
        """重置指標數值緩存"""
        cls._indicator_values = {}
    
    @classmethod
    def get_values(cls) -> Dict[str, float]:
        """獲取當前指標數值"""
        return cls._indicator_values.copy()
    
    @classmethod
    def calculate(cls, df: pd.DataFrame, indicator: str, params: dict = None, 
                  log_level: str = 'DEBUG') -> Tuple[Optional[int], Optional[Dict]]:
        """
        統一指標計算入口
        
        Args:
            df: K線數據
            indicator: 指標名稱 (如 'RSI', 'MACD', 'Bollinger')
            params: 指標參數
            log_level: 日誌級別 ('DEBUG', 'INFO', 'WARNING')
        
        Returns:
            (signal, details): 信號值 和 詳細信息字典
                signal: 1 (BUY), -1 (SELL), 0 (HOLD), None (無數據)
                details: {'indicator': str, 'value': float, 'threshold': dict, 'reason': str}
        """
        if params is None:
            params = {}
        
        # 重置緩存
        cls._indicator_values = {}
        
        # 處理組合策略
        if '+' in indicator:
            return cls._calculate_composite(df, indicator, params, log_level)
        
        # 單一指標策略分發
        method_name = f'_calc_{indicator}'
        if hasattr(cls, method_name):
            return getattr(cls, method_name)(df, params, log_level)
        
        # 未知指標
        logger.warning(f"  ⚠️ 未知指標: {indicator}")
        return 0, {'indicator': indicator, 'value': None, 'reason': 'unknown_indicator'}
    
    @classmethod
    def _calculate_composite(cls, df: pd.DataFrame, indicator: str, 
                            params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """
        計算組合策略信號
        只有當所有指標信號一致時才返回信號，否則返回 HOLD
        """
        indicators = indicator.split('+')
        signals = []
        all_details = {}
        
        for ind in indicators:
            ind = ind.strip()
            signal, details = cls.calculate(df, ind, params, log_level)
            if signal is None:
                return None, {'indicator': indicator, 'value': None, 'reason': 'no_data'}
            signals.append(signal)
            all_details[ind] = details
        
        # 所有信號必須一致才算有效
        if len(set(signals)) == 1:
            reason = f"composite_{indicator}: all一致"
            return signals[0], {
                'indicator': indicator, 
                'value': signals[0],
                'details': all_details,
                'reason': reason
            }
        
        # 信號不一致
        return 0, {
            'indicator': indicator,
            'value': 0,
            'details': all_details,
            'reason': f"composite: 信號不一致 {signals}"
        }
    
    # ==================== 各指標計算方法 ====================
    
    @classmethod
    def _calc_RSI(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 RSI 信號"""
        period = params.get('period', 14)
        oversold = params.get('oversold', 30)
        overbought = params.get('overbought', 70)
        
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        latest = rsi.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['RSI'] = round(latest, 2) if not pd.isna(latest) else None
        
        if pd.isna(latest):
            return None, {'indicator': 'RSI', 'value': None, 'reason': 'no_data'}
        
        # 判斷信號
        if latest < oversold:
            signal = 1
            reason = f"RSI={latest:.2f} < oversold({oversold}) → BUY"
        elif latest > overbought:
            signal = -1
            reason = f"RSI={latest:.2f} > overbought({overbought}) → SELL"
        else:
            signal = 0
            reason = f"RSI={latest:.2f} [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'RSI',
            'value': round(latest, 2),
            'threshold': {'oversold': oversold, 'overbought': overbought},
            'reason': reason
        }
    
    @classmethod
    def _calc_RSI_7(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 RSI_7 信號 (短週期)"""
        params_7 = params.copy()
        params_7['period'] = 7
        params_7['oversold'] = 25
        params_7['overbought'] = 75
        return cls._calc_RSI(df, params_7, log_level)
    
    @classmethod
    def _calc_Stochastic(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算隨機指標信號"""
        k_period = params.get('k_period', 14)
        d_period = params.get('d_period', 3)
        oversold = params.get('oversold', 20)
        overbought = params.get('overbought', 80)
        
        low_min = df['low'].rolling(window=k_period).min()
        high_max = df['high'].rolling(window=k_period).max()
        k = 100 * (df['close'] - low_min) / (high_max - low_min)
        d = k.rolling(window=d_period).mean()
        
        latest_k = k.iloc[-1]
        latest_d = d.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['Stochastic_K'] = round(latest_k, 2) if not pd.isna(latest_k) else None
        cls._indicator_values['Stochastic_D'] = round(latest_d, 2) if not pd.isna(latest_d) else None
        
        if pd.isna(latest_k) or pd.isna(latest_d):
            return None, {'indicator': 'Stochastic', 'value': None, 'reason': 'no_data'}
        
        if latest_k < oversold and latest_d < oversold:
            signal = 1
            reason = f"STOCH K={latest_k:.2f}, D={latest_d:.2f} < {oversold} → BUY"
        elif latest_k > overbought and latest_d > overbought:
            signal = -1
            reason = f"STOCH K={latest_k:.2f}, D={latest_d:.2f} > {overbought} → SELL"
        else:
            signal = 0
            reason = f"STOCH K={latest_k:.2f}, D={latest_d:.2f} [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'Stochastic',
            'value': round(latest_k, 2),
            'd_value': round(latest_d, 2),
            'threshold': {'oversold': oversold, 'overbought': overbought},
            'reason': reason
        }
    
    @classmethod
    def _calc_Bollinger(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算布林帶信號"""
        period = params.get('bb_period', params.get('period', 20))
        std_dev = params.get('std', 2)
        
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        latest_close = df['close'].iloc[-1]
        latest_upper = upper.iloc[-1]
        latest_lower = lower.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['BB_Upper'] = round(latest_upper, 2) if not pd.isna(latest_upper) else None
        cls._indicator_values['BB_Lower'] = round(latest_lower, 2) if not pd.isna(latest_lower) else None
        cls._indicator_values['BB_Close'] = round(latest_close, 2)
        
        if pd.isna(latest_upper):
            return None, {'indicator': 'Bollinger', 'value': None, 'reason': 'no_data'}
        
        if latest_close < latest_lower:
            signal = 1
            reason = f"Price={latest_close:.2f} < BB_Lower={latest_lower:.2f} → BUY"
        elif latest_close > latest_upper:
            signal = -1
            reason = f"Price={latest_close:.2f} > BB_Upper={latest_upper:.2f} → SELL"
        else:
            signal = 0
            reason = f"Price={latest_close:.2f} within BB [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'Bollinger',
            'value': round(latest_close, 2),
            'upper': round(latest_upper, 2),
            'lower': round(latest_lower, 2),
            'reason': reason
        }
    
    @classmethod
    def _calc_MACD(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 MACD 信號"""
        fast = params.get('fast', 12)
        slow = params.get('slow', 26)
        signal_period = params.get('signal', 9)
        
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal_period).mean()
        histogram = macd - macd_signal
        
        latest_hist = histogram.iloc[-1]
        latest_macd = macd.iloc[-1]
        latest_signal = macd_signal.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['MACD'] = round(latest_macd, 4) if not pd.isna(latest_macd) else None
        cls._indicator_values['MACD_Signal'] = round(latest_signal, 4) if not pd.isna(latest_signal) else None
        cls._indicator_values['MACD_Hist'] = round(latest_hist, 4) if not pd.isna(latest_hist) else None
        
        if pd.isna(latest_hist):
            return None, {'indicator': 'MACD', 'value': None, 'reason': 'no_data'}
        
        if latest_hist > 0:
            signal = 1
            reason = f"MACD_Hist={latest_hist:.4f} > 0 (金叉) → BUY"
        elif latest_hist < 0:
            signal = -1
            reason = f"MACD_Hist={latest_hist:.4f} < 0 (死叉) → SELL"
        else:
            signal = 0
            reason = f"MACD_Hist={latest_hist:.4f} = 0 [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'MACD',
            'value': round(latest_hist, 4),
            'macd': round(latest_macd, 4),
            'signal': round(latest_signal, 4),
            'reason': reason
        }
    
    @classmethod
    def _calc_SMA_Cross(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 SMA 交叉信號"""
        fast_ma = params.get('fast_ma', params.get('fast', 10))
        slow_ma = params.get('slow_ma', params.get('slow', 50))
        
        sma_fast = df['close'].rolling(fast_ma).mean()
        sma_slow = df['close'].rolling(slow_ma).mean()
        
        latest_diff = sma_fast.iloc[-1] - sma_slow.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['SMA_Fast'] = round(sma_fast.iloc[-1], 2) if not pd.isna(sma_fast.iloc[-1]) else None
        cls._indicator_values['SMA_Slow'] = round(sma_slow.iloc[-1], 2) if not pd.isna(sma_slow.iloc[-1]) else None
        cls._indicator_values['SMA_Diff'] = round(latest_diff, 2) if not pd.isna(latest_diff) else None
        
        if pd.isna(latest_diff):
            return None, {'indicator': 'SMA_Cross', 'value': None, 'reason': 'no_data'}
        
        if latest_diff > 0:
            signal = 1
            reason = f"SMA{fast_ma}={sma_fast.iloc[-1]:.2f} > SMA{slow_ma}={sma_slow.iloc[-1]:.2f} → BUY"
        elif latest_diff < 0:
            signal = -1
            reason = f"SMA{fast_ma}={sma_fast.iloc[-1]:.2f} < SMA{slow_ma}={sma_slow.iloc[-1]:.2f} → SELL"
        else:
            signal = 0
            reason = f"SMA Cross = 0 [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'SMA_Cross',
            'value': round(latest_diff, 2),
            'fast': round(sma_fast.iloc[-1], 2),
            'slow': round(sma_slow.iloc[-1], 2),
            'reason': reason
        }
    
    @classmethod
    def _calc_EMA_Cross(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 EMA 交叉信號"""
        fast_ema = params.get('fast_ema', params.get('fast', 12))
        slow_ema = params.get('slow_ema', params.get('slow', 26))
        
        ema_fast = df['close'].ewm(span=fast_ema).mean()
        ema_slow = df['close'].ewm(span=slow_ema).mean()
        
        latest_diff = ema_fast.iloc[-1] - ema_slow.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['EMA_Fast'] = round(ema_fast.iloc[-1], 2) if not pd.isna(ema_fast.iloc[-1]) else None
        cls._indicator_values['EMA_Slow'] = round(ema_slow.iloc[-1], 2) if not pd.isna(ema_slow.iloc[-1]) else None
        cls._indicator_values['EMA_Diff'] = round(latest_diff, 2) if not pd.isna(latest_diff) else None
        
        if pd.isna(latest_diff):
            return None, {'indicator': 'EMA_Cross', 'value': None, 'reason': 'no_data'}
        
        if latest_diff > 0:
            signal = 1
            reason = f"EMA{fast_ema}={ema_fast.iloc[-1]:.2f} > EMA{slow_ema}={ema_slow.iloc[-1]:.2f} → BUY"
        elif latest_diff < 0:
            signal = -1
            reason = f"EMA{fast_ema}={ema_fast.iloc[-1]:.2f} < EMA{slow_ema}={ema_slow.iloc[-1]:.2f} → SELL"
        else:
            signal = 0
            reason = f"EMA Cross = 0 [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'EMA_Cross',
            'value': round(latest_diff, 2),
            'fast': round(ema_fast.iloc[-1], 2),
            'slow': round(ema_slow.iloc[-1], 2),
            'reason': reason
        }
    
    @classmethod
    def _calc_CCI(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 CCI 信號"""
        period = params.get('cci_period', params.get('period', 20))
        oversold = params.get('oversold', -100)
        overbought = params.get('overbought', 100)
        
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma_tp = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        cci = (tp - sma_tp) / (0.015 * mad)
        
        latest = cci.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['CCI'] = round(latest, 2) if not pd.isna(latest) else None
        
        if pd.isna(latest):
            return None, {'indicator': 'CCI', 'value': None, 'reason': 'no_data'}
        
        if latest < oversold:
            signal = 1
            reason = f"CCI={latest:.2f} < {oversold} → BUY"
        elif latest > overbought:
            signal = -1
            reason = f"CCI={latest:.2f} > {overbought} → SELL"
        else:
            signal = 0
            reason = f"CCI={latest:.2f} [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'CCI',
            'value': round(latest, 2),
            'threshold': {'oversold': oversold, 'overbought': overbought},
            'reason': reason
        }
    
    @classmethod
    def _calc_Williams_R(cls, df: pd.DataFrame, params: dict, log_level: str) -> Tuple[Optional[int], Optional[Dict]]:
        """計算 Williams %R 信號"""
        period = params.get('wr_period', params.get('period', 14))
        oversold = params.get('oversold', -80)
        overbought = params.get('overbought', -20)
        
        highest = df['high'].rolling(period).max()
        lowest = df['low'].rolling(period).min()
        wr = -100 * (highest - df['close']) / (highest - lowest)
        
        latest = wr.iloc[-1]
        
        # 記錄數值
        cls._indicator_values['Williams_R'] = round(latest, 2) if not pd.isna(latest) else None
        
        if pd.isna(latest):
            return None, {'indicator': 'Williams_R', 'value': None, 'reason': 'no_data'}
        
        if latest < oversold:
            signal = 1
            reason = f"WR={latest:.2f} < {oversold} → BUY"
        elif latest > overbought:
            signal = -1
            reason = f"WR={latest:.2f} > {overbought} → SELL"
        else:
            signal = 0
            reason = f"WR={latest:.2f} [中性]"
        
        cls._log(log_level, reason)
        
        return signal, {
            'indicator': 'Williams_R',
            'value': round(latest, 2),
            'threshold': {'oversold': oversold, 'overbought': overbought},
            'reason': reason
        }
    
    @staticmethod
    def _log(level: str, message: str):
        """統一日誌輸出"""
        if level == 'DEBUG':
            logger.debug(message)
        elif level == 'INFO':
            logger.info(message)
        elif level == 'WARNING':
            logger.warning(message)
        else:
            logger.info(message)


# ==================== 舊函數兼容層 (已廢棄，建議移除) ====================

def calculate_single_indicator_signal(df: pd.DataFrame, indicator: str, params: dict) -> Optional[int]:
    """
    [已廢棄] 請使用 IndicatorCalculator.calculate()
    保留此函數是為了向後兼容
    """
    signal, _ = IndicatorCalculator.calculate(df, indicator, params)
    return signal


def calculate_composite_signal(df: pd.DataFrame, indicator: str, params: dict) -> int:
    """
    [已廢棄] 請使用 IndicatorCalculator.calculate()
    """
    signal, _ = IndicatorCalculator.calculate(df, indicator, params)
    return signal if signal is not None else 0


# ==================== 三週期信號計算 (重構後) ====================

def get_kline_data(symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
    """從數據庫獲取 K 線數據"""
    try:
        # 添加 US. 前綴（如果沒有）
        if not symbol.startswith('US.'):
            symbol = f'US.{symbol}'
        
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        query = """
            SELECT timestamp, open_price, high_price, low_price, close_price, volume
            FROM kline_cache
            WHERE symbol = %s AND interval_val = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        
        cursor.execute(query, (symbol, timeframe, limit))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
        df = df.sort_values('timestamp')  # oldest first for calculation
        return df
        
    except Exception as e:
        logger.error(f"獲取 K 線數據失敗: {symbol} {timeframe} - {e}")
        return None


def get_timeframe_signal(symbol: str, timeframe: str, verbose: bool = True) -> Tuple[Optional[int], Optional[Dict]]:
    """
    計算單個週期的信號 (重構後版本)
    
    Returns: 
        (signal, details): 
            signal: 1 (BUY), -1 (SELL), 0 (HOLD), None (無數據)
            details: 詳細指標信息 {'indicator': str, 'values': dict, 'reason': str}
    """
    # 從 MySQL 獲取該股票該週期的最佳策略
    config = get_stock_strategy(symbol, timeframe)
    if not config:
        return None, None
    
    indicator = config['indicator']
    params = config['params']
    
    # 5分線多取一根數據，用倒數第二根（上一根確定的K線）
    limit = 201 if timeframe == '5m' else 200
    
    df = get_kline_data(symbol, timeframe, limit=limit)
    if df is None or len(df) < 30:
        logger.warning(f"  ⚠️ {symbol} {timeframe} 數據不足")
        return None, None
    
    # 5分線：跳過最後一根（正在變動），用上一根確定的K線
    if timeframe == '5m' and len(df) > 1:
        df = df.iloc[:-1]  # 移除最後一根
    
    try:
        # 使用統一的指標計算器
        log_level = 'INFO' if verbose else 'DEBUG'
        signal, details = IndicatorCalculator.calculate(df, indicator, params, log_level)
        
        # 添加策略信息到 details
        if details:
            details['strategy'] = {
                'indicator': indicator,
                'params': params,
                'timeframe': timeframe
            }
        
        return signal, details
        
    except Exception as e:
        logger.error(f"  ❌ 計算信號失敗: {symbol} {timeframe} - {e}")
        return None, None


def get_multi_timeframe_signals(symbol: str, verbose: bool = True) -> Dict:
    """
    獲取三個週期的信號
    Returns: {'5m': signal, '1h': signal, '1d': signal, 'consensus': signal, 'details': {...}}
    """
    # 確保 symbol 有 US. 前綴
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'
    
    signals = {}
    details_all = {}
    
    for tf in ['5m', '1h', '1d']:
        signal, details = get_timeframe_signal(symbol, tf, verbose)
        signals[tf] = signal
        details_all[tf] = details
        
        signal_str = {1: 'BUY', -1: 'SELL', 0: 'HOLD', None: 'N/A'}.get(signal, 'N/A')
        
        # 輸出詳細日誌
        if verbose and details:
            indicator_name = details.get('indicator', tf)
            reason = details.get('reason', '')
            logger.info(f"  📊 {symbol} {tf} [{indicator_name}]: {signal_str} - {reason}")
        else:
            logger.info(f"  📊 {symbol} {tf}: {signal_str}")
    
    # 計算共識信號
    s5m, s1h, s1d = signals.get('5m'), signals.get('1h'), signals.get('1d')
    
    # 必須三個週期都有數據
    if s5m is None or s1h is None or s1d is None:
        signals['consensus'] = None
        signals['reason'] = '數據不足'
        signals['method'] = 'none'
        signals['details'] = details_all
        return signals
    
    # 檢查市場波動性 (VIX)
    market_volatility = check_market_volatility()
    signals['market_volatile'] = market_volatility
    
    # ====== 三週期共振邏輯 ======
    # 優先：必須三個週期都同意
    # 備用：市場波動大時，允許 2/3 週期同意
    
    # 三個週期都買入 (優先)
    if s5m == 1 and s1h == 1 and s1d == 1:
        signals['consensus'] = 1
        signals['reason'] = '三週期共振買入'
        signals['method'] = '3/3'
    # 三個週期都賣出 (優先)
    elif s5m == -1 and s1h == -1 and s1d == -1:
        signals['consensus'] = -1
        signals['reason'] = '三週期共振賣出'
        signals['method'] = '3/3'
    # 2/3 週期同意 (市場波動時)
    elif market_volatility:
        # 檢查 2/3 組合
        buy_count = sum(1 for s in [s5m, s1h, s1d] if s == 1)
        sell_count = sum(1 for s in [s5m, s1h, s1d] if s == -1)
        
        if buy_count >= 2:
            signals['consensus'] = 1
            signals['reason'] = f'2/3週期共振買入 (市場波動放寬)'
            signals['method'] = '2/3'
        elif sell_count >= 2:
            signals['consensus'] = -1
            signals['reason'] = f'2/3週期共振賣出 (市場波動放寬)'
            signals['method'] = '2/3'
        else:
            signals['consensus'] = 0
            signals['reason'] = f'信號不一致 ({s5m}/{s1h}/{s1d})'
            signals['method'] = 'none'
    else:
        signals['consensus'] = 0
        signals['reason'] = f'信號不一致 ({s5m}/{s1h}/{s1d})'
        signals['method'] = 'none'
    
    signals['details'] = details_all
    
    return signals


# ==================== 以下為原有函數，保持不變 ====================

def check_market_volatility() -> bool:
    """
    檢查市場波動性
    當 VIX > 30 或市場近期大跌時返回 True
    """
    try:
        # 嘗試從 API 獲取 VIX
        result = api_get('/market/vix')
        if result.get('status') == 'ok':
            vix = result.get('vix', 0)
            if vix > 30:
                logger.info(f"   📈 VIX={vix} > 30，市場波動大")
                return True
        
        # 也可以用標普 500 近期表現判斷
        result = api_get('/market/index/SPY')
        if result.get('status') == 'ok':
            change = result.get('change_percent', 0)
            # 大跌 > 3% 或 大漲 > 3% 都算波動大
            if abs(change) > 3:
                logger.info(f"   📈 SPY 單日漲跌 {change:.2f}%，市場波動大")
                return True
        
    except Exception as e:
        logger.debug(f"   ⚠️ 無法獲取市場波動性: {e}")
    
    return False


def api_put(endpoint: str, data: dict) -> dict:
    """發送 PUT 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.put(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API PUT 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


def get_positions() -> List[Dict]:
    """獲取持倉列表"""
    logger.info("📊 獲取持倉數據...")
    result = api_get('/positions')
    
    if result.get('status') == 'ok':
        positions = result.get('positions', [])
        logger.info(f"   找到 {len(positions)} 個持倉")
        return positions
    else:
        logger.warning(f"   獲取持倉失敗: {result.get('message')}")
        return []


def get_watchlist() -> List[str]:
    """從 MySQL 獲取 WATCHLIST 股票列表"""
    logger.info("📋 獲取 WATCHLIST 股票列表...")
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='alita',
            password='alitamysql',
            database='trademaster'
        )
        cursor = conn.cursor(dictionary=True)
        # enabled = 1 表示啟用的股票
        cursor.execute("SELECT symbol FROM stocks WHERE enabled = 1 ORDER BY symbol")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        symbols = [row['symbol'] for row in rows]
        logger.info(f"   找到 {len(symbols)} 檔 WATCHLIST 股票")
        return symbols
    except Exception as e:
        logger.error(f"   獲取 WATCHLIST 失敗: {e}")
        return []


def get_news_weight(symbol: str, hours: int = 24) -> Dict:
    """獲取股票新聞權重"""
    result = api_get(f'/news/weight/{symbol}', {'hours': hours})
    
    if result.get('status') == 'ok':
        return result
    else:
        logger.warning(f"   獲取新聞權重失敗: {result.get('message')}")
        return {
            'status': 'ok',
            'symbol': symbol,
            'total_weight': 0,
            'news_count': 0,
            'breakdown': {'positive': 0, 'negative': 0, 'neutral': 0}
        }


def get_market_data() -> Dict:
    """獲取市場數據"""
    logger.info("📈 獲取市場數據...")
    result = api_get('/market')
    
    if result.get('status') == 'ok':
        markets = result.get('markets', [])
        market_dict = {m['type'].lower(): m['value'] for m in markets}
        logger.info(f"   市場數據: {market_dict}")
        return market_dict
    else:
        logger.warning(f"   獲取市場數據失敗: {result.get('message')}")
        return {}


def check_market_risk(market_data: Dict) -> Tuple[bool, str]:
    """
    檢查市場風險
    返回: (是否通過, 原因)
    """
    vix = market_data.get('vix')
    market_drop = market_data.get('market_drop', 0)
    
    # 檢查 VIX
    if vix is not None and vix > RISK_PARAMS['VIX_THRESHOLD']:
        return False, f"VIX={vix} > {RISK_PARAMS['VIX_THRESHOLD']} (市場恐慌)"
    
    # 檢查市場跌幅
    if market_drop < RISK_PARAMS['MARKET_DROP_THRESHOLD']:
        return False, f"市場跌幅={market_drop}% < {RISK_PARAMS['MARKET_DROP_THRESHOLD']}% (市場大跌)"
    
    return True, "市場風險檢查通過"


def check_news_risk(news_weight: int) -> Tuple[bool, str]:
    """
    檢查新聞風險
    返回: (是否通過, 原因)
    """
    if news_weight > RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']:
        return False, f"新聞權重={news_weight} > {RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']} (新聞異常)"
    
    return True, "新聞風險檢查通過"


def calculate_confidence(position: Dict, news_data: Dict, market_data: Dict) -> float:
    """
    計算信心度 (0.0 - 1.0)
    
    信心度因素:
    - 持倉回報率: 正回報 + 信心，負回報 - 信心
    - 新聞權重: 低權重 + 信心，高權重 - 信心
    - 市場環境: VIX 低 + 信心，市場漲 + 信心
    """
    confidence = 0.5  # 基礎信心度
    
    # 1. 持倉回報率因素 (+/- 0.2)
    return_pct = position.get('return_pct', 0) or 0
    if return_pct > 10:
        confidence += 0.2
    elif return_pct > 5:
        confidence += 0.1
    elif return_pct > 0:
        confidence += 0.05
    elif return_pct > -5:
        confidence -= 0.1
    else:
        confidence -= 0.2
    
    # 2. 新聞因素 (+/- 0.2)
    news_weight = news_data.get('total_weight', 0) or 0
    if news_weight == 0:
        confidence += 0.1  # 無新聞 = 穩定
    elif news_weight < 3:
        confidence += 0.05
    elif news_weight > 7:
        confidence -= 0.2
    
    # 新聞情感
    breakdown = news_data.get('breakdown', {})
    positive = breakdown.get('positive', 0)
    negative = breakdown.get('negative', 0)
    if positive > negative:
        confidence += 0.1
    elif negative > positive:
        confidence -= 0.1
    
    # 3. 市場環境因素 (+/- 0.2)
    vix = market_data.get('vix')
    if vix is not None:
        if vix < 15:
            confidence += 0.2
        elif vix < 20:
            confidence += 0.1
        elif vix > 25:
            confidence -= 0.1
        elif vix > 30:
            confidence -= 0.2
    
    market_drop = market_data.get('market_drop', 0) or 0
    if market_drop > 1:
        confidence += 0.1
    elif market_drop < -2:
        confidence -= 0.15
    
    # 限制在 0.1 - 0.95 範圍內
    confidence = max(0.1, min(0.95, confidence))
    
    return round(confidence, 2)


def decide_signal(confidence: float, news_ok: bool, market_ok: bool) -> Tuple[str, str]:
    """
    決定交易信號
    返回: (信號類型, 原因)
    
    信號類型:
    - BUY: 買入/加倉
    - SELL: 賣出/減倉
    - HOLD: 不操作
    """
    # 必須通過風控
    if not market_ok:
        return 'HOLD', '市場風險過高'
    if not news_ok:
        return 'HOLD', '新聞風險過高'
    
    # 信心度決定信號
    if confidence >= RISK_PARAMS['HIGH_CONFIDENCE']:
        # 高信心，根據持倉回報決定
        return 'BUY', f'高信心度 ({confidence})'
    elif confidence >= RISK_PARAMS['MIN_CONFIDENCE']:
        # 中等信心，觀望
        return 'HOLD', f'中等信心度 ({confidence})'
    else:
        # 低信心，考慮賣出
        return 'SELL', f'低信心度 ({confidence})'


def create_signal(position: Dict, signal_type: str, confidence: float, 
                  news_ok: bool, market_ok: bool, reason: str,
                  stop_loss_pct: float = None) -> Dict:
    """創建交易信號 (自動去重)"""
    symbol = position.get('symbol')
    current_price = position.get('average_cost', 0) or 0
    
    # 計算止損價格
    if stop_loss_pct is None:
        stop_loss_pct = RISK_PARAMS['STOP_LOSS_PCT']
    
    # 計算建議股數 (假設每次操作 10% 倉位)
    total_capital = position.get('total_capital') or 50000
    quantity = int(total_capital * 0.1 / current_price) if current_price > 0 else 0
    
    signal_data = {
        'symbol': symbol,
        'strategy_type': 'fox_analysis',
        'signal_type': signal_type,
        'price': current_price,
        'quantity': quantity,
        'confidence': confidence,
        'status': 'PENDING',
        'news_weight': position.get('news_weight', 0),
        'stop_loss': stop_loss_pct,
        'risk_score': 1 if (news_ok and market_ok) else 0,
        'metadata': {
            'reason': reason,
            'market_ok': market_ok,
            'news_ok': news_ok,
            'created_at': datetime.now().isoformat()
        }
    }
    
    logger.info(f"   📝 創建信號: {symbol} {signal_type} (信心度: {confidence})")
    return api_post('/signals', signal_data)


def analyze_position(position: Dict, market_data: Dict) -> Dict:
    """分析單個持倉"""
    symbol = position.get('symbol')
    logger.info(f"\n🔍 分析持倉: {symbol}")
    
    # 0. 三週期共振檢查 (先檢查!)
    logger.info(f"   🌐 檢查三週期信號...")
    tf_signals = get_multi_timeframe_signals(symbol)
    consensus = tf_signals.get('consensus')
    reason = tf_signals.get('reason', '未知')
    
    # 無共振 → 直接寫入 HOLD，不調用 Agent
    if consensus is None or consensus == 0:
        logger.info(f"   ⏭️ 無共振，直接寫入 HOLD: {reason}")
        return {
            'symbol': symbol,
            'signal_type': 'HOLD',
            'confidence': 0.5,
            'news_ok': True,
            'market_ok': True,
            'reason': f'三週期: {reason}',
            'news_weight': 0,
            'position': position,
            'tf_signals': tf_signals,
            'agent_analyzed': False
        }
    
    # 有共振 → 調用 Fox Agent 分析
    logger.info(f"   ✅ 三週期共振: {reason}，調用 Fox Agent 分析...")
    
    # 這裡未來會調用 Fox Agent
    # 目前先用現有邏輯
    logger.info(f"   (暫時使用現有邏輯，未來會調用 Agent)")
    
    # 1. 獲取新聞權重
    news_data = get_news_weight(symbol)
    news_weight = news_data.get('total_weight', 0) or 0
    logger.info(f"   新聞權重: {news_weight}")
    
    # 2. 檢查新聞風險
    news_ok, news_reason = check_news_risk(news_weight)
    logger.info(f"   新聞風險: {'✅ 通過' if news_ok else '❌ 失敗'} - {news_reason}")
    
    # 3. 檢查市場風險
    market_ok, market_reason = check_market_risk(market_data)
    logger.info(f"   市場風險: {'✅ 通過' if market_ok else '❌ 失敗'} - {market_reason}")
    
    # 4. 計算信心度
    confidence = calculate_confidence(position, news_data, market_data)
    logger.info(f"   信心度: {confidence}")
    
    # 5. 決定信號 (三週期共振時增強信心度)
    if consensus == 1:
        confidence = min(0.95, confidence + 0.15)  # 買入共振加強
        signal_type = 'BUY'
    else:
        confidence = min(0.95, confidence + 0.15)  # 賣出共振加強
        signal_type = 'SELL'
    
    signal_reason = f'三週期共振 {reason}'
    logger.info(f"   信號: {signal_type} - {signal_reason} (信心度: {confidence})")
    
    return {
        'symbol': symbol,
        'signal_type': signal_type,
        'confidence': confidence,
        'news_ok': news_ok,
        'market_ok': market_ok,
        'reason': signal_reason,
        'news_weight': news_weight,
        'position': position,
        'tf_signals': tf_signals
    }


def run_analysis(dry_run: bool = False) -> List[Dict]:
    """
    執行 Fox 分析 - 分析 WATCHLIST 中所有股票
    """
    logger.info("=" * 60)
    logger.info("🦊 Fox Analysis 開始")
    logger.info("=" * 60)
    
    # 1. 獲取 WATCHLIST 股票列表
    watchlist = get_watchlist()
    if not watchlist:
        logger.warning("⚠️ 沒有 WATCHLIST，跳過分析")
        return []
    
    # 2. 獲取持倉（用於判斷是否已持有）
    positions = get_positions()
    position_dict = {p['symbol']: p for p in positions}
    
    # 3. 獲取市場數據
    market_data = get_market_data()
    
    # 4. 遍歷 WATCHLIST 進行分析
    signals_created = []
    
    for symbol in watchlist:
        # 檢查是否有持倉
        position = position_dict.get(symbol)
        current_qty = position.get('quantity', 0) if position else 0
        
        # 如果沒有持倉，創建一個虛擬持倉用於分析
        if not position:
            position = {
                'symbol': symbol,
                'quantity': 0,
                'avg_price': 0,
                'current_price': market_data.get(symbol, {}).get('price', 0)
            }
        
        logger.info(f"\n📈 分析 {symbol} {'(有持倉)' if current_qty > 0 else '(無持倉)'}")
        
        # 分析股票
        result = analyze_position(position, market_data)
        
        # 每次都創建信號 (包括 HOLD)
        if dry_run:
            logger.info(f"   [Dry Run] 模擬創建信號: {result['symbol']} {result['signal_type']}")
            signals_created.append(result)
        else:
            response = create_signal(
                position=result['position'],
                signal_type=result['signal_type'],
                confidence=result['confidence'],
                news_ok=result['news_ok'],
                market_ok=result['market_ok'],
                reason=result['reason']
            )
            if response.get('status') == 'ok':
                logger.info(f"   ✅ 信號創建成功: ID={response.get('signal_id')}")
                result['signal_id'] = response.get('signal_id')
            else:
                logger.error(f"   ❌ 信號創建失敗: {response.get('message')}")
            signals_created.append(result)
    
    # 總結
    logger.info("\n" + "=" * 60)
    logger.info("📊 Fox Analysis 完成")
    logger.info(f"   WATCHLIST 股票數: {len(watchlist)}")
    logger.info(f"   產生信號數: {len(signals_created)}")
    
    buy_count = sum(1 for s in signals_created if s['signal_type'] == 'BUY')
    sell_count = sum(1 for s in signals_created if s['signal_type'] == 'SELL')
    hold_count = len(signals_created) - buy_count - sell_count
    
    logger.info(f"   買入信號: {buy_count}")
    logger.info(f"   賣出信號: {sell_count}")
    logger.info(f"   觀望: {hold_count}")
    logger.info("=" * 60)
    
    return signals_created


def main():
    parser = argparse.ArgumentParser(description='Fox Analysis Script')
    parser.add_argument('--dry-run', action='store_true', help='模擬運行，不實際創建信號')
    parser.add_argument('--force', action='store_true', help='強制執行，忽略交易時段檢查')
    parser.add_argument('--verbose', action='store_true', help='顯示詳細指標數值日誌')
    args = parser.parse_args()
    
    # 檢查是否在交易時段 (自動判斷冬令時/夏令時)
    if HAS_MARKET_HOURS and not args.force:
        dst_status = "夏令時" if is_dst_us() else "冬令時"
        logger.info(f"📅 當前模式: {dst_status}")
        
        if not should_update_kline():
            logger.info("⏸️ 非交易時段，跳過分析")
            return
        logger.info("✅ 交易時段，開始分析...")
    
    run_analysis(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
