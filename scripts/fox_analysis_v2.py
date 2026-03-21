#!/usr/bin/env python3
"""
Fox Analysis Script v2 (優化版)
Fox 分析腳本 - 讀取持倉、新聞權重、市場數據，執行風控，計算信心度，寫入交易信號
自動判斷冬令時/夏令時
三週期共振策略：5m, 1h, 1d 三個週期同時出現信號才執行

優化內容:
- API 重試機制 (retry_api 裝飾器)
- 數據新鮮度檢查 (max_age_minutes 參數)
- 成交量分析模組 (量比、OBV)
- 統一數據庫配置 (移除硬編碼密碼)

用法:
    python fox_analysis_v2.py [--dry-run]

API Base: http://localhost:8080/api/v1
"""

# 清除 HTTP 代理（和 fetch_news_rss.py 一樣）
import os
for _proxy_key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(_proxy_key, None)

import requests
import json
import logging
import os
import sys
import mysql.connector
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import argparse
import time
from functools import wraps

# 富途 API
try:
    import futu as ft
    from futu.quote.open_quote_context import OpenQuoteContext
    from futu.common.constant import KLType, TrdMarket, TrdSide, OrderType, TrdEnv
    # 附加到 ft 对象
    ft.OpenQuoteContext = OpenQuoteContext
    ft.KLType = KLType
    ft.TrdMarket = TrdMarket
    ft.TrdSide = TrdSide
    ft.OrderType = OrderType
    ft.TrdEnv = TrdEnv
    HAS_FUTU = True
except ImportError as e:
    HAS_FUTU = False
    print(f"⚠️ 富途 SDK 导入失败: {e}")

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

# 添加 socket timeout 防止連接阻塞
import socket
socket.setdefaulttimeout(10)

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

RSI_PROFILES = {
    'default': {'RSI': {'oversold': 30, 'overbought': 70}, 'RSI_7': {'oversold': 25, 'overbought': 75}},
    'tighter': {'RSI': {'oversold': 25, 'overbought': 75}, 'RSI_7': {'oversold': 20, 'overbought': 80}},
    'conservative': {'RSI': {'oversold': 20, 'overbought': 80}, 'RSI_7': {'oversold': 18, 'overbought': 82}},
}

CONFIDENCE_TIERS = [
    (0.85, 'very_high', 'very_strong'),
    (0.75, 'high', 'strong'),
    (0.60, 'medium', 'moderate'),
    (0.00, 'low', 'weak'),
]

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

# 導入 TopK 信號生成器
try:
    from signal_generator_topk import TopKSignalGenerator
    TOPK_AVAILABLE = True
except ImportError:
    TOPK_AVAILABLE = False

# 導入系統配置
try:
    from models import SystemConfig
except ImportError:
    SystemConfig = None
    TOPK_AVAILABLE = False
    logger.warning("⚠️ TopK 信號生成器不可用")

# 股票策略緩存
_stock_strategy_cache = {}
_cache_loaded = False


# ==================== API 重試機制 ====================
def retry_api(max_retries: int = 3, delay: float = 1, backoff: float = 2):
    """
    API 重試裝飾器
    - max_retries: 最大重試次數
    - delay: 初始延遲秒數
    - backoff: 指數退避倍率
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    # 檢查結果是否為錯誤
                    if isinstance(result, dict) and result.get('status') == 'error':
                        if attempt < max_retries - 1:
                            wait_time = delay * (backoff ** attempt)
                            logger.warning(
                                f"API 失敗 (attempt {attempt + 1}/{max_retries}), "
                                f"等待 {wait_time:.1f}s 後重試... "
                                f"原因: {result.get('message')}"
                            )
                            time.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"API 失敗已達最大重試次數: {result.get('message')}")
                    return result
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(
                            f"API 異常 (attempt {attempt + 1}/{max_retries}), "
                            f"等待 {wait_time:.1f}s 後重試... 原因: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"API 異常已達最大重試次數: {e}")
            
            # 所有重試都失敗
            return {'status': 'error', 'message': str(last_exception or 'Max retries exceeded')}
        return wrapper
    return decorator


# ==================== 成交量分析模組 ====================
def calculate_volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    計算量比 = 當前成交量 / N日平均成交量
    """
    if len(df) < period:
        return pd.Series([1.0] * len(df), index=df.index)
    
    vol_ma = df['volume'].rolling(window=period).mean()
    vol_ratio = df['volume'] / vol_ma
    return vol_ratio


def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """
    計算 OBV (On-Balance Volume) 能量潮
    """
    obv = pd.Series(index=df.index, dtype=float)
    obv.iloc[0] = df['volume'].iloc[0]
    
    for i in range(1, len(df)):
        if df['close'].iloc[i] > df['close'].iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] + df['volume'].iloc[i]
        elif df['close'].iloc[i] < df['close'].iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] - df['volume'].iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    
    return obv


def get_volume_signal(df: pd.DataFrame, period: int = 20) -> Tuple[int, Dict]:
    """
    成交量信號判斷
    Returns: (信號, 詳細信息)
    信號: 1 (放量上漲/強勢), -1 (放量下跌/弱勢), 0 (無信號)
    """
    if len(df) < period + 1:
        return 0, {'reason': '數據不足'}
    
    try:
        vol_ratio = calculate_volume_ratio(df, period).iloc[-1]
        price_change = df['close'].pct_change().iloc[-1]
        
        details = {
            'volume_ratio': vol_ratio,
            'price_change': price_change
        }
        
        # 放量上漲 = 強勢信號
        if vol_ratio > 1.5 and price_change > 0:
            return 1, details
        # 放量下跌 = 弱勢信號
        elif vol_ratio > 1.5 and price_change < 0:
            return -1, details
        # 縮量上漲 = 可能虛漲
        elif vol_ratio < 0.5 and price_change > 0:
            return 0, {**details, 'reason': '縮量上漲可能虛漲'}
        # 縮量下跌 = 可能見底
        elif vol_ratio < 0.5 and price_change < 0:
            return 0, {**details, 'reason': '縮量下跌可能見底'}
        
        return 0, {**details, 'reason': '正常成交量'}
        
    except Exception as e:
        logger.error(f"成交量信號計算失敗: {e}")
        return 0, {'reason': f'計算錯誤: {e}'}


# ==================== 數據庫操作 ====================
def get_runtime_setting(key: str, default=None):
    if not SystemConfig:
        return default
    try:
        value = SystemConfig.get(key, default)
        return default if value in (None, '') else value
    except Exception:
        return default


def get_rsi_profile() -> str:
    profile = str(get_runtime_setting('rsi_profile', 'default')).strip().lower()
    return profile if profile in RSI_PROFILES else 'default'


