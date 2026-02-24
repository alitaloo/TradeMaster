#!/usr/bin/env python3
"""快速 K 線更新 - 只獲取最近數據"""

import futu as ft
import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'

WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

KL_TYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY,
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

def main():
    now = datetime.now()
    print(f"\n⏰ [{now.strftime('%H:%M:%S')}] 快速更新...")
    
    init_db()
    
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
    ret, data = quote_ctx.get_user_info()
    
    if ret != ft.RET_OK:
        print(f"❌ 連接失敗: {data}")
        quote_ctx.close()
        return
    
    print(f"✅ 連接成功")
    
    # 獲取最近 5 天有數據的範圍
    start = '2026-02-09'
    
    total = 0
    for symbol in WATCHLIST:
        for interval, ktype in KL_TYPE_MAP.items():
            result = quote_ctx.request_history_kline(
                symbol, start=start, end=now.strftime('%Y-%m-%d'), ktype=ktype
            )
            
            if len(result) >= 2:
                ret, data, _ = result
                if ret == ft.RET_OK and data is not None and not data.empty:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    now_utc = datetime.now(timezone.utc).isoformat()
                    
                    for _, row in data.iterrows():
                        cursor.execute('''
                            INSERT OR REPLACE INTO kline_cache
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (symbol, interval, str(row['time_key']),
                              row['open'], row['high'], row['low'], row['close'],
                              int(row['volume']), now_utc))
                        total += 1
                    
                    conn.commit()
                    conn.close()
    
    quote_ctx.close()
    print(f"✅ 完成！新增 {total} 筆")

if __name__ == '__main__':
    main()
