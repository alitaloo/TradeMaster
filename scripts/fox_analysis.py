#!/usr/bin/env python3
"""
Fox Analysis Script
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
import mysql.connector
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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

# 數據庫配置
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


# ==================== 三週期信號計算 ====================

def get_kline_data(symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
    """從數據庫獲取 K 線數據"""
    try:
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
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')  #  oldest first for calculation
        return df
        
    except Exception as e:
        logger.error(f"獲取 K 線數據失敗: {symbol} {timeframe} - {e}")
        return None


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """計算 RSI"""
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_stochastic(df: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> Tuple[pd.Series, pd.Series]:
    """計算隨機指標"""
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    k = 100 * (df['close'] - low_min) / (high_max - low_min)
    d = k.rolling(window=d_period).mean()
    return k, d


def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """計算布林帶"""
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper, sma, lower


def calculate_composite_signal(df: pd.DataFrame, indicator: str, params: dict) -> int:
    """
    計算組合策略信號
    只有當所有指標信號一致時才返回信號，否則返回 HOLD
    """
    indicators = indicator.split('+')
    signals = []
    
    for ind in indicators:
        ind = ind.strip()
        signal = calculate_single_indicator_signal(df, ind, params)
        if signal is None:
            return 0  # 無數據則放棄
        signals.append(signal)
    
    # 所有信號必須一致才算有效
    if len(set(signals)) == 1:
        return signals[0]  # 返回共識信號
    return 0  # 信號不一致，返回 HOLD


def calculate_single_indicator_signal(df: pd.DataFrame, indicator: str, params: dict) -> Optional[int]:
    """計算單一指標信號"""
    try:
        if indicator == 'RSI':
            rsi = calculate_rsi(df, params.get('period', 14))
            latest = rsi.iloc[-1]
            if pd.isna(latest):
                return None
            if latest < params.get('oversold', 30):
                return 1
            elif latest > params.get('overbought', 70):
                return -1
            return 0
            
        elif indicator == 'RSI_7':
            rsi = calculate_rsi(df, 7)
            latest = rsi.iloc[-1]
            if pd.isna(latest):
                return None
            if latest < 25:
                return 1
            elif latest > 75:
                return -1
            return 0
            
        elif indicator == 'Stochastic':
            k, d = calculate_stochastic(df, params.get('k_period', 14), params.get('d_period', 3))
            latest_k = k.iloc[-1]
            latest_d = d.iloc[-1]
            if pd.isna(latest_k) or pd.isna(latest_d):
                return None
            if latest_k < params.get('oversold', 20):
                return 1
            elif latest_k > params.get('overbought', 80):
                return -1
            return 0
            
        elif indicator == 'Bollinger':
            upper, middle, lower = calculate_bollinger(df, params.get('bb_period', 20), params.get('std', 2))
            latest_close = df['close'].iloc[-1]
            if pd.isna(upper.iloc[-1]):
                return None
            if latest_close < lower.iloc[-1]:
                return 1
            elif latest_close > upper.iloc[-1]:
                return -1
            return 0
            
        elif indicator == 'MACD':
            ema12 = df['close'].ewm(span=params.get('fast', 12)).mean()
            ema26 = df['close'].ewm(span=params.get('slow', 26)).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=params.get('signal', 9)).mean()
            latest = macd.iloc[-1] - signal.iloc[-1]
            if pd.isna(latest):
                return None
            if latest > 0:
                return 1
            elif latest < 0:
                return -1
            return 0
            
        elif indicator == 'SMA_Cross':
            sma_fast = df['close'].rolling(params.get('fast_ma', 10)).mean()
            sma_slow = df['close'].rolling(params.get('slow_ma', 50)).mean()
            latest = sma_fast.iloc[-1] - sma_slow.iloc[-1]
            if pd.isna(latest):
                return None
            if latest > 0:
                return 1
            elif latest < 0:
                return -1
            return 0
            
        elif indicator == 'EMA_Cross':
            ema_fast = df['close'].ewm(span=params.get('fast_ema', 12)).mean()
            ema_slow = df['close'].ewm(span=params.get('slow_ema', 26)).mean()
            latest = ema_fast.iloc[-1] - ema_slow.iloc[-1]
            if pd.isna(latest):
                return None
            if latest > 0:
                return 1
            elif latest < 0:
                return -1
            return 0
            
        elif indicator == 'CCI':
            tp = (df['high'] + df['low'] + df['close']) / 3
            sma_tp = tp.rolling(20).mean()
            mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
            cci = (tp - sma_tp) / (0.015 * mad)
            latest = cci.iloc[-1]
            if pd.isna(latest):
                return None
            if latest < -100:
                return 1
            elif latest > 100:
                return -1
            return 0
            
        elif indicator == 'Williams_R':
            highest = df['high'].rolling(14).max()
            lowest = df['low'].rolling(14).min()
            wr = -100 * (highest - df['close']) / (highest - lowest)
            latest = wr.iloc[-1]
            if pd.isna(latest):
                return None
            if latest < -80:
                return 1
            elif latest > -20:
                return -1
            return 0
            
        return 0
        
    except Exception as e:
        logger.error(f"  ❌ 計算指標 {indicator} 信號失敗: {e}")
        return None


def get_timeframe_signal(symbol: str, timeframe: str) -> Optional[int]:
    """
    計算單個週期的信號
    Returns: 1 (BUY), -1 (SELL), 0 (HOLD), None (無數據)
    """
    # 從 MySQL 獲取該股票該週期的最佳策略
    config = get_stock_strategy(symbol, timeframe)
    if not config:
        return None
    
    indicator = config['indicator']
    params = config['params']
    
    df = get_kline_data(symbol, timeframe, limit=200)
    if df is None or len(df) < 30:
        logger.warning(f"  ⚠️ {symbol} {timeframe} 數據不足")
        return None
    
    try:
        # 處理組合策略 (如 RSI+MACD, BB+STOCH)
        if '+' in indicator:
            return calculate_composite_signal(df, indicator, params)
        
        # 單一指標策略
        if indicator == 'RSI':
            rsi = calculate_rsi(df, params.get('period', 14))
            latest_rsi = rsi.iloc[-1]
            if pd.isna(latest_rsi):
                return None
            if latest_rsi < params.get('oversold', 30):
                return 1  # BUY
            elif latest_rsi > params.get('overbought', 70):
                return -1  # SELL
            return 0
            
        elif indicator == 'RSI_7':
            rsi = calculate_rsi(df, 7)
            latest_rsi = rsi.iloc[-1]
            if pd.isna(latest_rsi):
                return None
            if latest_rsi < 25:
                return 1
            elif latest_rsi > 75:
                return -1
            return 0
            
        elif indicator == 'Stochastic':
            k, d = calculate_stochastic(df, params.get('k_period', 14), params.get('d_period', 3))
            latest_k = k.iloc[-1]
            latest_d = d.iloc[-1]
            if pd.isna(latest_k) or pd.isna(latest_d):
                return None
            if latest_k < params.get('oversold', 20) and latest_d < params.get('oversold', 20):
                return 1  # BUY
            elif latest_k > params.get('overbought', 80) and latest_d > params.get('overbought', 80):
                return -1  # SELL
            return 0
            
        elif indicator == 'Bollinger':
            upper, middle, lower = calculate_bollinger(df, params.get('period', 20), params.get('std', 2))
            latest_close = df['close'].iloc[-1]
            if pd.isna(upper.iloc[-1]):
                return None
            if latest_close < lower.iloc[-1]:
                return 1  # BUY (接觸下軌)
            elif latest_close > upper.iloc[-1]:
                return -1  # SELL (接觸上軌)
            return 0
            
        elif indicator == 'MACD':
            ema12 = df['close'].ewm(span=12).mean()
            ema26 = df['close'].ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()
            latest = macd.iloc[-1] - signal.iloc[-1]
            if pd.isna(latest):
                return None
            if latest > 0:
                return 1
            elif latest < 0:
                return -1
            return 0
            
        elif indicator == 'SMA_Cross':
            sma_fast = df['close'].rolling(params.get('fast_ma', 10)).mean()
            sma_slow = df['close'].rolling(params.get('slow_ma', 50)).mean()
            latest = sma_fast.iloc[-1] - sma_slow.iloc[-1]
            if pd.isna(latest):
                return None
            if latest > 0:
                return 1
            elif latest < 0:
                return -1
            return 0
            
        elif indicator == 'EMA_Cross':
            ema_fast = df['close'].ewm(span=params.get('fast_ema', 12)).mean()
            ema_slow = df['close'].ewm(span=params.get('slow_ema', 26)).mean()
            latest = ema_fast.iloc[-1] - ema_slow.iloc[-1]
            if pd.isna(latest):
                return None
            if latest > 0:
                return 1
            elif latest < 0:
                return -1
            return 0
            
        elif indicator == 'CCI':
            tp = (df['high'] + df['low'] + df['close']) / 3
            sma_tp = tp.rolling(20).mean()
            mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
            cci = (tp - sma_tp) / (0.015 * mad)
            latest = cci.iloc[-1]
            if pd.isna(latest):
                return None
            if latest < -100:
                return 1
            elif latest > 100:
                return -1
            return 0
            
        elif indicator == 'Williams_R':
            highest = df['high'].rolling(14).max()
            lowest = df['low'].rolling(14).min()
            wr = -100 * (highest - df['close']) / (highest - lowest)
            latest = wr.iloc[-1]
            if pd.isna(latest):
                return None
            if latest < -80:
                return 1
            elif latest > -20:
                return -1
            return 0
            
        # 未知指標
        logger.warning(f"  ⚠️ 未知指標: {indicator}")
        return 0
            
    except Exception as e:
        logger.error(f"  ❌ 計算信號失敗: {symbol} {timeframe} - {e}")
        return None


def get_multi_timeframe_signals(symbol: str) -> Dict:
    """
    獲取三個週期的信號
    Returns: {'5m': signal, '1h': signal, '1d': signal, 'consensus': signal}
    """
    # 確保 symbol 有 US. 前綴
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'
    
    signals = {}
    
    for tf in ['5m', '1h', '1d']:
        signal = get_timeframe_signal(symbol, tf)
        signals[tf] = signal
        signal_str = {1: 'BUY', -1: 'SELL', 0: 'HOLD', None: 'N/A'}.get(signal, 'N/A')
        logger.info(f"  📊 {symbol} {tf}: {signal_str}")
    
    # 計算共識信號
    s5m, s1h, s1d = signals.get('5m'), signals.get('1h'), signals.get('1d')
    
    # 必須三個週期都有數據
    if s5m is None or s1h is None or s1d is None:
        signals['consensus'] = None
        signals['reason'] = '數據不足'
        signals['method'] = 'none'
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
    
    return signals


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
    
    # 去重檢查：檢查最近 1 小時內是否有相同的信號
    try:
        result = api_get(f'/signals?symbol={symbol}&limit=5')
        if result.get('status') == 'ok':
            recent_signals = result.get('signals', [])
            for sig in recent_signals:
                # 檢查是否同樣的信號類型
                if sig.get('signal_type') == signal_type:
                    logger.info(f"   ⏭️ 跳過: {symbol} 已有相同信號 {signal_type} (不重複寫入)")
                    return {'status': 'ok', 'message': 'duplicate', 'signal_id': sig.get('id')}
    except Exception as e:
        logger.warning(f"   ⚠️ 去重檢查失敗: {e}")
    
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
    執行 Fox 分析
    """
    logger.info("=" * 60)
    logger.info("🦊 Fox Analysis 開始")
    logger.info("=" * 60)
    
    # 1. 獲取持倉
    positions = get_positions()
    if not positions:
        logger.warning("⚠️ 沒有持倉，跳過分析")
        return []
    
    # 2. 獲取市場數據
    market_data = get_market_data()
    
    # 3. 遍歷持倉進行分析
    signals_created = []
    
    for position in positions:
        # 跳過空持倉
        current_qty = position.get('current_quantity', 0) or 0
        if current_qty <= 0:
            continue
        
        # 分析持倉
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
    logger.info(f"   總持倉數: {len(positions)}")
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