def apply_rsi_profile(indicator: str, params: dict) -> dict:
    adjusted = dict(params or {})
    profile = RSI_PROFILES[get_rsi_profile()]
    if indicator == 'RSI':
        adjusted.update(profile['RSI'])
    elif indicator == 'RSI_7':
        adjusted.update(profile['RSI_7'])
    elif 'RSI' in indicator.split('+'):
        adjusted.update(profile['RSI'])
    return adjusted


def quantize_confidence(value: float) -> float:
    clipped = max(0.1, min(0.95, value))
    return round(round(clipped / 0.05) * 0.05, 2)


def get_agent_scores(symbol: str) -> Dict:
    """
    從 agent_scores 表讀取 Agent 評分
    
    Returns:
    {
        'news_risk': float,      # -1.0 ~ 1.0
        'strategy_signal': float, # -1.0 ~ 1.0
        'updated_at': datetime
    }
    """
    try:
        # 保持 symbol 格式 (可能帶 US. 前綴)
        # 嘗試兩種格式都查詢
        search_symbols = [symbol]
        if symbol.startswith('US.'):
            search_symbols.append(symbol.split('.', 1)[1])
        else:
            search_symbols.append(f'US.{symbol}')
        
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # 讀取該股票最近的評分
        placeholders = ','.join(['%s'] * len(search_symbols))
        cursor.execute(f"""
            SELECT score_type, score, updated_at
            FROM agent_scores
            WHERE symbol IN ({placeholders})
            AND updated_at > DATE_SUB(NOW(), INTERVAL 1 HOUR)
            ORDER BY updated_at DESC
        """, search_symbols)
        
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        result = {}
        for row in rows:
            score_type = row['score_type']
            if score_type not in result:
                result[score_type] = row['score']
                result['updated_at'] = row['updated_at']
        
        if result:
            logger.debug(f"📊 Agent Scores for {symbol}: {result}")
        
        return result
        
    except Exception as e:
        logger.debug(f"讀取 agent_scores 失敗: {e}")
        return {}


def classify_confidence(confidence: float) -> Tuple[str, str]:
    for minimum, tier, strength in CONFIDENCE_TIERS:
        if confidence >= minimum:
            return tier, strength
    return 'low', 'weak'


def get_trend_label(tf_signal) -> str:
    mapping = {1: 'bullish', -1: 'bearish', 0: 'neutral', None: 'unknown', 'BUY': 'bullish', 'SELL': 'bearish', 'HOLD': 'neutral'}
    return mapping.get(tf_signal, str(tf_signal).lower())


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
            WHERE COALESCE(active, 1) = 1
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
            params = apply_rsi_profile(indicator, params)
            
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
    config = default_config.get(timeframe, {'indicator': 'RSI', 'params': {}})
    return {'indicator': config['indicator'], 'params': apply_rsi_profile(config['indicator'], config['params'])}


# 保持向後兼容的默認配置
TIMEFRAME_CONFIG = {
    '5m': {'indicator': 'RSI', 'params': {'period': 14, 'oversold': 30, 'overbought': 70}},
    '1h': {'indicator': 'Stochastic', 'params': {'k_period': 14, 'd_period': 3, 'oversold': 20, 'overbought': 80}},
    '1d': {'indicator': 'Bollinger', 'params': {'period': 20, 'std': 2}},
}


# ==================== API 請求 (含重試機制) ====================
@retry_api(max_retries=3, delay=1, backoff=2)
def api_get(endpoint: str, params: dict = None) -> dict:
    """發送 GET 請求 (含重試機制)"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


@retry_api(max_retries=3, delay=1, backoff=2)
def api_post(endpoint: str, data: dict) -> dict:
    """發送 POST 請求 (含重試機制)"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.post(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


