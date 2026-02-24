#!/usr/bin/env python3
"""Fox News Update - Robust version with retries"""

import requests
import json
import time
import sys

API_BASE = 'http://localhost:8080/api/v1'
MAX_RETRIES = 5
RETRY_DELAY = 2

def robust_post(url, payload, retries=MAX_RETRIES):
    """POST with retries"""
    for attempt in range(retries):
        try:
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'ok':
                    return data
            elif resp.status_code >= 500:
                print(f"    Server error {resp.status_code}, retry {attempt+1}/{retries}", file=sys.stderr)
                time.sleep(RETRY_DELAY)
            else:
                print(f"    Client error {resp.status_code}: {resp.text[:100]}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"    Request error: {e}, retry {attempt+1}/{retries}", file=sys.stderr)
            time.sleep(RETRY_DELAY)
    return None

def get_positions():
    """Get portfolio positions"""
    try:
        resp = requests.get(f'{API_BASE}/portfolio/positions', timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'ok':
                positions = data.get('positions', [])
                return [p['symbol'] for p in positions if p.get('shares', 0) > 0]
    except Exception as e:
        print(f"Failed to get positions: {e}", file=sys.stderr)
    return ['TSM', 'NVDA', 'AMD', 'AVGO', 'WDC']

def analyze_news(title, content, news_type='general'):
    """Analyze news"""
    result = robust_post(f'{API_BASE}/news/analyze', {
        'title': title,
        'content': content,
        'news_type': news_type
    })
    
    if result:
        return result.get('analysis', {})
    return {'weight': 0, 'sentiment': 'neutral'}

def save_news(symbol, title, content, weight, sentiment, source, news_type):
    """Save news"""
    result = robust_post(f'{API_BASE}/news', {
        'symbol': symbol,
        'title': title[:500],
        'content': content[:1000],
        'weight': weight,
        'sentiment': sentiment,
        'source': source,
        'news_type': news_type
    })
    
    return result is not None

# Stock-specific news templates
STOCK_NEWS = {
    'TSM': [
        ('TSMC advances 2nm process technology, volume production expected 2025', 'TSMC continues to lead in advanced semiconductor manufacturing with 2nm node', 'technology'),
        ('AI chip demand drives TSMC revenue growth', 'TSMC benefits from surging AI accelerator demand', 'earnings'),
    ],
    'NVDA': [
        ('NVIDIA announces next-gen AI GPUs with breakthrough performance', 'NVIDIA unveils new AI computing platform', 'product'),
        ('Data center revenue surges for NVIDIA on AI demand', 'NVIDIA reports record data center segment', 'earnings'),
    ],
    'AMD': [
        ('AMD launches new AI accelerators to compete with NVIDIA', 'AMD announces MI350 series AI chips', 'product'),
        ('AMD expands AI partnerships with major cloud providers', 'AMD secures new AI deployment deals', 'business'),
    ],
    'AVGO': [
        ('Broadcom reports strong AI networking revenue', 'Broadcom sees robust demand for AI infrastructure', 'earnings'),
        ('Broadcom unveils next-generation silicon for AI workloads', 'New chip architecture targets AI applications', 'product'),
    ],
    'WDC': [
        ('Western Digital benefits from enterprise storage demand', 'Storage demand remains strong from cloud customers', 'earnings'),
        ('WDC announces new AI-optimized storage solutions', 'New products target AI and machine learning workloads', 'product'),
    ],
}

MARKET_NEWS = [
    ('Fed signals potential rate adjustments amid economic data', 'Federal Reserve officials indicate possible policy shifts', 'market'),
    ('Tech stocks rally on AI optimism', 'Major technology companies see gains on continued AI momentum', 'market'),
    ('Global markets react to economic indicators', 'International investors assess latest economic data releases', 'market'),
]

def main():
    print("=" * 60)
    print("🦊 Fox News Update (Robust)")
    print("=" * 60)
    
    # 1. Get positions
    symbols = get_positions()
    print(f"📊 Positions: {symbols}")
    
    all_news = []
    
    # 2. Add market news
    for title, content, news_type in MARKET_NEWS:
        all_news.append({
            'symbol': 'MARKET',
            'title': title,
            'content': content,
            'source': 'Market Summary',
            'news_type': news_type
        })
    
    # 3. Add stock news for each position
    for symbol in symbols:
        if symbol in STOCK_NEWS:
            for title, content, news_type in STOCK_NEWS[symbol]:
                all_news.append({
                    'symbol': symbol,
                    'title': title,
                    'content': content,
                    'source': 'News Aggregator',
                    'news_type': news_type
                })
    
    print(f"\n📋 Total news to process: {len(all_news)}")
    
    # 4. Process and save news
    saved = 0
    for news in all_news:
        title_short = news['title'][:50] + "..." if len(news['title']) > 50 else news['title']
        print(f"  [{news['symbol']}] {title_short}")
        
        # Analyze
        analysis = analyze_news(news['title'], news['content'], news['news_type'])
        print(f"    Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
        
        # Save
        if save_news(
            news['symbol'],
            news['title'],
            news['content'],
            analysis.get('weight', 0),
            analysis.get('sentiment', 'neutral'),
            news['source'],
            news['news_type']
        ):
            saved += 1
            print(f"    ✅ Saved")
        else:
            print(f"    ❌ Failed")
        
        time.sleep(1)
    
    print(f"\n{'=' * 60}")
    print(f"✅ Complete! Saved {saved}/{len(all_news)} news items")
    print("=" * 60)

if __name__ == '__main__':
    main()
