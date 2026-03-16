#!/usr/bin/env python3
"""
News Sync - 新聞同步工具

功能:
- 將外部新聞同步到 TM 數據庫
- 調用 /api/v1/news/analyze 計算權重
- 去重檢查 (URL + title)

用法:
    python3 sync_news.py --symbol TSLA --title "Tesla launches new product" --content "..."
    python3 sync_news.py --batch file.json
"""

import sys
import os
import argparse
import json
import hashlib
import time
import requests
from datetime import datetime
from typing import List, Dict, Optional

# 添加項目路徑
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.database import get_db_connection

# API 服務地址
API_BASE = os.environ.get('API_BASE', 'http://localhost:8080')


def _retry(fn, max_retries=2, backoff_base=0.5, label=""):
    """指數退避重試"""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                wait = backoff_base * (2 ** (attempt - 1))
                print(f"[RETRY] {label} attempt {attempt}/{max_retries}: {e} (wait {wait:.1f}s)")
                time.sleep(wait)
    raise last_exc


class NewsSync:
    """新聞同步器"""
    
    def __init__(self):
        self.seen_hashes = set()
        self._load_history()
    
    def _load_history(self):
        """載入歷史記錄用於去重"""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # 載入最近 7 天的新聞 (去重視窗 7d)
                cursor.execute("""
                    SELECT url, title FROM news 
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """)
                rows = cursor.fetchall()
                for row in rows:
                    self.seen_hashes.add(self._make_hash(row[0], row[1]))
        except Exception as e:
            print(f"[WARN] 無法載入歷史記錄: {e}")
    
    def _make_hash(self, url: str, title: str) -> str:
        """生成去重哈希"""
        text = f"{url}|{title}"
        return hashlib.md5(text.encode()).hexdigest()
    
    def is_duplicate(self, url: str, title: str) -> bool:
        """檢查是否重複"""
        return self._make_hash(url, title) in self.seen_hashes
    
    def add_record(self, url: str, title: str):
        """添加已處理的記錄"""
        self.seen_hashes.add(self._make_hash(url, title))
    
    def analyze_news(self, title: str, content: str = "", news_type: str = "general") -> Dict:
        """調用 API 分析新聞 (含 retry)"""
        def _do():
            resp = requests.post(
                f"{API_BASE}/api/v1/news/analyze",
                json={
                    "title": title,
                    "content": content[:1000] if content else "",
                    "news_type": news_type
                },
                timeout=10
            )
            resp.raise_for_status()
            return resp.json().get("analysis", {"weight": 0, "sentiment": "neutral"})

        try:
            return _retry(_do, max_retries=2, backoff_base=0.5, label="analyze")
        except Exception as e:
            print(f"[ERROR] Analyze failed after retries: {e}")
            return {"weight": 0, "sentiment": "neutral"}
    
    def create_news(self, article: Dict, analysis: Dict) -> int:
        """創建新聞記錄 (含 retry)"""
        def _do():
            resp = requests.post(
                f"{API_BASE}/api/v1/news",
                json={
                    "symbol": article.get("symbol", "").upper(),
                    "title": article.get("title", ""),
                    "content": article.get("content", "")[:2000] if article.get("content") else "",
                    "weight": analysis.get("weight", 0),
                    "sentiment": analysis.get("sentiment", "neutral"),
                    "source": article.get("source", "Unknown"),
                    "url": article.get("url", ""),
                    "news_type": article.get("news_type", "general")
                },
                timeout=10
            )
            resp.raise_for_status()
            return resp.json().get("news_id", 0)

        try:
            return _retry(_do, max_retries=2, backoff_base=0.5, label="create_news")
        except Exception as e:
            print(f"[ERROR] Create news failed after retries: {e}")
            return 0
    
    def sync_single(self, article: Dict, dry_run: bool = False) -> int:
        """同步單條新聞"""
        # 去重檢查
        if self.is_duplicate(article.get("url", ""), article.get("title", "")):
            print(f"  ⏭️  Skip (duplicate): {article.get('title', '')[:40]}...")
            return 0
        
        # 分析新聞
        analysis = self.analyze_news(
            article.get("title", ""),
            article.get("content", ""),
            article.get("news_type", "general")
        )
        
        if dry_run:
            print(f"  [DRY-RUN] {article.get('title', '')[:40]}...")
            print(f"    → Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
            return 0
        
        # 寫入數據庫
        news_id = self.create_news(article, analysis)
        
        if news_id > 0:
            self.add_record(article.get("url", ""), article.get("title", ""))
            print(f"  ✅ Created {news_id}: {article.get('title', '')[:40]}...")
            print(f"    → Weight: {analysis.get('weight')}, Sentiment: {analysis.get('sentiment')}")
            return 1
        else:
            return 0
    
    def sync_batch(self, articles: List[Dict], dry_run: bool = False) -> int:
        """批量同步新聞"""
        synced = 0
        for article in articles:
            synced += self.sync_single(article, dry_run)
        return synced


def main():
    parser = argparse.ArgumentParser(description="News Sync Tool")
    
    # 單條新聞模式
    parser.add_argument("--symbol", "-s", help="Stock symbol")
    parser.add_argument("--title", "-t", help="News title")
    parser.add_argument("--content", "-c", help="News content")
    parser.add_argument("--url", "-u", help="News URL")
    parser.add_argument("--source", help="News source")
    parser.add_argument("--news-type", default="general", help="News type")
    
    # 批量模式
    parser.add_argument("--batch", "-b", help="JSON file with news array")
    
    # 選項
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    
    args = parser.parse_args()
    
    sync = NewsSync()
    
    if args.batch:
        # 批量模式
        try:
            with open(args.batch, 'r') as f:
                articles = json.load(f)
            
            if not isinstance(articles, list):
                print("Error: JSON file must contain an array of articles")
                sys.exit(1)
            
            print(f"📦 Syncing {len(articles)} articles from {args.batch}...")
            synced = sync.sync_batch(articles, args.dry_run)
            print(f"✅ Total synced: {synced}")
            
        except FileNotFoundError:
            print(f"Error: File not found: {args.batch}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON: {e}")
            sys.exit(1)
    
    elif args.symbol and args.title:
        # 單條新聞模式
        article = {
            "symbol": args.symbol,
            "title": args.title,
            "content": args.content or "",
            "url": args.url or "",
            "source": args.source or "Manual",
            "news_type": args.news_type
        }
        
        print(f"📰 Syncing news: {args.title[:50]}...")
        synced = sync.sync_single(article, args.dry_run)
        print(f"✅ Synced: {synced}")
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