# ==================== K線數據 (含新鮮度檢查) ====================
def get_realtime_kline(symbol: str, timeframe: str, limit: int = 10) -> Optional[pd.DataFrame]:
    """
    從富途 API 獲取實時 K 線數據
    
    Parameters:
    - symbol: 股票代碼 (如 US.AAPL)
    - timeframe: 週期 (5m, 1h, 1d)
    - limit: 獲取數據量
    
    Returns:
    - pd.DataFrame 或 None (獲取失敗)
    """
    if not HAS_FUTU:
        logger.warning("富途模組未安裝，無法獲取實時數據")
        return None
    
    # 快速檢查連接，如果失敗則跳過
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex(('127.0.0.1', 11111))
        sock.close()
        if result != 0:
            logger.warning("富途服務未運行，跳過實時數據")
            return None
    except Exception:
        try:
            sock.close()
        except:
            pass
        logger.warning("富途連接失敗，跳過實時數據")
        return None
    
    try:
        # 轉換週期格式
        timeframe_map = {
            '5m': ft.KLType.K_5M,
            '1h': ft.KLType.K_60M,
            '1d': ft.KLType.K_DAY,
            '1w': ft.KLType.K_WEEK,
            '1M': ft.KLType.K_1M,
        }
        ktype = timeframe_map.get(timeframe)
        if ktype is None:
            logger.warning(f"不支持的週期: {timeframe}")
            return None
        
        # 連接富途
        quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        
        # 計算時間範圍（取足夠的歷史數據）
        if timeframe == '5m':
            start_date = (datetime.now() - pd.Timedelta(days=3)).strftime('%Y-%m-%d')
        elif timeframe == '1h':
            start_date = (datetime.now() - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        else:  # 1d
            start_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        # 獲取實時 K 線
        result = quote_ctx.request_history_kline(
            symbol,
            start=start_date,
            end=end_date,
            ktype=ktype,
            max_count=limit
        )
        
        # 富途返回 (ret, data, extra) 三個值
        if len(result) == 3:
            ret, data, extra = result
        else:
            logger.warning(f"富途 API 返回格式錯誤: {symbol} {timeframe}")
            quote_ctx.close()
            return None
        
        quote_ctx.close()
        
        if ret != 0:
            logger.warning(f"富途 API 獲取失敗: {symbol} {timeframe}, ret={ret}")
            return None
        if data is None:
            logger.warning(f"富途 API 返回空數據: {symbol} {timeframe}")
            return None
        if len(data) == 0:
            logger.warning(f"富途 API 返回 0 條數據: {symbol} {timeframe}")
            return None
        
        # 轉換為 DataFrame
        df = pd.DataFrame({
            'timestamp': pd.to_datetime(data['time_key']),
            'open': data['open'].astype(float),
            'high': data['high'].astype(float),
            'low': data['low'].astype(float),
            'close': data['close'].astype(float),
            'volume': data['volume'].astype(int)
        })
        
        df = df.sort_values('timestamp')  # oldest first
        logger.info(f"✅ 實時 K 線獲取成功: {symbol} {timeframe}, {len(df)} 條")
        return df
        
    except Exception as e:
        logger.error(f"獲取實時 K 線失敗: {symbol} {timeframe} - {e}")
        return None


def get_kline_data(
    symbol: str, 
    timeframe: str, 
    limit: int = 100, 
    max_age_minutes: Optional[float] = None
) -> Optional[pd.DataFrame]:
    """
    獲取 K 線數據：優先實時 K 線，失敗則用 cache
    
    Parameters:
    - symbol: 股票代碼 (如 AAPL 或 US.AAPL)
    - timeframe: 週期 (5m, 1h, 1d)
    - limit: 獲取數據量
    - max_age_minutes: 數據最大年齡(分鐘)。如果數據超過此年齡，返回 None
    
    Returns:
    - pd.DataFrame 或 None (數據過期或獲取失敗)
    """
    try:
        # 添加 US. 前綴（如果沒有）
        if not symbol.startswith('US.'):
            symbol = f'US.{symbol}'
        
        # ===== Step 1: 嘗試獲取實時 K 線 =====
        realtime_df = get_realtime_kline(symbol, timeframe, limit=limit)
        
        if realtime_df is not None and len(realtime_df) > 0:
            # 有實時數據，直接使用
            df = realtime_df
            source = "實時"
        else:
            # ===== Step 2: 實時獲取失敗，使用 cache =====
            logger.info(f"無法獲取實時 K 線，使用 cache: {symbol} {timeframe}")
        
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
            logger.warning(f"無 K 線數據: {symbol} {timeframe}")
            return None
        
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
        df = df.sort_values('timestamp')  # oldest first for calculation
        
        # ===== 新鮮度檢查 =====
        if max_age_minutes is not None and len(df) > 0:
            latest_timestamp = df['timestamp'].iloc[-1]
            now = datetime.now()
            
            # 處理時區
            if latest_timestamp.tzinfo is not None:
                now = pd.Timestamp.now(tz=latest_timestamp.tzinfo)
            
            age_minutes = (now - latest_timestamp).total_seconds() / 60
            
            # 根據週期設置默認 max_age_minutes
            default_age_limits = {
                '5m': 10,    # 5分線 10 分鐘內
                '1h': 60,    # 1小時線 60 分鐘內
                '1d': 1440,  # 1天线 24 小時內
            }
            
            # 如果未指定，使用週期默認值
            if max_age_minutes is None:
                max_age_minutes = default_age_limits.get(timeframe, 60)
            
            if age_minutes > max_age_minutes:
                logger.warning(
                    f"數據過期: {symbol} {timeframe}, "
                    f"年齡={age_minutes:.1f}分鐘 > 限制={max_age_minutes}分鐘"
                )
                return None
            
            logger.debug(f"數據新鮮度: {symbol} {timeframe}, 年齡={age_minutes:.1f}分鐘")
        
        return df
        
    except Exception as e:
        logger.error(f"獲取 K 線數據失敗: {symbol} {timeframe} - {e}")
        return None


# ==================== 技術指標計算 ====================
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


def get_timeframe_signal(symbol: str, timeframe: str, max_age_minutes: Optional[float] = None) -> Optional[int]:
    """
    計算單個週期的信號
    注意：5分線使用上一根確定的K線，避免當前K線還在變動
    Returns: 1 (BUY), -1 (SELL), 0 (HOLD), None (無數據)
    """
    # 從 MySQL 獲取該股票該週期的最佳策略
    config = get_stock_strategy(symbol, timeframe)
    if not config:
        return None
    
    indicator = config['indicator']
    params = config['params']
    
    # 5分線多取一根數據，用倒數第二根（上一根確定的K線）
    limit = 201 if timeframe == '5m' else 200
    
    # 調用 get_kline_data 時傳入 max_age_minutes 參數
    df = get_kline_data(symbol, timeframe, limit=limit, max_age_minutes=max_age_minutes)
    if df is None or len(df) < 30:
        logger.warning(f"  ⚠️ {symbol} {timeframe} 數據不足")
        return None
    
    # 5分線：跳過最後一根（正在變動），用上一根確定的K線
    if timeframe == '5m' and len(df) > 1:
        df = df.iloc[:-1]  # 移除最後一根
    
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


# ==================== TopK 三週期共振 ====================

def get_topk_signals_v2(symbol: str, df_5m: pd.DataFrame = None, df_1h: pd.DataFrame = None, df_1d: pd.DataFrame = None) -> Dict:
    """
    使用 TopK 產生三個週期的信號
    只有當三個週期都是 BUY 或都是 SELL 時才返回信號，否則返回 HOLD
    
    Returns:
    {
        '5m': 'BUY'/'SELL'/'HOLD',
        '1h': 'BUY'/'SELL'/'HOLD', 
        '1d': 'BUY'/'SELL'/'HOLD',
        'consensus': 'BUY'/'SELL'/'HOLD',  # 最終共識
        'method': 'TopK_3/3'
    }
    """
    if not TOPK_AVAILABLE:
        return {'consensus': 'HOLD', 'method': 'TopK_not_available'}
    
    try:
        generator = TopKSignalGenerator()
    except Exception as e:
        logger.warning(f"⚠️ TopK 初始化失敗: {e}")
        return {'consensus': 'HOLD', 'method': 'TopK_error'}
    
    results = {}
    
    # 處理每個週期
    for timeframe, df in [('5m', df_5m), ('1h', df_1h), ('1d', df_1d)]:
        if df is None or len(df) < 30:
            results[timeframe] = 'HOLD'
            continue
        
        try:
            result = generator.generate_signal(symbol, df)
            results[timeframe] = result.get('signal', 'HOLD')
        except Exception as e:
            logger.warning(f"⚠️ {symbol} {timeframe} TopK 失敗: {e}")
            results[timeframe] = 'HOLD'
    
    # 計算共識：必須三個週期都相同且不是 HOLD
    signals = [results.get('5m'), results.get('1h'), results.get('1d')]
    
    if signals.count('BUY') == 3:
        consensus = 'BUY'
    elif signals.count('SELL') == 3:
        consensus = 'SELL'
    else:
        consensus = 'HOLD'
    
    return {
        '5m': results.get('5m', 'HOLD'),
        '1h': results.get('1h', 'HOLD'),
        '1d': results.get('1d', 'HOLD'),
        'consensus': consensus,
        'method': 'TopK_3/3'
    }


# ==================== 原有函數 ====================

def get_multi_timeframe_signals(symbol: str, max_age_minutes: Optional[float] = None) -> Dict:
    """
    獲取三個週期的信號
    Returns: {'5m': signal, '1h': signal, '1d': signal, 'consensus': signal}
    """
    # 確保 symbol 有 US. 前綴
    if not symbol.startswith('US.'):
        symbol = f'US.{symbol}'
    
    signals = {}
    
    for tf in ['5m', '1h', '1d']:
        signal = get_timeframe_signal(symbol, tf, max_age_minutes=max_age_minutes)
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


# ==================== 其他 API 函數 ====================
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
    result = api_get('/paper/positions')
    
    if result.get('status') == 'ok':
        positions = result.get('positions', [])
        # 確保每個 position 都有 return_pct
        for p in positions:
            if 'return_pct' not in p and p.get('average_cost') and float(p['average_cost']) > 0:
                cost = float(p['average_cost'])
                curr = float(p.get('current_price', 0))
                p['return_pct'] = round(((curr - cost) / cost) * 100, 2)
        logger.info(f"   找到 {len(positions)} 個持倉")
        return positions
    else:
        logger.warning(f"   獲取持倉失敗: {result.get('message')}")
        return []


def get_watchlist() -> List[str]:
    """從 MySQL 獲取 WATCHLIST 股票列表 (使用統一 DB_CONFIG)"""
    logger.info("📋 獲取 WATCHLIST 股票列表...")
    try:
        # 使用統一 DB_CONFIG (移除硬編碼密碼)
        conn = mysql.connector.connect(**DB_CONFIG)
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
    """獲取股票新聞權重
    注意：news 表與 API 使用無市場前綴的代碼（TSLA），
    需在此處移除例如 US.TSLA 之類的前綴，避免永遠查不到資料。

    業務規則 (見 docs/news_sync_business_rules.md):
    - sync_status == 'ok' + news_count == 0 = 真的沒有新聞 (quiet)
    - sync_status == 'error'/'degraded' = 同步失敗，需告警或繞過
    - is_stale == True = 數據過期，需重新同步
    - 兼容舊版 API：無 sync_status 欄位時，預設視為 ok
    """
    # 去除市場前綴（例如 US.TSLA → TSLA）
    if symbol.startswith('US.'):
        api_symbol = symbol.split('.', 1)[1]
    else:
        api_symbol = symbol

    result = api_get(f'/news/weight/{api_symbol}', {'hours': hours})
    
    if result.get('status') == 'ok':
        # 兼容舊版 API（無 sync_status/is_stale 欄位）
        result.setdefault('sync_status', 'ok')
        result.setdefault('is_stale', False)
        return result
    else:
        logger.warning(f"   獲取新聞權重失敗: {result.get('message')}")
        return {
            'status': 'error',
            'degraded': True,
            'symbol': api_symbol,
            'total_weight': None,
            'news_count': 0,
            'breakdown': {'positive': 0, 'negative': 0, 'neutral': 0},
            'error_message': result.get('message', 'unknown API error'),
            'sync_status': 'error',  # 明確標記為錯誤
            'is_stale': True
        }


def get_market_data() -> Dict:
    """獲取市場數據（含新鮮度檢查）"""
    logger.info("📈 獲取市場數據...")
    from datetime import datetime, timedelta
    
    market_dict = {}
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT type, value, updated_at FROM market")
        for row in cursor.fetchall():
            mtype = row['type'].lower()
            updated = row['updated_at']
            if updated and (datetime.now() - updated).total_seconds() > 86400:
                logger.warning(f"   ⚠️ {mtype} 數據過期 (更新於 {updated})，跳過")
                continue
            market_dict[mtype] = row['value']
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(f"   獲取市場數據失敗: {e}")
    
    logger.info(f"   市場數據: {market_dict}")
    return market_dict


def get_stock_price(symbol: str) -> float:
    """
    獲取個股現價 (從 K 線數據)
    
    Args:
        symbol: 股票代碼 (如 AAPL 或 US.AAPL)
    
    Returns:
        float: 現價，如果獲取失敗返回 0
    """
    # 優先從 1d K 線獲取最新收盤價
    df = get_kline_data(symbol, '1d', limit=1)
    if df is not None and len(df) > 0:
        price = float(df['close'].iloc[-1])
        logger.info(f"   📊 {symbol} 現價: ${price}")
        return price
    
    # Fallback: 嘗試 1h K 線
    df = get_kline_data(symbol, '1h', limit=1)
    if df is not None and len(df) > 0:
        price = float(df['close'].iloc[-1])
        logger.info(f"   📊 {symbol} 現價 (1h): ${price}")
        return price
    
    logger.warning(f"   ⚠️ 無法獲取 {symbol} 現價")
    return 0


# ==================== 風控與信心度 ====================
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


def check_news_risk(news_weight: int, news_data: Optional[Dict] = None) -> Tuple[bool, str]:
    """
    檢查新聞風險
    返回: (是否通過, 原因)
    
    業務規則:
    - sync_status == 'error' = API 完全失敗，阻擋交易
    - sync_status == 'degraded' = 部分失敗，建議謹慎
    - is_stale == True = 數據過期，阻擋交易
    - news_weight > 阈值 = 新聞異常，阻擋交易
    - news_weight == 0 且 sync_status == 'ok' = quiet，正常通過
    """
    # 檢查同步狀態
    if news_data:
        sync_status = news_data.get('sync_status', 'ok')
        is_stale = news_data.get('is_stale', False)
        
        if sync_status == 'error':
            return False, f"新聞同步失敗 (API error)，無法評估風險"
        
        if sync_status == 'degraded':
            return False, f"新聞同步降級 (partial failure)，建議謹慎"
        
        if is_stale:
            return False, f"新聞數據過期 (超過 6 小時未更新)，請重新同步"
    
    # 檢查新聞權重
    if news_weight is None:
        news_weight = 0
    
    if news_weight > RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']:
        return False, f"新聞權重={news_weight} > {RISK_PARAMS['NEWS_WEIGHT_THRESHOLD']} (新聞異常)"
    
    return True, "新聞風險檢查通過"


def check_total_position(positions: List[Dict], max_total: float = 50000) -> Dict:
    """
    風控檢查 - fail-safe
    檢查總持倉金額是否超過限制
    失敗時預設阻擋！
    """
    try:
        # 原有邏輯
        total = sum(p.get('position_value', 0) for p in positions)
        if total > max_total:
            return {'passed': False, 'reason': 'exceeded_limit', 'total': total}
        return {'passed': True, 'total': total}
    except Exception as e:
        # 失敗時預設阻擋！
        logger.error(f"風控檢查失敗: {e}")
        return {'passed': False, 'reason': f'check_error: {e}'}


def calculate_confidence(position: Dict, news_data: Dict, market_data: Dict, tf_signals: Optional[Dict] = None) -> Dict:
    """
    計算更細緻的信心度，並返回 tier / strength 供 execution 使用
    """
    confidence = 0.50
    components = []

    return_pct = position.get('return_pct', 0) or 0
    if return_pct > 15:
        confidence += 0.18
        components.append('position_return:strong_positive')
    elif return_pct > 8:
        confidence += 0.12
        components.append('position_return:positive')
    elif return_pct > 0:
        confidence += 0.06
        components.append('position_return:slightly_positive')
    elif return_pct > -5:
        confidence -= 0.08
        components.append('position_return:slightly_negative')
    else:
        confidence -= 0.16
        components.append('position_return:negative')

    news_weight_raw = news_data.get('total_weight')
    # 兼容新舊版 API：優先使用 sync_status，fallback 到 degraded 欄位
    sync_status = news_data.get('sync_status', 'ok')
    news_degraded = news_data.get('degraded', False) or (sync_status in ('error', 'degraded'))
    
    if news_degraded or news_weight_raw is None:
        # API error: don't adjust confidence, mark as degraded
        confidence += 0.0
        components.append('news:degraded')
    else:
        news_weight = news_weight_raw or 0
        if news_weight == 0:
            confidence += 0.08
            components.append('news:quiet')
        elif news_weight < 3:
            confidence += 0.04
            components.append('news:light')
        elif news_weight > 7:
            confidence -= 0.16
            components.append('news:heavy')

    breakdown = news_data.get('breakdown', {})
    positive = breakdown.get('positive', 0)
    negative = breakdown.get('negative', 0)
    if positive > negative:
        confidence += 0.06
        components.append('sentiment:positive')
    elif negative > positive:
        confidence -= 0.06
        components.append('sentiment:negative')

    vix = market_data.get('vix')
    if vix is not None:
        if vix < 15:
            confidence += 0.12
            components.append('vix:calm')
        elif vix < 20:
            confidence += 0.06
            components.append('vix:stable')
        elif vix > 30:
            confidence -= 0.14
            components.append('vix:risk_off')
        elif vix > 25:
            confidence -= 0.08
            components.append('vix:elevated')

    # ===== 多因子大盤評分 (方案三) =====
    def _market_factor_score(market_data: Dict, components: list) -> float:
        """多因子大盤評分，返回 -0.20 ~ +0.15"""
        score = 0.0
        
        # 1. 漲跌幅模組（每 1% ≈ ±0.04，上限 ±0.12）
        md = float(market_data.get('market_drop', 0) or 0)
        md_score = min(max(md * 0.04, -0.12), 0.08)
        score += md_score
        if md > 1:
            components.append('market:broad_strength')
        elif md < -1:
            components.append('market:broad_weakness')
        else:
            components.append('market:neutral')
        
        # 2. SPY/QQQ 趨勢模組（從 kline_cache 查 5日/20日均線）
        try:
            from config.database import get_db_cursor
            spy_trend = 0
            qqq_trend = 0
            with get_db_cursor() as c:
                for sym in ['US.SPY', 'US.QQQ']:
                    c.execute("""
                        SELECT AVG(close) as avg FROM (
                            SELECT close FROM kline_cache
                            WHERE symbol=%s AND interval_val='1d'
                            ORDER BY timestamp DESC LIMIT 5
                        ) t5
                    """, (sym,))
                    ma5_row = c.fetchone()
                    c.execute("""
                        SELECT AVG(close) as avg FROM (
                            SELECT close FROM kline_cache
                            WHERE symbol=%s AND interval_val='1d'
                            ORDER BY timestamp DESC LIMIT 20
                        ) t20
                    """, (sym,))
                    ma20_row = c.fetchone()
                    if ma5_row and ma20_row and ma5_row['avg'] and ma20_row['avg']:
                        if float(ma5_row['avg']) > float(ma20_row['avg']):
                            if sym == 'US.SPY': spy_trend = 1
                            else: qqq_trend = 1
                        else:
                            if sym == 'US.SPY': spy_trend = -1
                            else: qqq_trend = -1
            
            if spy_trend == 1 and qqq_trend == 1:
                score += 0.03
                components.append('market:dual_bull')
            elif spy_trend == -1 and qqq_trend == -1:
                score -= 0.03
                components.append('market:dual_bear')
        except Exception:
            pass  # 查不到就不調整
        
        # 3. VIX 模組（絕對值 + 趨勢方向）
        vix = market_data.get('vix')
        if vix is not None:
            vix = float(vix)
            if vix > 25:
                score -= 0.03
            elif vix > 20:
                score -= 0.01
            # VIX 3日趨勢
            try:
                with get_db_cursor() as c:
                    c.execute("""
                        SELECT value, updated_at FROM market
                        WHERE type='VIX' ORDER BY updated_at DESC LIMIT 1
                    """)
                    # 簡單判斷：若 VIX > 20 且市場下跌，VIX 可能在上升
                    if vix > 20 and md < -0.5:
                        score -= 0.02
                        components.append('vix:rising_risk')
            except Exception:
                pass
        
        # 限制總影響範圍
        return float(max(min(score, 0.15), -0.20))
    
    # 呼叫多因子評分
    market_score = _market_factor_score(market_data, components)
    confidence += market_score

    if tf_signals:
        consensus = tf_signals.get('consensus')
        one_hour = tf_signals.get('1h')
        daily = tf_signals.get('1d')
        if consensus in ('BUY', 'SELL'):
            confidence += 0.08
            components.append('topk:consensus')
        if one_hour == consensus and consensus in ('BUY', 'SELL'):
            confidence += 0.05
            components.append('trend_1h:aligned')
        if daily == consensus and consensus in ('BUY', 'SELL'):
            confidence += 0.03
            components.append('trend_1d:aligned')

    # ===== Agent Scores 評分 (Async Advisor Mode) =====
    symbol = position.get('symbol')
    if symbol:
        agent_scores = get_agent_scores(symbol)
        if agent_scores:
            # 新聞風險權重：負面新聞多 → confidence 下降
            news_risk = agent_scores.get('news_risk', 0)
            if news_risk != 0:
                # news_risk > 0 表示負面新聞多，扣信心度
                # news_risk < 0 表示正面新聞多，加信心度
                # 權重 10%
                confidence += (news_risk * 0.1)
                components.append(f'agent:news_risk({news_risk:.2f})')
            
            # 策略信號權重：買入信號 → confidence 上升
            strategy_signal = float(agent_scores.get('strategy_signal', 0))
            if strategy_signal != 0:
                # strategy_signal > 0 表示買入信號，加信心度
                # strategy_signal < 0 表示賣出信號，扣信心度
                # 權重 10%
                confidence += (strategy_signal * 0.1)
                components.append(f'agent:strategy_signal({strategy_signal:.2f})')
            
            logger.info(f"   🤖 Agent Scores: news_risk={news_risk:.2f}, strategy_signal={strategy_signal:.2f}")

    confidence = quantize_confidence(confidence)
    tier, strength = classify_confidence(confidence)
    return {
        'confidence': confidence,
        'confidence_tier': tier,
        'strength': strength,
        'components': components,
    }


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


def get_recent_signal(symbol: str, hours: int = 24) -> Optional[Dict]:
    """
    獲取最近的小時內的同方向信號
    用於去重邏輯
    """
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # 查詢最近 N 小時內的信號
        cursor.execute("""
            SELECT id, symbol, signal_type, confidence, created_at
            FROM signals
            WHERE symbol = %s 
            AND created_at >= DATE_SUB(NOW(), INTERVAL %s HOUR)
            ORDER BY created_at DESC
            LIMIT 1
        """, (symbol, hours))
        
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return row
        
    except Exception as e:
        logger.debug(f"查詢最近信號失敗: {e}")
        return None


def should_write_signal(symbol: str, new_direction: str, hours: int = 24) -> Tuple[bool, Optional[Dict]]:
    """
    判斷是否應該寫入信號（去重邏輯）
    
    返回: (是否應該寫入, 現有信號信息)
    - 如果方向相同，更新信心度，不重複寫入
    - 如果方向改變，寫入新信號
    - 連續 HOLD 跳過
    """
    recent = get_recent_signal(symbol, hours)
    
    if recent is None:
        # 無歷史信號，寫入
        return True, None
    
    prev_direction = recent['signal_type']
    prev_confidence = recent.get('confidence', 0)
    
    # 連續 HOLD，跳過
    if new_direction == "HOLD" and prev_direction == "HOLD":
        logger.info(f"   ⏭️ 連續 HOLD 信號，跳過寫入")
        return False, recent
    
    # 方向改變，寫入新信號
    if new_direction != prev_direction:
        return True, recent
    
    # 方向相同（非 HOLD），寫入（更新信心度）
    if new_direction != "HOLD":
        logger.info(f"   🔄 方向相同 ({new_direction})，更新信心度: {prev_confidence}")
        return True, recent
    
    return True, recent


def update_signal_confidence(signal_id: int, new_confidence: float) -> bool:
    """更新現有信號的信心度"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE signals 
            SET confidence = %s, updated_at = NOW()
            WHERE id = %s
        """, (new_confidence, signal_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"   ✅ 更新信號信心度: ID={signal_id}, confidence={new_confidence}")
        return True
        
    except Exception as e:
        logger.error(f"更新信號信心度失敗: {e}")
        return False


def create_signal(position: Dict, signal_type: str, confidence: float, 
                  news_ok: bool, market_ok: bool, reason: str,
                  stop_loss_pct: float = None, market_data: Dict = None,
                  *, tf_signals: Optional[Dict] = None, confidence_tier: Optional[str] = None,
                  strength: Optional[str] = None, confidence_components: Optional[List[str]] = None) -> Dict:
    """創建交易信號 (自動去重)"""
    symbol = position.get('symbol')
    
    # 優先從 K 線數據獲取當前價格
    current_price = get_stock_price(symbol)
    
    # Fallback: 從持倉記錄獲取平均成本
    if current_price == 0:
        current_price = position.get('average_cost', 0) or 0
    
    # Fallback: 從持倉記錄獲取當前價格
    if current_price == 0:
        current_price = position.get('current_price', 0) or 0
    
    # ===== HOLD 的處理：寫入 IGNORED =====
    if signal_type == 'HOLD':
        # 檢查是否已有 IGNORED 記錄 (避免重複寫入)
        should_write, _ = should_write_signal(symbol, 'HOLD', hours=24)
        
        if not should_write:
            return {'status': 'ok', 'message': 'HOLD 跳過（已有記錄）'}
        
        # 寫入 IGNORED 狀態
        signal_data = {
            'symbol': symbol,
            'strategy_type': 'fox_analysis_v2',
            'signal_type': 'HOLD',
            'price': current_price,
            'quantity': 0,
            'confidence': 0.5,
            'confidence_tier': 'low',
            'strength': 'weak',
            'status': 'IGNORED',
            'news_weight': position.get('news_weight', 0),
            'stop_loss': 0,
            'risk_score': 1,
            'metadata': {
                'reason': reason,
                'trend_tf': '1h',
                '1h_trend': get_trend_label((tf_signals or {}).get('1h')),
                'confidence_tier': confidence_tier or 'low',
                'strength': strength or 'weak',
                'tf_signals': tf_signals or {}
            }
        }
        
        logger.info(f"   📝 寫入 HOLD: {symbol} (status=IGNORED)")
        return api_post('/signals', signal_data)
    
    # ===== BUY/SELL 的處理：寫入 PENDING =====
    
    # ===== 信號去重邏輯 =====
    should_write, existing_signal = should_write_signal(symbol, signal_type, hours=24)
    
    if not should_write:
        # 不需要寫入信號（連續 HOLD 或重複信號）
        return {
            'status': 'ok', 
            'message': '信號跳過（去重）', 
            'signal_id': existing_signal.get('id') if existing_signal else None
        }
    
    # 如果存在相同方向舊信號，更新信心度
    if existing_signal and existing_signal['signal_type'] == signal_type:
        old_id = existing_signal['id']
        old_confidence = existing_signal.get('confidence', 0)
        
        # 取較高信心度
        updated_confidence = max(old_confidence, confidence)
        
        if update_signal_confidence(old_id, updated_confidence):
            return {
                'status': 'ok',
                'message': '更新現有信心度',
                'signal_id': old_id,
                'confidence_updated': True
            }
    
    # 計算止損價格 - 轉換為實際價格而非百分比
    # Bug fix: 之前直接傳 stop_loss_pct (5.0%) 而非價格，導致資料庫出現 $5.00 這種垃圾值
    if stop_loss_pct is None:
        stop_loss_pct = RISK_PARAMS['STOP_LOSS_PCT']
    
    # 根據信號類型計算止損價格
    if signal_type == 'BUY':
        stop_loss_price = round(current_price * (1 - stop_loss_pct / 100), 2)
    elif signal_type == 'SELL':
        # 賣出時止損是價格上限（防止過度上漲被軋空）
        stop_loss_price = round(current_price * (1 + stop_loss_pct / 100), 2)
    else:
        stop_loss_price = 0
    
    # 計算止盈價格 (默認 2 倍止損)
    take_profit_price = round(current_price * (1 + stop_loss_pct * 2 / 100), 2) if signal_type == 'BUY' else None
    
    # 計算建議股數 (假設每次操作 10% 倉位)
    # 動態計算：取可用現金的 10%，而非總資金的 10%
    try:
        from paper_trading_portfolio import get_paper_balance
        available_cash = get_paper_balance()
        position_capital = available_cash * 0.1  # 每次用可用現金的 10%
    except Exception:
        # 從系統配置獲取初始資金作為 fallback
        if SystemConfig:
            total_capital = SystemConfig.get_initial_balance()
        else:
            total_capital = 50000  # 預設值
        position_capital = total_capital * 0.1
    quantity = int(position_capital / current_price) if current_price > 0 else 0
    
    signal_data = {
        'symbol': symbol,
        'strategy_type': 'fox_analysis_v2',
        'signal_type': signal_type,
        'price': current_price,
        'quantity': quantity,
        'confidence': confidence,
        'status': 'PENDING',
        'news_weight': position.get('news_weight', 0),
        'stop_loss': stop_loss_price,
        'take_profit': take_profit_price,
        'risk_score': 1 if (news_ok and market_ok) else 0,
        'metadata': {
            'reason': reason,
            'market_ok': market_ok,
            'news_ok': news_ok,
            'created_at': datetime.now().isoformat(),
            'trend_tf': '1h',
            '1h_trend': get_trend_label((tf_signals or {}).get('1h')),
            '1d_trend': get_trend_label((tf_signals or {}).get('1d')),
            'confidence_tier': confidence_tier,
            'strength': strength,
            'confidence_components': confidence_components or [],
            'tf_signals': tf_signals or {},
            'rsi_profile': get_rsi_profile()
        }
    }
    
    logger.info(f"   📝 創建信號: {symbol} {signal_type} (信心度: {confidence})")
    return api_post('/signals', signal_data)


def analyze_position(position: Dict, market_data: Dict, max_age_minutes: Optional[float] = None) -> Dict:
    """分析單個持倉"""
    symbol = position.get('symbol')
    logger.info(f"\n🔍 分析持倉: {symbol}")
    
    # 0. 三週期共振檢查 (使用 TopK!)
    logger.info(f"   🌐 檢查三週期信號 (TopK)...")
    
    # 獲取三個週期的數據
    df_5m = get_kline_data(symbol, '5m', limit=201, max_age_minutes=max_age_minutes)
    df_1h = get_kline_data(symbol, '1h', limit=200, max_age_minutes=max_age_minutes)
    df_1d = get_kline_data(symbol, '1d', limit=200, max_age_minutes=max_age_minutes)
    
    # 使用 TopK 產生信號
    tf_signals = get_topk_signals_v2(symbol, df_5m=df_5m, df_1h=df_1h, df_1d=df_1d)
    consensus = tf_signals.get('consensus')
    method = tf_signals.get('method', 'unknown')
    
    logger.info(f"   📊 TopK 信號: 5m={tf_signals.get('5m')}, 1h={tf_signals.get('1h')}, 1d={tf_signals.get('1d')}")
    logger.info(f"   📊 共識: {consensus} (method: {method})")
    
    # HOLD → 直接寫入 HOLD，不繼續分析
    if consensus == 'HOLD':
        logger.info(f"   ⏭️ 無共識 (HOLD)，直接寫入 HOLD")
        return {
            'symbol': symbol,
            'signal_type': 'HOLD',
            'confidence': 0.5,
            'confidence_tier': 'low',
            'strength': 'weak',
            'news_ok': True,
            'market_ok': True,
            'reason': f'TopK: 5m={tf_signals.get("5m")}, 1h={tf_signals.get("1h")}, 1d={tf_signals.get("1d")}',
            'news_weight': 0,
            'position': position,
            'tf_signals': tf_signals,
            'agent_analyzed': False
        }
    
    # BUY 或 SELL → 繼續風控分析
    logger.info(f"   ✅ TopK 共識: {consensus}，繼續風控分析...")
    
    # 這裡未來會調用 Fox Agent
    # 目前先用現有邏輯
    logger.info(f"   (暫時使用現有邏輯，未來會調用 Agent)")
    
    # 1. 獲取新聞權重
    news_data = get_news_weight(symbol)
    news_degraded = news_data.get('degraded', False)
    news_weight_raw = news_data.get('total_weight')
    news_weight = 0 if (news_weight_raw is None or news_degraded) else (news_weight_raw or 0)
    if news_degraded:
        logger.warning(f"   新聞權重: DEGRADED (API error: {news_data.get('error_message', '?')})")
    else:
        logger.info(f"   新聞權重: {news_weight}")
    
    # 2. 檢查新聞風險（傳遞 news_data 以檢查 sync_status）
    news_ok, news_reason = check_news_risk(news_weight, news_data)
    logger.info(f"   新聞風險: {'✅ 通過' if news_ok else '❌ 失敗'} - {news_reason}")
    
    # 3. 檢查市場風險
    market_ok, market_reason = check_market_risk(market_data)
    logger.info(f"   市場風險: {'✅ 通過' if market_ok else '❌ 失敗'} - {market_reason}")
    
    # 4. 計算信心度
    confidence_info = calculate_confidence(position, news_data, market_data, tf_signals=tf_signals)
    confidence = confidence_info['confidence']
    confidence_tier = confidence_info['confidence_tier']
    strength = confidence_info['strength']
    logger.info(f"   信心度: {confidence} ({confidence_tier}/{strength})")
    
    # 5. 決定信號 (TopK 共識 + 信心度雙重確認)
    min_conf = RISK_PARAMS['MIN_CONFIDENCE']  # 0.60
    if consensus == 'BUY':
        confidence = quantize_confidence(confidence + 0.10)
        confidence_tier, strength = classify_confidence(confidence)
        if confidence >= min_conf:
            signal_type = 'BUY'
        else:
            signal_type = 'HOLD'
            logger.info(f"   ⚠️ {symbol} 共識 BUY 但信心度 {confidence} < {min_conf}，降級為 HOLD")
    elif consensus == 'SELL':
        # 檢查是否有持倉，沒有持倉則改為 HOLD
        current_qty = position.get('quantity', 0)
        if current_qty <= 0:
            signal_type = 'HOLD'
            logger.info(f"   ⚠️ {symbol} 無持倉，SELL 信號改為 HOLD")
        else:
            confidence = quantize_confidence(confidence + 0.10)
            confidence_tier, strength = classify_confidence(confidence)
            if confidence >= min_conf:
                signal_type = 'SELL'
            else:
                signal_type = 'HOLD'
                logger.info(f"   ⚠️ {symbol} 共識 SELL 但信心度 {confidence} < {min_conf}，降級為 HOLD")
    else:
        signal_type = 'HOLD'
    
    signal_reason = f"TopK 共識 ({consensus}) | 1h={get_trend_label(tf_signals.get('1h'))} | conf={confidence} tier={confidence_tier}" if signal_type != 'HOLD' else f'共識={consensus} conf={confidence} (未達門檻或無持倉)'
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
        'tf_signals': tf_signals,
        'confidence_tier': confidence_tier,
        'strength': strength,
        'confidence_components': confidence_info['components'],
        '1h_trend': get_trend_label(tf_signals.get('1h'))
    }


