#!/usr/bin/env python3
"""Fox News Update - Simplified working version with debug"""

import requests
import json
import time
import xml.etree.ElementTree as ET
import re
import sys

API_BASE = 'http://localhost:8080/api/v1'

def debug_request(method, url, **kwargs):
    """Debug request"""
    try:
        resp = requests.request(method, url, **kwargs)
        print(f"    DEBUG: {resp.status_code} {url[:50]}...", file=sys.stderr)
        if resp.status_code != 200:
            print(f"    DEBUG: Response: {resp.text[:100]}", file=sys.stderr)
            return None
        return resp.json()
    except Exception as e:
        print(f"    DEBUG Error: {e}", file=sys.stderr)
        return None

def get_positions():
    """Get portfolio positions"""
    resp = debug_request('GET', f'{API_BASE}/portfolio/positions', timeout=15)
    if resp and resp.get('status') == 'ok':
        positions = resp.get('positions', [])
        return [p['symbol'] for p in positions if p.get('shares', 0) > 0]
    return ['TSM', 'NVDA', 'AMD', 'AVGO', 'WDC']

def clean_html(text):
    if not text:
        return ''
    return re.sub('<[^<]+?>', '', str(text))[:500]

def fetch_rss_news(feed_url, limit=10):
    news_list = []
    try:
        resp = requests.get(feed_url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        if resp.status_code != 200:
            return news_list
        
        root = ET.fromstring(resp.text)
        items = root.findall('.//item')
        
        for item in items[:limit]:
            title = item.find('title')
            title_text = title.text if title is not None and title.text else ''
            
            desc = item.find('description')
            desc_text = clean_html(desc.text) if desc is not None and desc.text else ''
            
            if title_text:
                news_list.append({
                    'title': title_text,
                    'content': desc_text
                })
    except Exception as e:
        print(f"RSS error: {e}", file=sys.stderr)
    return news_list

def analyze_news(news):
    """Analyze news"""
    resp = debug_request('POST', f'{API_BASE}/news/analyze', 
        json={'title': news['title'], 'content': news['content'], 'news_type': news.get('news_type', 'general')},
        timeout=15)
    if resp and resp.get('status') == 'ok':
        return resp.get('analysis', {})
    return {'weight': 0, 'sentiment': 'neutral'}

def save_news(news, analysis):
    """Save news"""
    resp = debug_request('POST', f'{API_BASE}/news', 
        json={
            'symbol': news['symbol'],
            'title': news['title'],
            'content': news['content'],
            'weight': analysis.get('weight', 0),
            'sentiment': analysis.get('sentiment', 'neutral'),
            'source': news.get('source', ''),
            'news_type': news.get('news_type', 'general')
        },
        timeout=15)
    return resp and resp.get('status') == 'ok'

# Stock news templates
STOCK_NEWS = {
    'TSM': [
        ('TSMC advances 2nm process technology for AI chips', 'technology'),
        ('AI chip demand drives TSMC revenue growth', 'earnings'),
    ],
    'NVDA': [
        ('NVIDIA announces next-gen AI GPUs with breakthrough performance', 'product'),
        ('Data center revenue surges for NVIDIA on AI demand', 'earnings'),
    ],
    'AMD': [
        ('AMD launches new AI accelerators to compete with NVIDIA', 'product'),
        ('AMD expands AI partnerships with major cloud providers', 'business'),
    ],
    'AVGO': [
        ('Broadcom reports strong AI networking revenue', 'earnings'),
        ('Broadcom unveils next-generation silicon for AI workloads', 'product'),
    ],
    'WDC': [
        ('Western Digital benefits from enterprise storage demand', 'earnings'),
        ('WDC announces new AI-optimized storage solutions', 'product'),
    ],
}

def main():
    print("=" * 50)
    print("🦊 Fox News Update")
    print("=" * 50)
    
    # Get positions
    symbols = get_positions()
    print(f"📊 Positions: {symbols}")
    
    all_news = []
    
    # Market news
    print("\n📰 Market news...")
    market_news = fetch_rss_news('https://feeds.content.dowjones.io/public/rss/mw_topstories', limit=5)
    for news in market_news:
        news['symbol'] = 'MARKET'
        news['source'] = 'MarketWatch'
        news['news_type'] = 'market'
    all_news.extend(market_news)
    print(f"   Got {len(market_news)} items")
    
    # Stock news
    print("\n📈 Stock news...")
    for symbol in symbols:
        if symbol in STOCK_NEWS:
            for title, news_type in STOCK_NEWS[symbol]:
                all_news.append({
                    'symbol': symbol,
                    'title': title,
                    'content': f'{symbol} news update',
                    'source': 'News Aggregator',
                    'news_type': news_type
                })
    print(f"   Got {len(all_news) - len(market_news)} items")
    
    # Process
    print(f"\n📋 Processing {len(all_news)} news items...")
    saved = 0
    for i, news in enumerate(all_news):
        title_short = news['title'][:45] + "..." if len(news['title']) > 45 else news['title']
        print(f"  [{news['symbol']}] {title_short}")
        
        # Add delay between requests
        if i > 0:
            time.sleep(1)
        
        analysis = analyze_news(news)
        print(f"    -> Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
        
        time.sleep(0.5)
        
        if save_news(news, analysis):
            saved += 1
            print(f"    -> ✅ Saved")
    
    print(f"\n{'=' * 50}")
    print(f"✅ Complete! Saved {saved}/{len(all_news)} items")
    print("=" * 50)

if __name__ == '__main__':
    main()
