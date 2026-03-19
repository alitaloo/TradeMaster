#!/usr/bin/env python3
"""
Strategy Analysis Agent
分析 K 線/技術指標，輸出 signal_score (-1.0 ~ 1.0)

- 強烈買入信號 → score > 0.5
- 觀望 → -0.5 ~ 0.5
- 強烈賣出信號 → score < -0.5

用法:
    python strategy_analysis.py [--symbol SYMBOL]
"""

import os
import sys
import logging
import argparse
import mysql.connector
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# 清除代理
for _proxy_key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(_proxy_key, None)
os.environ.setdefault('NO_PROXY', 'localhost,127.0.0.1')

# 富途 API
try:
    import futu as ft
    from futu.quote.open_quote_context import OpenQuoteContext
    from futu.common.constant import KLType
    ft.OpenQuoteContext = OpenQuoteContext
    ft.KLType = KLType
    HAS_FUTU = True
except ImportError:
    HAS_FUTU = False

# 項目根目錄
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.database import MYSQL_CONFIG

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111


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


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """計算 MACD"""
    ema_fast = df['close'].ewm(span=fast).mean()
    ema_slow = df['close'].ewm(span=slow).mean()
    macd = ema_fast - ema_slow
    macd_signal = macd.ewm(span=signal).mean()
    histogram = macd - macd_signal
    return macd, macd_signal, histogram


# ==================== K線數據獲取 ====================
def get_kline_from_db(symbol: str, timeframe: str, limit: int = 100) -> Optional[pd.DataFrame]:
    """從資料庫獲取 K 線數據"""
    try:
        # 確保有 US. 前綴
        if not symbol.startswith('US.'):
            symbol = f'US.{symbol}'
        
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        
        # 轉換 timeframe
        interval_map = {'5m': '5m', '1h': '1h', '1d': '1d', '15m': '15m', '30m': '30m'}
        interval = interval_map.get(timeframe, '1h')
        
        query = """
            SELECT timestamp, open_price, high_price, low_price, close_price, volume
            FROM kline_cache
            WHERE symbol = %s AND interval_val = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """
        
        cursor.execute(query, (symbol, interval, limit))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not rows:
            return None
        
        df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='mixed')
        df = df.sort_values('timestamp')  # oldest first
        
        return df
        
    except Exception as e:
        logger.error(f"獲取 K 線失敗: {symbol} {timeframe} - {e}")
        return None


def get_realtime_kline(symbol: str, timeframe: str, limit: int = 200) -> Optional[pd.DataFrame]:
    """從富途 API 獲取實時 K 線數據"""
    if not HAS_FUTU:
        return None
    
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex(('127.0.0.1', 11111))
        sock.close()
        if result != 0:
            return None
    except Exception:
        try:
            sock.close()
        except:
            pass
        return None
    
    try:
        timeframe_map = {
            '5m': ft.KLType.K_5M,
            '1h': ft.KLType.K_60M,
            '1d': ft.KLType.K_DAY,
            '15m': ft.KLType.K_15M,
            '30m': ft.KLType.K_30M,
        }
        ktype = timeframe_map.get(timeframe)
        if ktype is None:
            return None
        
        quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        
        # 時間範圍
        if timeframe == '5m':
            start_date = (datetime.now() - pd.Timedelta(days=3)).strftime('%Y-%m-%d')
        elif timeframe == '1h':
            start_date = (datetime.now() - pd.Timedelta(days=60)).strftime('%Y-%m-%d')
        else:
            start_date = (datetime.now() - pd.Timedelta(days=365)).strftime('%Y-%m-%d')
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        
        result = quote_ctx.request_history_kline(
            symbol,
            start=start_date,
            end=end_date,
            ktype=ktype,
            max_count=limit
        )
        
        quote_ctx.close()
        
        if len(result) == 3:
            ret, data, extra = result
        else:
            return None
        
        if ret != 0 or data is None or len(data) == 0:
            return None
        
        df = pd.DataFrame({
            'timestamp': pd.to_datetime(data['time_key']),
            'open': data['open'].astype(float),
            'high': data['high'].astype(float),
            'low': data['low'].astype(float),
            'close': data['close'].astype(float),
            'volume': data['volume'].astype(int)
        })
        
        df = df.sort_values('timestamp')
        return df
        
    except Exception as e:
        logger.error(f"富途 K 線獲取失敗: {symbol} {timeframe} - {e}")
        return None


def get_kline_data(symbol: str, timeframe: str, limit: int = 200) -> Optional[pd.DataFrame]:
    """獲取 K 線數據：優先實時，失敗則用 cache"""
    # 優先嘗試實時
    df = get_realtime_kline(symbol, timeframe, limit)
    if df is not None and len(df) > 0:
        return df
    
    # Fallback 到 DB cache
    return get_kline_from_db(symbol, timeframe, limit)


