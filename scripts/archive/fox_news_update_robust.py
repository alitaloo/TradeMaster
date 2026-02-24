#!/usr/bin/env python3
"""Fox News Update - Robust version with better error handling"""

import requests
import json
import time
import xml.etree.ElementTree as ET
import re
import sys

API_BASE = 'http://localhost:8080/api/v1'
MAX_RETRIES = 3
RETRY_DELAY = 3

def robust_request(method, url, **kwargs):
    """Make a request with retries and better error handling"""
    kwargs.setdefault('timeout', 15)
    
    for attempt in range(MAX_RETRIES):
        try:
            if method.upper() == 'GET':
                resp = requests.get(url, **kwargs)
            else:
                resp = requests.post(url, **kwargs)
            
            # Check for empty response
            if not resp.text or resp.text.strip() == '':
                print(f"  Empty response, attempt {attempt + 1}/{MAX_RETRIES}", file=sys.stderr)
                time.sleep(RETRY_DELAY)
                continue
                
            resp.raise_for_status()
            return resp.json()
            
        except requests.exceptions.RequestException as e:
            print(f"  Request error (attempt {attempt + 1}/{MAX_RETRIES}): {e}", file=sys.stderr)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                raise

def get_positions():
    """Get portfolio positions"""
    try:
        data = robust_request('GET', f'{API_BASE}/portfolio/positions')
        if data and data.get('status') == 'ok':
            positions = data.get('positions', [])
            return [p['symbol'] for p in positions if p.get('shares', 0) > 0]
    except Exception as e:
        print(f"Failed to get positions: {e}", file=sys.stderr)
    return ['TSM', 'NVDA', 'AMD', 'AVGO', 'WDC']  # Fallback to hardcoded

def clean_html(text):
    """Clean HTML tags"""
    if not text:
        return ''
    return re.sub('<[^<]+?>', '', text)[:500]

def fetch_rss_news(feeds, limit=10):
    """Fetch news from RSS feeds"""
    news_list = []
    for feed_url in feeds:
        try:
            resp = requests.get(feed_url, timeout=15)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.text)
            items = root.findall('.//item')
            for item in items[:limit]:
                title = item.find('title').text if item.find('title') is not None else ''
                desc_elem = item.find('description')
                desc = clean_html(desc_elem.text) if desc_elem is not None and desc_elem.text else ''
                if title:
                    news_list.append({
                        'symbol': 'MARKET',
                        'title': title,
                        'content': desc,
                        'source': 'MarketWatch',
                        'news_type': 'market'
                    })
        except Exception as e:
            print(f"RSS feed error: {e}", file=sys.stderr)
    return news_list

def analyze_news(news):
    """Analyze news sentiment and weight"""
    try:
        result = robust_request('POST', f'{API_BASE}/news/analyze', json={
            'title': news['title'],
            'content': news['content'],
            'news_type': news.get('news_type', 'general')
        })
        if result and result.get('status') == 'ok':
            return result.get('analysis', {})
    except Exception as e:
        print(f"Analysis error: {e}", file=sys.stderr)
    return {'weight': 0, 'sentiment': 'neutral'}

def save_news(news, analysis):
    """Save news to database"""
    try:
        data = {
            'symbol': news['symbol'],
            'title': news['title'],
            'content': news['content'],
            'weight': analysis.get('weight', 0),
            'sentiment': analysis.get('sentiment', 'neutral'),
            'source': news.get('source', ''),
            'url': news.get('url', ''),
            'news_type': news.get('news_type', 'general')
        }
        result = robust_request('POST', f'{API_BASE}/news', json=data)
        return result and result.get('status') == 'ok'
    except Exception as e:
        print(f"Save error: {e}", file=sys.stderr)
        return False

def main():
    print("=" * 60)
    print("🦊 Fox News Update (Robust)")
    print("=" * 60)
    
    # 1. Get positions
    symbols = get_positions()
    print(f"📊 Positions: {symbols}")
    
    # 2. Fetch market news
    feeds = ['https://feeds.content.dowjones.io/public/rss/mw_topstories']
    all_news = fetch_rss_news(feeds, limit=10)
    print(f"📰 Market news: {len(all_news)}")
    
    # 3. Process news
    saved = 0
    for news in all_news:
        print(f"  Processing: {news['title'][:50]}...")
        
        # Analyze
        analysis = analyze_news(news)
        print(f"    Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
        
        # Save
        if save_news(news, analysis):
            saved += 1
            print(f"    ✅ Saved")
        
        time.sleep(1)
    
    print(f"\n✅ Complete! Saved {saved}/{len(all_news)} news items")
    print("=" * 60)

if __name__ == '__main__':
    main()
