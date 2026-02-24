#!/usr/bin/env python3
"""
Fox News Update Script
新聞更新腳本 - 搜索市場熱門新聞 + 個股新聞，分析權重並寫入數據庫

用法:
    python fox_news_update.py

API Base: http://localhost:8080/api/v1
"""

import requests
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
import time
import xml.etree.ElementTree as ET
import re
import os

# 禁用代理设置
os.environ['no_proxy'] = '*'
os.environ['NO_PROXY'] = '*'

# 创建禁用环境代理的 session
session = requests.Session()
session.trust_env = False

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# API 配置
API_BASE = 'http://localhost:8080/api/v1'

# RSS 新聞源（使用正確的 URL）
RSS_FEEDS = {
    'market': [
        'https://feeds.content.dowjones.io/public/rss/mw_topstories',
    ],
    'stock': [
        'https://feeds.content.dowjones.io/public/rss/mw_topstories',
    ]
}


def api_get(endpoint: str, params: dict = None) -> dict:
    """發送 GET 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = session.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API GET 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


def api_post(endpoint: str, data: dict) -> dict:
    """發送 POST 請求"""
    url = f"{API_BASE}{endpoint}"
    try:
        resp = session.post(url, json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API POST 請求失敗: {url} - {e}")
        return {'status': 'error', 'message': str(e)}


def get_positions() -> List[Dict]:
    """獲取持倉列表"""
    # 使用 portfolio/positions 獲取真實持倉
    result = api_get('/portfolio/positions')
    
    if result.get('status') == 'ok':
        positions = result.get('positions', [])
        return [p['symbol'] for p in positions if p.get('shares', 0) > 0]
    return []


def clean_html(text: str) -> str:
    """清理 HTML 標籤"""
    if not text:
        return ''
    return re.sub('<[^<]+?>', '', text)[:500]


def fetch_rss_news(feeds: List[str], symbol: str = None) -> List[Dict]:
    """通過 RSS 獲取新聞"""
    news_list = []
    
    for feed_url in feeds:
        try:
            resp = session.get(feed_url, timeout=15)
            if resp.status_code != 200:
                continue
                
            root = ET.fromstring(resp.text)
            items = root.findall('.//item')
            
            for item in items[:5]:
                title_elem = item.find('title')
                desc_elem = item.find('description')
                link_elem = item.find('link')
                
                title = title_elem.text if title_elem is not None and title_elem.text else ''
                content = clean_html(desc_elem.text) if desc_elem is not None and desc_elem.text else ''
                link = link_elem.text if link_elem is not None else ''
                
                if not title:
                    continue
                    
                news_list.append({
                    'symbol': symbol or 'MARKET',
                    'title': title,
                    'content': content,
                    'source': 'MarketWatch',
                    'url': link,
                    'news_type': 'stock' if symbol else 'market'
                })
                
        except Exception as e:
            logger.warning(f"   獲取 RSS 失敗: {feed_url} - {e}")
    
    return news_list


def search_market_news() -> List[Dict]:
    """搜索市場熱門新聞"""
    logger.info("🔍 搜索市場熱門新聞...")
    
    news_list = []
    
    # 使用 RSS 獲取市場新聞
    news_list.extend(fetch_rss_news(RSS_FEEDS.get('market', [])))
    
    logger.info(f"   找到 {len(news_list)} 條市場新聞")
    return news_list


def search_stock_news(symbol: str) -> List[Dict]:
    """搜索個股新聞"""
    logger.info(f"   🔍 搜索 {symbol} 新聞...")
    
    news_list = []
    
    # 使用 RSS 獲取新聞並過濾
    feeds = RSS_FEEDS.get('stock', [])
    all_news = fetch_rss_news(feeds, symbol)
    
    # 過濾相關新聞（標題或內容包含股票代碼）
    symbol_lower = symbol.lower()
    for news in all_news:
        if symbol_lower in news['title'].lower() or symbol_lower in news['content'].lower():
            news['symbol'] = symbol  # 確保符號正確
            news_list.append(news)
    
    # 如果沒有過濾結果，添加一些通用新聞作為替代
    if not news_list and all_news:
        for news in all_news[:2]:
            news['symbol'] = symbol
            news_list.append(news)
    
    return news_list


def analyze_news(news_item: Dict) -> Dict:
    """分析新聞權重"""
    result = api_post('/news/analyze', {
        'title': news_item['title'],
        'content': news_item['content'],
        'news_type': news_item.get('news_type', 'general')
    })
    
    if result.get('status') == 'ok':
        return result.get('analysis', {})
    else:
        logger.warning(f"   分析失敗: {result.get('message')}")
        return {'weight': 0, 'sentiment': 'neutral'}


def save_news(news_item: Dict, analysis: Dict) -> bool:
    """寫入新聞到數據庫"""
    data = {
        'symbol': news_item['symbol'],
        'title': news_item['title'],
        'content': news_item['content'],
        'weight': analysis.get('weight', 0),
        'sentiment': analysis.get('sentiment', 'neutral'),
        'source': news_item.get('source', ''),
        'url': news_item.get('url', ''),
        'news_type': news_item.get('news_type', 'general')
    }
    
    result = api_post('/news', data)
    
    if result.get('status') == 'ok':
        return True
    else:
        logger.error(f"   保存失敗: {result.get('message')}")
        return False


def run_news_update():
    """執行新聞更新"""
    logger.info("=" * 60)
    logger.info("🦊 Fox News Update 開始")
    logger.info("=" * 60)
    
    # 1. 獲取持倉列表
    symbols = get_positions()
    logger.info(f"📊 持倉股票: {symbols}")
    
    # 2. 搜索市場熱門新聞
    all_news = search_market_news()
    
    # 3. 遍歷持倉股票，搜索個股新聞
    for symbol in symbols:
        stock_news = search_stock_news(symbol)
        all_news.extend(stock_news)
    
    logger.info(f"\n📰 總共找到 {len(all_news)} 條新聞")
    
    # 4. 分析並寫入每條新聞
    saved_count = 0
    for news_item in all_news:
        if not news_item.get('title'):
            continue
            
        # 分析權重
        analysis = analyze_news(news_item)
        
        # 寫入數據庫
        if save_news(news_item, analysis):
            saved_count += 1
            logger.info(f"   ✅ {news_item['symbol']}: {news_item['title'][:50]}... (權重: {analysis.get('weight')}, 情感: {analysis.get('sentiment')})")
        
        # 避免請求過快
        time.sleep(0.3)
    
    # 總結
    logger.info("\n" + "=" * 60)
    logger.info("📊 Fox News Update 完成")
    logger.info(f"   處理的股票: {len(symbols)}")
    logger.info(f"   總新聞數: {len(all_news)}")
    logger.info(f"   成功寫入: {saved_count}")
    logger.info("=" * 60)
    
    return saved_count


if __name__ == '__main__':
    run_news_update()
