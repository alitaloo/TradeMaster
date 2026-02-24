#!/usr/bin/env python3
"""富途即時報價訂閱服務 - 開盤時實時更新"""

import futu as ft
import sqlite3
import os
from datetime import datetime, timezone
import time
import signal
import sys

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'

# 從數據庫讀取配置的股票清單
def get_watchlist():
    import sqlite3
    import os
    
    DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/trademaster.db'
    
    if not os.path.exists(DB_PATH):
        # 預設清單
        return ["US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN"]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 從 stock_ 表獲取股票
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'stock_%' AND name != 'stock_metadata'")
    tables = [row[0].replace('stock_', '') for row in cursor.fetchall()]
    conn.close()
    
    # 轉換為富途格式 (US.XXX)
    return [f"US.{s}" for s in sorted(tables)]

WATCHLIST = get_watchlist()

class MyKlineHandler(ft.CurKlineHandlerBase):
    """處理 K 線實時更新"""
    def on_receive(self, data):
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for row in data:
            code = row['code']
            # 根據 K 線類型確定 interval
            if row.get('kline_type') == ft.KLType.K_5M:
                interval = '5m'
            elif row.get('kline_type') == ft.KLType.K_60M:
                interval = '1h'
            elif row.get('kline_type') == ft.KLType.K_DAY:
                interval = '1d'
            else:
                continue
            
            cursor.execute('''
                INSERT OR REPLACE INTO kline_cache (symbol, interval, timestamp, open, high, low, close, volume, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, interval, row['time_key'], row['open'], row['high'], row['low'], row['close'], row['volume'], now))
        
        conn.commit()
        conn.close()
        
        if data:
            print(f"[KLINE] {data[0]['code']} {data[0]['time_key']}")

class MyQuoteHandler(ft.StockQuoteHandlerBase):
    def on_receive(self, data):
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for row in data:
            code = row['code']
            cursor.execute('''
                INSERT OR REPLACE INTO realtime_quote
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                code,
                row['last_price'],
                row['open_price'],
                row['high_price'],
                row['low_price'],
                row['prev_close_price'],
                row['volume'],
                now
            ))
            
            # 更新 1m K 線
            ts = f"{row['data_date']} {row['data_time']}" if row.get('data_time') else row['data_date']
            cursor.execute('''
                INSERT OR REPLACE INTO kline_cache (symbol, interval, timestamp, open, high, low, close, volume, updated_at)
                VALUES (?, '1m', ?, ?, ?, ?, ?, ?, ?)
            ''', (code, ts, row['open_price'], row['high_price'], row['low_price'], row['last_price'], row['volume'], now))
        
        conn.commit()
        conn.close()
        
        # 打印狀態
        if data:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] " + " | ".join([f"{r['code']}: ${r['last_price']:.2f}" for r in data[:3]]))

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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS realtime_quote (
            symbol TEXT PRIMARY KEY,
            last_price REAL,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            prev_close REAL,
            volume INTEGER,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def main():
    print("=" * 50)
    print("📡 富途即時報價訂閱服務")
    print("=" * 50)
    
    init_db()
    
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
    quote_handler = MyQuoteHandler()
    kline_handler = MyKlineHandler()
    quote_ctx.set_handler(quote_handler)
    quote_ctx.set_handler(kline_handler)
    
    ret, data = quote_ctx.get_user_info()
    if ret != ft.RET_OK:
        print(f"❌ 連接失敗: {data}")
        return
    
    print(f"✅ 連接成功: {data.get('nick_name')}")
    
    # 訂閱報價 + 實時數據 + K線
    ret = quote_ctx.subscribe(WATCHLIST, [ft.SubType.QUOTE, ft.SubType.RT_DATA, ft.SubType.K_5M, ft.SubType.K_60M, ft.SubType.K_DAY])
    print(f"📊 訂閱: {ret}")
    
    if ret[0] != 0:
        print(f"❌ 訂閱失敗")
        return
    
    print("⏰ 等待報價更新... (按 Ctrl+C 停止)")
    print("-" * 50)
    
    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n🛑 停止...")
    finally:
        quote_ctx.close()
        print("👋 已停止")

if __name__ == '__main__':
    main()
