#!/usr/bin/env python3
"""
News Finance Analysis Agent
分析持倉股票的新聞，輸出標準化 risk score (-1.0 ~ 1.0)

- 負面新聞多 → risk > 0
- 正面新聞多 → risk < 0
- 中性 → risk ≈ 0

用法:
    python news_finance_analysis.py [--symbol SYMBOL]
"""

import os
import sys
import logging
import argparse
import requests
import mysql.connector
from typing import Dict, List, Optional
from datetime import datetime, timedelta

# 清除代理
for _proxy_key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(_proxy_key, None)
os.environ.setdefault('NO_PROXY', 'localhost,127.0.0.1')

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

# API 配置
API_BASE = 'http://localhost:8080/api/v1'


def api_get(endpoint: str, params: dict = None) -> dict:
    """發送 GET 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"API GET 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


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
        
        # 從 paper_positions 獲取持倉
        cursor.execute("""
            SELECT DISTINCT symbol FROM paper_positions 
            WHERE quantity > 0
        """)
        rows = cursor.fetchall()
        
        # 也從 positions 獲取
        cursor.execute("""
            SELECT DISTINCT symbol FROM positions 
            WHERE quantity > 0
        """)
        rows2 = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        symbols = set([row['symbol'] for row in rows])
        symbols.update([row['symbol'] for row in rows2])
        return list(symbols)
    except Exception as e:
        logger.error(f"獲取持倉失敗: {e}")
        return []


def analyze_news_for_symbol(symbol: str, hours: int = 24) -> Dict:
    """
    分析單支股票的新聞風險
    
    Returns:
    {
        'symbol': str,
        'news_risk': float (-1.0 ~ 1.0),
        'reasoning': str,
        'metadata': dict
    }
    """
    # 去除市場前綴
    if symbol.startswith('US.'):
        api_symbol = symbol.split('.', 1)[1]
    else:
        api_symbol = symbol
    
    # 獲取新聞權重
    result = api_get(f'/news/weight/{api_symbol}', {'hours': hours})
    
    if result.get('status') != 'ok':
        return {
            'symbol': symbol,
            'news_risk': 0.0,
            'reasoning': f"API 失敗: {result.get('message')}",
            'metadata': {'api_error': True}
        }
    
    breakdown = result.get('breakdown', {})
    positive = breakdown.get('positive', 0)
    negative = breakdown.get('negative', 0)
    neutral = breakdown.get('neutral', 0)
    total_weight = result.get('total_weight', 0)
    news_count = result.get('news_count', 0)
    
    # 計算風險分數
    # 邏輯:
    # - 負面新聞多 → risk > 0
    # - 正面新聞多 → risk < 0
    # - 中性 → risk ≈ 0
    
    total = positive + negative + neutral
    if total == 0:
        # 無新聞 = 中性
        news_risk = 0.0
        reasoning = "無新聞，中性"
    else:
        # 計算正負比率
        pos_ratio = positive / total if total > 0 else 0
        neg_ratio = negative / total if total > 0 else 0
        
        # 計算淨情緒 (-1 ~ 1)
        net_sentiment = pos_ratio - neg_ratio  # 正面為負數，負面為正數
        
        # 權重影響 (新聞數量越多，影響越大)
        weight_factor = min(news_count / 10, 1.0)  # 最多 10 篇新聞影響最大
        
        # 最終風險分數
        # 負面多 = 正風險，正面多 = 負風險
        news_risk = round(net_sentiment * weight_factor, 3)
        
        # 生成 reasoning
        if news_risk > 0.3:
            reasoning = f"負面新聞較多 (pos:{positive}, neg:{negative}, weight:{total_weight})"
        elif news_risk < -0.3:
            reasoning = f"正面新聞較多 (pos:{positive}, neg:{negative}, weight:{total_weight})"
        else:
            reasoning = f"新聞中性 (pos:{positive}, neg:{negative}, neutral:{neutral})"
    
    metadata = {
        'positive': positive,
        'negative': negative,
        'neutral': neutral,
        'total_weight': total_weight,
        'news_count': news_count,
        'api_status': result.get('status'),
        'sync_status': result.get('sync_status', 'unknown'),
        'analyzed_at': datetime.now().isoformat()
    }
    
    return {
        'symbol': symbol,
        'news_risk': news_risk,
        'reasoning': reasoning,
        'metadata': metadata
    }


def save_agent_score(symbol: str, agent_id: str, score_type: str, 
                    score: float, reasoning: str, metadata: dict = None) -> bool:
    """寫入 agent_scores 表"""
    try:
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        
        # 使用 INSERT ... ON DUPLICATE KEY UPDATE 進行 upsert
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


def run_analysis(symbols: List[str] = None) -> List[Dict]:
    """
    執行新聞分析
    
    Args:
        symbols: 指定股票列表，None 時從持倉+WATCHLIST 獲取
    """
    logger.info("=" * 50)
    logger.info("📰 News Finance Analysis Agent 開始")
    logger.info("=" * 50)
    
    # 獲取要分析的股票
    if symbols is None:
        watchlist = get_watchlist_symbols()
        positions = get_positions_symbols()
        # 合併去重
        symbols = list(set(watchlist + positions))
        logger.info(f"分析股票列表 (WATCHLIST + 持倉): {len(symbols)} 檔")
    else:
        logger.info(f"分析指定股票: {len(symbols)} 檔")
    
    results = []
    for symbol in symbols:
        logger.info(f"📰 分析 {symbol}...")
        
        analysis = analyze_news_for_symbol(symbol)
        
        # 寫入數據庫
        success = save_agent_score(
            symbol=symbol,
            agent_id='tm-news-finance',
            score_type='news_risk',
            score=analysis['news_risk'],
            reasoning=analysis['reasoning'],
            metadata=analysis['metadata']
        )
        
        if success:
            logger.info(f"   ✅ news_risk = {analysis['news_risk']} ({analysis['reasoning']})")
            results.append(analysis)
        else:
            logger.error(f"   ❌ 寫入失敗")
    
    # 統計
    positive_count = sum(1 for r in results if r['news_risk'] > 0.1)
    negative_count = sum(1 for r in results if r['news_risk'] < -0.1)
    neutral_count = len(results) - positive_count - negative_count
    
    logger.info("=" * 50)
    logger.info(f"📊 分析完成: {len(results)} 檔")
    logger.info(f"   正面風險 (risk > 0.1): {positive_count}")
    logger.info(f"   負面風險 (risk < -0.1): {negative_count}")
    logger.info(f"   中性 (-0.1 ~ 0.1): {neutral_count}")
    logger.info("=" * 50)
    
    return results


def main():
    parser = argparse.ArgumentParser(description='News Finance Analysis Agent')
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
