#!/usr/bin/env python3
"""Fox News Update - Simple version"""

import requests
import json
import time
import sys

API_BASE = 'http://localhost:8080/api/v1'

def get_positions():
    """Get portfolio positions"""
    try:
        resp = requests.get(f'{API_BASE}/portfolio/positions', timeout=10)
        data = resp.json()
        if data.get('status') == 'ok':
            positions = data.get('positions', [])
            return [p['symbol'] for p in positions if p.get('shares', 0) > 0]
    except Exception as e:
        print(f"Failed to get positions: {e}")
    return []

def analyze_news(title, content, news_type='general'):
    """Analyze news sentiment"""
    try:
        resp = requests.post(f'{API_BASE}/news/analyze', json={
            'title': title,
            'content': content,
            'news_type': news_type
        }, timeout=15)
        result = resp.json()
        if result.get('status') == 'ok':
            return result.get('analysis', {})
    except Exception as e:
        print(f"Analysis error: {e}")
    return {'weight': 0, 'sentiment': 'neutral'}

def save_news(symbol, title, content, source, news_type, analysis):
    """Save news to database"""
    try:
        data = {
            'symbol': symbol,
            'title': title[:200],
            'content': content[:500],
            'weight': analysis.get('weight', 0),
            'sentiment': analysis.get('sentiment', 'neutral'),
            'source': source,
            'news_type': news_type
        }
        resp = requests.post(f'{API_BASE}/news', json=data, timeout=10)
        result = resp.json()
        return result.get('status') == 'ok'
    except Exception as e:
        print(f"Save error: {e}")
        return False

def main():
    print("=" * 50)
    print("Fox News Update")
    print("=" * 50)
    
    # 1. Get positions
    symbols = get_positions()
    print(f"Positions: {symbols}")
    
    # 2. Sample news for each symbol (in production, fetch from real sources)
    sample_news = [
        {
            'symbol': 'MARKET',
            'title': 'Fed signals potential rate adjustments amid economic uncertainty',
            'content': 'Federal Reserve officials indicated they are monitoring economic indicators closely',
            'source': 'Reuters',
            'news_type': 'market'
        },
        {
            'symbol': 'TSM',
            'title': 'Taiwan Semiconductor announces new advanced packaging facility',
            'content': 'TSMC expands its advanced packaging capabilities to meet growing AI chip demand',
            'source': 'Bloomberg',
            'news_type': 'earnings'
        },
        {
            'symbol': 'NVDA',
            'title': 'NVIDIA AI chip demand exceeds expectations in data center segment',
            'content': 'NVIDIA reports unprecedented demand for its AI accelerators',
            'source': 'CNBC',
            'news_type': 'earnings'
        },
        {
            'symbol': 'AMD',
            'title': 'AMD launches new AI accelerators to compete with NVIDIA',
            'content': 'AMD announces new MI300 series AI chips',
            'source': 'TechCrunch',
            'news_type': 'product'
        },
        {
            'symbol': 'AVGO',
            'title': 'Broadcom strengthens AI networking portfolio with new switches',
            'content': 'Broadcom announces next-gen silicon for AI infrastructure',
            'source': 'Reuters',
            'news_type': 'product'
        },
        {
            'symbol': 'WDC',
            'title': 'Western Digital sees strong storage demand from cloud customers',
            'content': 'WDC reports robust demand for enterprise storage solutions',
            'source': 'Bloomberg',
            'news_type': 'earnings'
        }
    ]
    
    # 3. Process and save news
    saved = 0
    for news in sample_news:
        print(f"\nProcessing: {news['symbol']} - {news['title'][:40]}...")
        
        # Analyze
        analysis = analyze_news(news['title'], news['content'], news['news_type'])
        print(f"  -> Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
        
        # Save
        if save_news(news['symbol'], news['title'], news['content'], 
                     news['source'], news['news_type'], analysis):
            saved += 1
            print(f"  -> Saved!")
        
        time.sleep(0.5)
    
    print(f"\n{'='*50}")
    print(f"Complete! Saved {saved}/{len(sample_news)} news items")
    print("=" * 50)

if __name__ == '__main__':
    main()
