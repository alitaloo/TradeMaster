#!/usr/bin/env python3
"""
測試富途牛牛獲取單個股票歷史數據
"""

import futu as ft
import sqlite3
import os
from datetime import datetime

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'
KL_TYPE_MAP = {
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
    '1M': ft.KLType.K_MON,
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
    print("=" * 60)
    print("📊 測試富途牛牛獲取數據")
    print("=" * 60)
    
    init_db()
    
    print("🔗 連接富途牛牛...")
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
    
    # 測試一個股票
    symbol = "US.AAPL"
    interval = "1d"
    
    print(f"\n📈 獲取 {symbol} {interval}...")
    
    ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
    result = quote_ctx.request_history_kline(
        symbol,
        start='2025-01-01',
        end='2025-01-10',
        ktype=ktype
    )
    
    print(f"返回長度: {len(result)}")
    ret, data, extra = result
    
    if ret == ft.RET_OK:
        print(f"✅ 成功！獲取 {len(data)} 筆數據")
        print(f"欄位: {data.columns.tolist()}")
        print(f"前3筆:")
        print(data.head(3))
        
        # 存入數據庫
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
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
            except:
                pass
        
        conn.commit()
        conn.close()
        print(f"\n✅ 已存入數據庫")
        
    else:
        print(f"❌ 失敗: {data}")
    
    quote_ctx.close()
    
    # 檢查數據庫
    count = sqlite3.connect(DB_PATH).cursor().execute("SELECT COUNT(*) FROM kline_cache").fetchone()[0]
    print(f"\n📊 數據庫總筆數: {count}")

if __name__ == '__main__':
    main()
