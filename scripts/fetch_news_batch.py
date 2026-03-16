#!/usr/bin/env python3
"""
News Batch Fetcher - 批量為持倉+watchlist抓取新聞

功能:
- 自動獲取持倉列表
- 自動獲取 watchlist
- 對每個標的調用 RSS 抓取
- 調用 sync_news 寫入數據庫

用法:
    python3 fetch_news_batch.py
    python3 fetch_news_batch.py --dry-run
    python3 fetch_news_batch.py --limit 20
"""

import sys
import os
import argparse
import requests
from datetime import datetime
from typing import List, Set

# 添加項目路徑
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config.database import get_db_connection

# API 服務地址
API_BASE = os.environ.get('API_BASE', 'http://localhost:8080')

# 默認 watchlist (當無法從 API 獲取時使用)
DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSM", "AMZN", "META", "UBER", 
    "MU", "AMD", "ORCL", "GOOGL", "GOOG", "NFLX", "ADBE", 
    "CRM", "QCOM", "TXN", "AVGO", "COIN", "MSTR"
]


def get_positions() -> List[str]:
    """獲取持倉列表"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/positions", timeout=10)
        if response.status_code == 200:
            data = response.json()
            positions = data.get("positions", [])
            symbols = [p.get("symbol", "").replace("US.", "").replace("HK.", "") 
                      for p in positions if p.get("symbol")]
            print(f"📊 Found {len(symbols)} positions: {symbols}")
            return symbols
        else:
            print(f"[WARN] Failed to get positions: {response.status_code}")
            return []
    except Exception as e:
        print(f"[ERROR] Get positions failed: {e}")
        return []


def get_watchlist() -> List[str]:
    """獲取 watchlist"""
    try:
        # 嘗試從 stocks 表獲取 (這是 watchlist)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stocks ORDER BY symbol")
            rows = cursor.fetchall()
            
            if rows:
                symbols = [row[0].replace("US.", "").replace("HK.", "").replace("CN.", "") 
                          for row in rows if row[0]]
                print(f"📋 Found {len(symbols)} watchlist from DB (stocks table)")
                return symbols
    except Exception as e:
        print(f"[WARN] Cannot get watchlist from DB: {e}")
    
    # 使用默認 watchlist
    print(f"📋 Using default watchlist ({len(DEFAULT_WATCHLIST)} symbols)")
    return DEFAULT_WATCHLIST


def get_all_symbols() -> List[str]:
    """獲取所有需要抓取新聞的標的"""
    positions = get_positions()
    watchlist = get_watchlist()
    
    # 合併並去重
    all_symbols = list(set(positions + watchlist))
    
    # 清理符號 (去除市場前綴)
    cleaned = []
    for s in all_symbols:
        # 去除 US., HK., 等前綴
        s = s.replace("US.", "").replace("HK.", "").replace("CN.", "")
        if s:
            cleaned.append(s.upper())
    
    cleaned = list(set(cleaned))
    print(f"\n🎯 Total unique symbols to fetch: {len(cleaned)}")
    return cleaned


def fetch_news_for_symbols(symbols: List[str], limit: int = 10, dry_run: bool = False) -> int:
    """為多個標的抓取新聞"""
    total_synced = 0
    
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] 📰 Fetching for {symbol}...")
        
        try:
            # 調用 fetch_news_rss.py 腳本
            import subprocess
            
            cmd = [
                sys.executable,
                os.path.join(PROJECT_ROOT, "scripts", "fetch_news_rss.py"),
                "--symbol", symbol,
                "--limit", str(limit)
            ]
            
            if dry_run:
                cmd.append("--dry-run")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                # 計算同步數量 - 查找 "Total news synced:" 行
                for line in result.stdout.split('\n'):
                    if 'Total news synced:' in line:
                        # 格式: "✅ Total news synced: 5"
                        count_str = line.split(':')[-1].strip()
                        try:
                            count = int(count_str)
                            total_synced += count
                        except ValueError:
                            # Try parsing "X/Y" format
                            if '/' in count_str:
                                count = int(count_str.split('/')[0])
                                total_synced += count
                        break
            else:
                print(f"  [ERROR] {result.stderr}")
                
        except subprocess.TimeoutExpired:
            print(f"  [ERROR] Timeout for {symbol}")
        except Exception as e:
            print(f"  [ERROR] Failed: {e}")
    
    return total_synced


def main():
    parser = argparse.ArgumentParser(description="News Batch Fetcher")
    parser.add_argument("--limit", "-l", type=int, default=10, 
                       help="Max articles per symbol per source")
    parser.add_argument("--dry-run", action="store_true", help="Dry run")
    parser.add_argument("--symbols", nargs="+", help="Override symbols (skip auto-detection)")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 News Batch Fetcher - 持倉+Watchlist 新聞抓取")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Limit: {args.limit} articles per symbol")
    print(f"   Dry run: {args.dry_run}")
    print("=" * 60)
    
    # 獲取標的列表
    if args.symbols:
        symbols = [s.upper().replace("US.", "").replace("HK.", "") for s in args.symbols]
    else:
        symbols = get_all_symbols()
    
    if not symbols:
        print("❌ No symbols to fetch")
        sys.exit(1)
    
    print(f"\n📋 Symbols: {', '.join(symbols[:10])}{'...' if len(symbols) > 10 else ''}")
    
    # 抓取新聞
    total = fetch_news_for_symbols(symbols, args.limit, args.dry_run)
    
    print("\n" + "=" * 60)
    print(f"✅ Batch fetch complete! Total synced: {total}")
    print("=" * 60)


if __name__ == "__main__":
    main()
