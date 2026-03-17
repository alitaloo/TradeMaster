#!/usr/bin/env python3
"""
News RSS Fetcher - 從 RSS 源抓取新聞

功能:
- 從 Yahoo Finance RSS 抓取特定股票的新聞
- 從 Google News RSS 抓取新聞
- 調用 sync_news.py 寫入數據庫
- 支持 symbol 參數

業務規則 (見 docs/news_sync_business_rules.md):
- 去重策略: URL MD5 hash, 24小時窗口 (同 URL 視為同新聞)
- API Error vs 0 News Weight:
  - RSS API 失敗 = degraded/error, 非「無新聞」
  - RSS 返回空 = 真的沒有新聞 (quiet)
- Fox Analysis 應通過 sync_status 欄位判斷同步是否成功

用法:
    python3 fetch_news_rss.py --symbol TSLA
    python3 fetch_news_rss.py --symbol AAPL NVDA MSFT
    python3 fetch_news_rss.py --limit 20
"""

import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# 清除代理設定，避免 localhost API 調用走代理被 502
import os
for _proxy_key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(_proxy_key, None)

import sys
import os
import argparse
import feedparser
import http.client
import json
import hashlib
import time
import urllib.request
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Set

# 添加項目路徑
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.database import get_db_connection

# ── 錯誤統計 (進程內) ──
_sync_stats = {
    'fetch_attempts': 0, 'fetch_errors': 0,
    'analyze_attempts': 0, 'analyze_errors': 0,
    'create_attempts': 0, 'create_errors': 0,
}


def _retry(fn, max_retries=3, backoff_base=1.0, label=""):
    """指數退避重試包裝器"""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"[RETRY] {label} attempt {attempt}/{max_retries} failed: {e}  (wait {wait:.1f}s)")
                time.sleep(wait)
    print(f"[ERROR] {label} all {max_retries} attempts failed: {last_exc}")
    raise last_exc


# RSS 源配置
RSS_SOURCES = {
    "yahoo": "https://finance.yahoo.com/rss/quote?q={symbol}",
    "google": "https://news.google.com/rss/search?q={symbol}+stock"
}

# API 服務地址
API_BASE = os.environ.get('API_BASE', 'http://localhost:8080')


