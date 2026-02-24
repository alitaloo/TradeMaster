#!/usr/bin/env python3
"""
獲取所有股票的歷史 K 線數據（富途牛牛版）
"""

import futu as ft
import sqlite3
import os
from datetime import datetime
import time

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'
WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]
KL_TYPE_MAP = {
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
}

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kline_cache (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (symbol, interval, timestamp)
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ 數據庫初始化完成")

def fetch_and_save(symbol, interval, quote_ctx):
    ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
    
    result = quote_ctx.request_history_kline(
        symbol,
        start='2024-01-01',
        end='2025-01-31',
        ktype=ktype
    )
    
    if len(result) == 3:
        ret, data, extra = result
    else:
        return 0
    
    if ret == ft.RET_OK and data is not None and not data.empty:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        count = 0
        
        for _, row in data.iterrows():
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO kline_cache
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol, interval,
                    str(row['time_key']),
                    row['open'], row['high'], row['low'], row['close'],
                    int(row['volume']), now
                ))
                count += 1
            except:
                pass
        
        conn.commit()
        conn.close()
        return count
    else:
        return 0

def main():
    print("=" * 60)
    print("📊 獲取所有股票歷史數據（富途牛牛）")
    print("=" * 60)
    
    init_db()
    
    print("🔗 連接富途牛牛...")
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
    
    total = 0
    for symbol in WATCHLIST:
        for interval in ['1d', '1w']:
            count = fetch_and_save(symbol, interval, quote_ctx)
            if count > 0:
                print(f"  ✅ {symbol} {interval}: {count} 筆")
                total += count
            else:
                print(f"  ❌ {symbol} {interval}: 0 筆")
            
            time.sleep(0.3)  # 避免請求過快
    
    quote_ctx.close()
    
    # 統計
    final_count = sqlite3.connect(DB_PATH).cursor().execute("SELECT COUNT(*) FROM kline_cache").fetchone()[0]
    symbol_count = sqlite3.connect(DB_PATH).cursor().execute("SELECT COUNT(DISTINCT symbol) FROM kline_cache").fetchone()[0]
    
    print("\n" + "=" * 60)
    print(f"✅ 完成！共 {symbol_count} 支股票，{final_count} 筆數據")
    print("=" * 60)

if __name__ == '__main__':
    main()