# ==================== 信號計算 ====================
def calculate_indicator_signals(df: pd.DataFrame) -> Dict:
    """
    計算多個指標的信號，返回綜合評分
    
    Returns:
    {
        'rsi': float (-1 ~ 1, 負=超賣/買入, 正=超買/賣出),
        'stochastic': float,
        'bollinger': float,
        'macd': float,
        'overall': float (-1 ~ 1)
    }
    """
    signals = {}
    
    # RSI
    try:
        rsi = calculate_rsi(df, 14)
        latest_rsi = rsi.iloc[-1]
        if pd.notna(latest_rsi):
            # RSI < 30 超賣 = 買入信號 (-1)
            # RSI > 70 超買 = 賣出信號 (+1)
            signals['rsi'] = (latest_rsi - 50) / 50  # 標準化到 -1 ~ 1
    except Exception:
        signals['rsi'] = 0
    
    # Stochastic
    try:
        k, d = calculate_stochastic(df, 14, 3)
        latest_k = k.iloc[-1]
        if pd.notna(latest_k):
            # K < 20 超賣 = 買入, K > 80 超買 = 賣出
            signals['stochastic'] = (latest_k - 50) / 50
    except Exception:
        signals['stochastic'] = 0
    
    # Bollinger
    try:
        upper, middle, lower = calculate_bollinger(df, 20, 2)
        latest_close = df['close'].iloc[-1]
        if pd.notna(upper.iloc[-1]):
            # 價格接觸下軌 = 買入，接觸上軌 = 賣出
            bb_position = (latest_close - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
            signals['bollinger'] = (bb_position - 0.5) * 2  # 標準化
    except Exception:
        signals['bollinger'] = 0
    
    # MACD
    try:
        macd, signal, hist = calculate_macd(df)
        latest_hist = hist.iloc[-1]
        if pd.notna(latest_hist):
            # Histogram > 0 上漲趨勢 = 買入, < 0 下跌趨勢 = 賣出
            # 標準化：取相對於價格的比率
            price = df['close'].iloc[-1]
            signals['macd'] = np.clip(latest_hist / price * 100, -1, 1)
    except Exception:
        signals['macd'] = 0
    
    # 計算綜合信號
    valid_signals = [v for v in signals.values() if v != 0]
    if valid_signals:
        signals['overall'] = np.mean(valid_signals)
    else:
        signals['overall'] = 0
    
    return signals


def analyze_strategy_for_symbol(symbol: str) -> Dict:
    """
    分析單支股票的技術面信號
    
    Returns:
    {
        'symbol': str,
        'strategy_signal': float (-1.0 ~ 1.0),
        'reasoning': str,
        'metadata': dict
    }
    """
    # 確保有 US. 前綴
    if not symbol.startswith('US.'):
        full_symbol = f'US.{symbol}'
    else:
        full_symbol = symbol
    
    # 獲取多個週期的數據
    timeframes = ['1h', '1d']
    all_signals = {}
    
    for tf in timeframes:
        df = get_kline_data(full_symbol, tf, limit=200)
        if df is not None and len(df) >= 30:
            signals = calculate_indicator_signals(df)
            all_signals[tf] = signals
    
    if not all_signals:
        return {
            'symbol': symbol,
            'strategy_signal': 0.0,
            'reasoning': '無法獲取 K 線數據',
            'metadata': {'error': 'no_data'}
        }
    
    # 綜合各週期信號
    # 1h 信號權重 40%, 1d 信號權重 60%
    overall_signals = []
    weights = {'1h': 0.4, '1d': 0.6}
    
    for tf, signals in all_signals.items():
        overall_signals.append(signals.get('overall', 0) * weights.get(tf, 0.5))
    
    strategy_signal = round(sum(overall_signals), 3)
    
    # 限制在 -1 ~ 1 範圍
    strategy_signal = max(-1.0, min(1.0, strategy_signal))
    
    # 生成 reasoning
    if strategy_signal > 0.5:
        signal_label = "強烈買入"
    elif strategy_signal > 0.2:
        signal_label = "溫和買入"
    elif strategy_signal > -0.2:
        signal_label = "觀望"
    elif strategy_signal > -0.5:
        signal_label = "溫和賣出"
    else:
        signal_label = "強烈賣出"
    
    # 收集各指標詳情
    indicator_details = {}
    for tf, signals in all_signals.items():
        indicator_details[tf] = {
            'rsi': round(signals.get('rsi', 0), 3),
            'stochastic': round(signals.get('stochastic', 0), 3),
            'bollinger': round(signals.get('bollinger', 0), 3),
            'macd': round(signals.get('macd', 0), 3),
            'overall': round(signals.get('overall', 0), 3)
        }
    
    reasoning = f"{signal_label} (signal={strategy_signal})"
    
    metadata = {
        'indicators': indicator_details,
        'timeframes': list(all_signals.keys()),
        'analyzed_at': datetime.now().isoformat()
    }
    
    return {
        'symbol': symbol,
        'strategy_signal': strategy_signal,
        'reasoning': reasoning,
        'metadata': metadata
    }


def save_agent_score(symbol: str, agent_id: str, score_type: str, 
                    score: float, reasoning: str, metadata: dict = None) -> bool:
    """寫入 agent_scores 表"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO agent_scores (symbol, agent_id, score_type, score, reasoning, metadata)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
                score = VALUES(score),
                reasoning = VALUES(reasoning),
                metadata = VALUES(metadata),
                updated_at = NOW()
        """
        
        import json
        metadata_json = json.dumps(metadata) if metadata else None
        
        cursor.execute(sql, (symbol, agent_id, score_type, score, reasoning, metadata_json))
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
    except Exception as e:
        logger.error(f"寫入 agent_scores 失敗: {e}")
        return False


def get_watchlist_symbols() -> List[str]:
    """從 MySQL 獲取 WATCHLIST 股票列表"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT symbol FROM stocks WHERE enabled = 1 ORDER BY symbol")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [row['symbol'] for row in rows]
    except Exception as e:
        logger.error(f"獲取 WATCHLIST 失敗: {e}")
        return []


def get_positions_symbols() -> List[str]:
    """從持倉中獲取股票列表"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT DISTINCT symbol FROM paper_positions WHERE quantity > 0")
        rows = cursor.fetchall()
        
        cursor.execute("SELECT DISTINCT symbol FROM positions WHERE quantity > 0")
        rows2 = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        symbols = set([row['symbol'] for row in rows])
        symbols.update([row['symbol'] for row in rows2])
        return list(symbols)
    except Exception as e:
        logger.error(f"獲取持倉失敗: {e}")
        return []


