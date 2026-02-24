#!/usr/bin/env python3
"""
補齊缺失的 1h K線數據
針對 TSLA、TSM 等股票，從 2/19 之後缺失的 1h 數據
"""

import futu as ft
import pymysql
import sys
import os
from datetime import datetime, timezone
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config.database import PYMYSQL_CONFIG as MYSQL_CONFIG
except ImportError:
    MYSQL_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster',
        'charset': 'utf8mb4'
    }

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

def normalize_timestamp(time_key):
    """確保 timestamp 格式一致"""
    ts = str(time_key)
    if len(ts) == 10:
        ts = ts + ' 00:00:00'
    return ts

def main():
    print("=" * 60)
    print("補齊缺失的 1h K線數據")
    print("=" * 60)
    
    # 連接富途牛牛
    quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    print(f"✅ 富途連接成功")
    
    # 連接 MySQL
    conn = pymysql.connect(**MYSQL_CONFIG)
    cursor = conn.cursor()
    print(f"✅ MySQL 連接成功")
    
    # 獲取所有啟用的股票
    cursor.execute("SELECT symbol FROM stocks WHERE enabled = 1 ORDER BY symbol")
    watchlist = [row[0] for row in cursor.fetchall()]
    print(f"📋 共 {len(watchlist)} 檔股票")
    
    # 訂閱所有股票的 1h K線
    print(f"📡 訂閱 1h K線...")
    for symbol in watchlist:
        quote_ctx.subscribe([symbol], [ft.KLType.K_60M])
    time.sleep(2)
    
    total_updated = 0
    
    for symbol in watchlist:
        print(f"\n處理 {symbol}...", end=" ")
        sys.stdout.flush()
        
        # 獲取 1h K線
        ret, data = quote_ctx.get_cur_kline(symbol, 100, ft.KLType.K_60M)
        
        if ret != ft.RET_OK or data is None or data.empty:
            print(f"❌ 獲取失敗")
            continue
        
        print(f"獲取到 {len(data)} 根K線", end=" ")
        
        now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        count = 0
        
        for _, row in data.iterrows():
            try:
                timestamp = normalize_timestamp(row['time_key'])
                
                cursor.execute('''
                    INSERT INTO kline_cache 
                    (symbol, interval_val, timestamp, open_price, high_price, low_price, close_price, volume, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    open_price = VALUES(open_price),
                    high_price = VALUES(high_price),
                    low_price = VALUES(low_price),
                    close_price = VALUES(close_price),
                    volume = VALUES(volume),
                    updated_at = VALUES(updated_at)
                ''', (
                    symbol, '1h', timestamp,
                    float(row['open']), float(row['high']), 
                    float(row['low']), float(row['close']),
                    int(row['volume']), now_utc
                ))
                count += 1
            except Exception as e:
                print(f"\n  ❌ 寫入錯誤: {e}")
                continue
        
        conn.commit()
        total_updated += count
        print(f"→ 寫入 {count} 筆 ✅")
        
        time.sleep(0.2)
    
    cursor.close()
    conn.close()
    quote_ctx.close()
    
    print("\n" + "=" * 60)
    print(f"✅ 完成！共補齊 {total_updated} 筆 1h K線數據")
    print("=" * 60)

if __name__ == '__main__':
    main()