def process_pending_signals_from_db(dry_run: bool = False) -> List[Dict]:
    """
    從資料庫讀取 pending 信號，進行風控分析，寫入 orders
    """
    logger.info("=" * 60)
    logger.info("🦊 Fox Analysis - 處理 DB Pending 信號")
    logger.info("=" * 60)
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 讀取 pending 信號
        cursor.execute("""
            SELECT id, symbol, signal_type, price, quantity, confidence, metadata
            FROM signals
            WHERE status = 'pending'
            AND created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
        """)
        
        pending = cursor.fetchall()
        logger.info(f"📥 找到 {len(pending)} 筆 pending 信號")
        
        results = []
        for row in pending:
            signal_id, symbol, signal_type, price, quantity, confidence, metadata = row
            
            logger.info(f"\n📊 分析 {symbol}: {signal_type} @ ${price}")
            
            # 風控檢查 (簡化版)
            # 這裡應該加入完整風控邏輯
            
            if not dry_run:
                # 寫入 orders 表
                cursor.execute("""
                    INSERT INTO orders 
                    (symbol, order_type, quantity, price, status, created_at)
                    VALUES (%s, %s, %s, %s, 'pending', NOW())
                """, (symbol, signal_type, quantity or 0, price))
                
                # 更新信號狀態
                cursor.execute("""
                    UPDATE signals 
                    SET status = 'analyzed', updated_at = NOW()
                    WHERE id = %s
                """, (signal_id,))
                
                logger.info(f"   ✅ 已寫入 orders")
            else:
                logger.info(f"   � dry-run: 跳過寫入")
            
            results.append({'symbol': symbol, 'signal': signal_type})
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"\n✅ 完成 {len(results)} 筆信號處理")
        return results
        
    except Exception as e:
        logger.error(f"❌ 處理失敗: {e}")
        return []