def run_analysis(symbols: List[str] = None) -> List[Dict]:
    """
    執行技術分析
    
    Args:
        symbols: 指定股票列表，None 時從持倉+WATCHLIST 獲取
    """
    logger.info("=" * 50)
    logger.info("📈 Strategy Analysis Agent 開始")
    logger.info("=" * 50)
    
    # 獲取要分析的股票
    if symbols is None:
        watchlist = get_watchlist_symbols()
        positions = get_positions_symbols()
        symbols = list(set(watchlist + positions))
        logger.info(f"分析股票列表 (WATCHLIST + 持倉): {len(symbols)} 檔")
    else:
        logger.info(f"分析指定股票: {len(symbols)} 檔")
    
    results = []
    for symbol in symbols:
        logger.info(f"📈 分析 {symbol}...")
        
        analysis = analyze_strategy_for_symbol(symbol)
        
        # 寫入數據庫
        success = save_agent_score(
            symbol=symbol,
            agent_id='tm-strategist',
            score_type='strategy_signal',
            score=analysis['strategy_signal'],
            reasoning=analysis['reasoning'],
            metadata=analysis['metadata']
        )
        
        if success:
            logger.info(f"   ✅ strategy_signal = {analysis['strategy_signal']} ({analysis['reasoning']})")
            results.append(analysis)
        else:
            logger.error(f"   ❌ 寫入失敗")
    
    # 統計
    buy_count = sum(1 for r in results if r['strategy_signal'] > 0.5)
    sell_count = sum(1 for r in results if r['strategy_signal'] < -0.5)
    neutral_count = len(results) - buy_count - sell_count
    
    logger.info("=" * 50)
    logger.info(f"📊 分析完成: {len(results)} 檔")
    logger.info(f"   強烈買入 (signal > 0.5): {buy_count}")
    logger.info(f"   強烈賣出 (signal < -0.5): {sell_count}")
    logger.info(f"   觀望 (-0.5 ~ 0.5): {neutral_count}")
    logger.info("=" * 50)
    
    return results


def main():
    parser = argparse.ArgumentParser(description='Strategy Analysis Agent')
    parser.add_argument('--symbol', type=str, help='指定股票代碼')
    parser.add_argument('--symbols', type=str, help='逗號分隔的股票代碼列表')
    args = parser.parse_args()
    
    if args.symbol:
        symbols = [args.symbol]
    elif args.symbols:
        symbols = [s.strip() for s in args.symbols.split(',')]
    else:
        symbols = None
    
    run_analysis(symbols)


if __name__ == '__main__':
    main()