class NewsDeduplicator:
    """新聞去重"""
    
    def __init__(self):
        self.seen_hashes: Set[str] = set()
        self._load_recent_hashes()
    
    def _load_recent_hashes(self):
        """從數據庫載入最近的新聞哈希"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # 載入最近 7 天的新聞 URL 哈希 (去重視窗 7d)
                cursor.execute("""
                    SELECT url FROM news 
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """)
                rows = cursor.fetchall()
                for row in rows:
                    if row[0]:
                        self.seen_hashes.add(self._hash_url(row[0]))
        except Exception as e:
            print(f"[WARN] 無法載入歷史記錄: {e}")
    
    def _hash_url(self, url: str) -> str:
        """生成 URL 哈希"""
        return hashlib.md5(url.encode()).hexdigest()
    
    def is_duplicate(self, url: str) -> bool:
        """檢查是否重複"""
        if not url:
            return True
        return self._hash_url(url) in self.seen_hashes
    
    def add(self, url: str):
        """添加已處理 URL"""
        if url:
            self.seen_hashes.add(self._hash_url(url))


def fetch_yahoo_rss(symbol: str, limit: int = 10) -> List[Dict]:
    """從 Yahoo Finance RSS 抓取新聞 (含 retry/backoff)"""
    url = RSS_SOURCES["yahoo"].format(symbol=symbol.upper())
    _sync_stats['fetch_attempts'] += 1
    
    try:
        def _do_fetch():
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
            resp.raise_for_status()
            return resp.text

        import re
        text = _retry(_do_fetch, max_retries=3, backoff_base=1.0, label=f"Yahoo-{symbol}")
        feed = feedparser.parse(text)
        articles = []
        
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            content = entry.get("summary", "") or entry.get("description", "")
            content = re.sub(r'<[^>]+>', '', content)
            content = ' '.join(content.split())
            
            if title and link:
                articles.append({
                    "symbol": symbol.upper(),
                    "title": title,
                    "content": content[:500] if content else "",
                    "url": link,
                    "source": "Yahoo Finance",
                    "published": entry.get("published", "")
                })
        
        return articles
        
    except Exception as e:
        _sync_stats['fetch_errors'] += 1
        print(f"[ERROR] Yahoo RSS fetch failed for {symbol}: {e}")
        return []


def fetch_google_rss(symbol: str, limit: int = 10) -> List[Dict]:
    """從 Google News RSS 抓取新聞 (含 retry/backoff)"""
    url = RSS_SOURCES["google"].format(symbol=symbol.upper())
    _sync_stats['fetch_attempts'] += 1
    
    try:
        def _do_fetch():
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
            resp.raise_for_status()
            return resp.text

        import re
        text = _retry(_do_fetch, max_retries=3, backoff_base=1.0, label=f"Google-{symbol}")
        feed = feedparser.parse(text)
        articles = []
        
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            
            if hasattr(entry, 'source') and entry.source:
                source_name = entry.source.get('title', 'Google News')
            else:
                source_name = "Google News"
            
            content = entry.get("summary", "")
            content = re.sub(r'<[^>]+>', '', content)
            content = ' '.join(content.split())
            
            if title and link:
                articles.append({
                    "symbol": symbol.upper(),
                    "title": title,
                    "content": content[:500] if content else "",
                    "url": link,
                    "source": source_name,
                    "published": entry.get("published", "")
                })
        
        return articles
        
    except Exception as e:
        _sync_stats['fetch_errors'] += 1
        print(f"[ERROR] Google RSS fetch failed for {symbol}: {e}")
        return []


def analyze_news(article: Dict) -> Dict:
    """調用 API 分析新聞 (含 retry/backoff)"""
    _sync_stats['analyze_attempts'] += 1

    def _do_analyze():
        resp = requests.post(
            f"{API_BASE}/api/v1/news/analyze",
            json={
                "title": article["title"],
                "content": article.get("content", ""),
                "news_type": "general"
            },
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("analysis", {"weight": 0, "sentiment": "neutral"})

    try:
        return _retry(_do_analyze, max_retries=2, backoff_base=0.5, label="analyze")
    except Exception as e:
        _sync_stats['analyze_errors'] += 1
        print(f"[ERROR] Analyze news failed: {e}")
        return {"weight": 0, "sentiment": "neutral"}


def create_news(article: Dict, analysis: Dict) -> int:
    """創建新聞記錄 (含 retry/backoff)"""
    _sync_stats['create_attempts'] += 1

    def _do_create():
        resp = requests.post(
            f"{API_BASE}/api/v1/news",
            json={
                "symbol": article["symbol"],
                "title": article["title"],
                "content": article.get("content", ""),
                "weight": analysis.get("weight", 0),
                "sentiment": analysis.get("sentiment", "neutral"),
                "source": article.get("source", "Unknown"),
                "url": article.get("url", ""),
                "news_type": "general"
            },
            timeout=10
        )
        resp.raise_for_status()
        return resp.json().get("news_id", 0)

    try:
        return _retry(_do_create, max_retries=2, backoff_base=0.5, label="create_news")
    except Exception as e:
        _sync_stats['create_errors'] += 1
        print(f"[ERROR] Create news failed: {e}")
        return 0


def sync_news_for_symbol(symbol: str, limit: int = 10, dry_run: bool = False) -> int:
    """為指定股票同步新聞"""
    print(f"\n📰 Fetching news for {symbol}...")
    
    deduplicator = NewsDeduplicator()
    all_articles = []
    
    # 從 Yahoo RSS 抓取
    print(f"  → Yahoo RSS...")
    yahoo_articles = fetch_yahoo_rss(symbol, limit)
    all_articles.extend(yahoo_articles)
    print(f"    Found {len(yahoo_articles)} articles")
    
    # 從 Google RSS 抓取
    print(f"  → Google RSS...")
    google_articles = fetch_google_rss(symbol, limit)
    all_articles.extend(google_articles)
    print(f"    Found {len(google_articles)} articles")
    
    # 去重並寫入數據庫
    synced_count = 0
    for article in all_articles:
        # 去重檢查
        if deduplicator.is_duplicate(article.get("url", "")):
            continue
        
        # 分析新聞
        analysis = analyze_news(article)
        
        if dry_run:
            print(f"  [DRY-RUN] Would create: {article['title'][:50]}...")
            print(f"    Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
        else:
            news_id = create_news(article, analysis)
            if news_id > 0:
                synced_count += 1
                deduplicator.add(article.get("url", ""))
                print(f"    ✅ Created news {news_id}: {article['title'][:40]}...")
    
    print(f"  Total synced: {synced_count}/{len(all_articles)}")
    return synced_count


def main():
    parser = argparse.ArgumentParser(description="News RSS Fetcher")
    parser.add_argument("--symbol", "-s", nargs="+", help="Stock symbol(s)")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Max articles per source")
    parser.add_argument("--dry-run", action="store_true", help="Dry run without writing to DB")
    
    args = parser.parse_args()
    
    symbols = args.symbol
    if not symbols:
        print("Error: --symbol is required")
        sys.exit(1)
    
    print(f"🚀 Starting news fetch for: {', '.join(symbols)}")
    print(f"   Limit: {args.limit} per source")
    print(f"   Dry run: {args.dry_run}")
    
    total_synced = 0
    for symbol in symbols:
        count = sync_news_for_symbol(symbol, args.limit, args.dry_run)
        total_synced += count
    
    print(f"\n✅ Total news synced: {total_synced}")
    print(f"📊 Stats: fetch={_sync_stats['fetch_attempts']}(err={_sync_stats['fetch_errors']}), "
          f"analyze={_sync_stats['analyze_attempts']}(err={_sync_stats['analyze_errors']}), "
          f"create={_sync_stats['create_attempts']}(err={_sync_stats['create_errors']})")


if __name__ == "__main__":
    main()