def run_analysis(dry_run: bool = False, max_age_minutes: Optional[float] = None) -> List[Dict]:
    """
    執行 Fox 分析 - 分析 WATCHLIST 中所有股票
    
    Parameters:
    - dry_run: 模擬運行，不實際創建信號
    - max_age_minutes: K線數據最大年齡(分鐘)
    """
    logger.info("=" * 60)
    logger.info("🦊 Fox Analysis v2 開始")
    logger.info("=" * 60)
    
    # 1. 獲取 WATCHLIST 股票列表
    watchlist = get_watchlist()
    if not watchlist:
        logger.warning("⚠️ 沒有 WATCHLIST，跳過分析")
        return []
    
    # 2. 獲取持倉（用於判斷是否已持有）
    positions = get_positions()
    position_dict = {p['symbol']: p for p in positions}
    
    # ===== 風控檢查：總持倉金額 =====
    risk_check = check_total_position(positions)
    if not risk_check['passed']:
        logger.error(f"❌ 風控阻擋: 總持倉過高 - {risk_check['reason']}")
        logger.info(f"   當前持倉總額: ${risk_check.get('total', 0):,.2f}")
        # 風控失敗不放行！
        return []
    else:
        logger.info(f"   ✅ 風控通過: 持倉總額 ${risk_check['total']:,.2f}")
    
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
            # 從 K 線獲取當前價格
            stock_price = get_stock_price(symbol)
            position = {
                'symbol': symbol,
                'quantity': 0,
                'avg_price': 0,
                'current_price': stock_price,
                'average_cost': stock_price  # 用於 quantity 計算
            }
        
        logger.info(f"\n📈 分析 {symbol} {'(有持倉)' if current_qty > 0 else '(無持倉)'}")
        
        # 分析股票 (傳入 max_age_minutes)
        result = analyze_position(position, market_data, max_age_minutes=max_age_minutes)
        
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
                reason=result['reason'],
                market_data=market_data,
                tf_signals=result.get('tf_signals'),
                confidence_tier=result.get('confidence_tier'),
                strength=result.get('strength'),
                confidence_components=result.get('confidence_components')
            )
            if response.get('status') == 'ok':
                logger.info(f"   ✅ 信號創建成功: ID={response.get('signal_id')}")
                result['signal_id'] = response.get('signal_id')
            else:
                logger.error(f"   ❌ 信號創建失敗: {response.get('message')}")
            signals_created.append(result)
    
    # 總結
    logger.info("\n" + "=" * 60)
    logger.info("📊 Fox Analysis v2 完成")
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
    parser = argparse.ArgumentParser(description='Fox Analysis Script v2')
    parser.add_argument('--dry-run', action='store_true', help='模擬運行，不實際創建信號')
    parser.add_argument('--force', action='store_true', help='強制執行，忽略交易時段檢查')
    parser.add_argument(
        '--max-age', 
        type=float, 
        default=None,
        help='K線數據最大年齡(分鐘)，默認根據週期自動設定 (5m:10分, 1h:60分, 1d:1440分)'
    )
    parser.add_argument(
        '--from-db',
        action='store_true',
        help='從資料庫讀取 pending 信號進行分析'
    )
    parser.add_argument(
        '--paper-trading',
        action='store_true',
        help='模擬交易模式：信號寫入 paper_orders 表'
    )
    args = parser.parse_args()
    
    # 如果指定從 DB 讀取信號
    if args.from_db:
        process_pending_signals_from_db(dry_run=args.dry_run, paper_trading=args.paper_trading)
        return
    
    # 檢查是否在交易時段 (自動判斷冬令時/夏令時)
    if HAS_MARKET_HOURS and not args.force:
        dst_status = "夏令時" if is_dst_us() else "冬令時"
        logger.info(f"📅 當前模式: {dst_status}")
        
        if not should_update_kline():
            logger.info("⏸️ 非交易時段，跳過分析")
            return
        logger.info("✅ 交易時段，開始分析...")
    
    run_analysis(dry_run=args.dry_run, max_age_minutes=args.max_age)


if __name__ == '__main__':
    main()
