#!/usr/bin/env python3
"""分頁獲取 AAPL 完整歷史數據"""

import futu as ft
import sqlite3
from datetime import datetime

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'

KL_TYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY,
}

def main():
    print("🔗 連接富途牛牛...")
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
    
    ret, data = quote_ctx.get_user_info()
    if ret != 0:
        print(f"❌ 連接失敗: {data}")
        return
    
    print(f"✅ 連接成功: {data.get('nick_name', 'Unknown')}")
    
    symbol = 'US.AAPL'
    now = datetime.now().isoformat()
    
    for interval in ['5m', '1h', '1d']:
        print(f"\n📊 {interval}...")
        ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
        
        page = 1
        total_count = 0
        
        while page <= 10:  # 最多 10 頁
            # 每次請求 500 筆
            result = quote_ctx.request_history_kline(
                symbol,
                start='2024-01-01',
                end='2025-12-31',
                ktype=ktype,
                autype=ft.AuType.QFQ,
                max_count=500
            )
            
            if len(result) == 3:
                ret_code, resp_data, page_req_key = result
            else:
                break
            
            if ret_code != 0:
                print(f"  ❌ 錯誤: {resp_data}")
                break
            
            if resp_data is None or resp_data.empty:
                print(f"  ✅ 完成，總計 {total_count} 筆")
                break
            
            # 插入數據庫
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            count = 0
            
            for _, row in resp_data.iterrows():
                try:
                    timestamp = str(row['time_key'])
                    cursor.execute('''
                        INSERT OR REPLACE INTO kline_cache
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        symbol, interval,
                        timestamp,
                        float(row['open']), float(row['high']), 
                        float(row['low']), float(row['close']),
                        int(row['volume']), now
                    ))
                    count += 1
                except:
                    pass
            
            conn.commit()
            conn.close()
            total_count += count
            print(f"  📄 Page {page}: {count} 筆")
            
            if not page_req_key:
                break
            
            page += 1
            time.sleep(0.5)
        
        print(f"  ✅ {interval} 總計: {total_count} 筆")
        time.sleep(1)
    
    quote_ctx.close()
    
    # 統計
    print(f"\n📊 數據庫統計:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for interval in ['5m', '1h', '1d']:
        count = cursor.execute(
            "SELECT COUNT(*) FROM kline_cache WHERE symbol=? AND interval=?", 
            (symbol, interval)
        ).fetchone()[0]
        latest = cursor.execute(
            "SELECT MAX(timestamp) FROM kline_cache WHERE symbol=? AND interval=?", 
            (symbol, interval)
        ).fetchone()[0]
        earliest = cursor.execute(
            "SELECT MIN(timestamp) FROM kline_cache WHERE symbol=? AND interval=?", 
            (symbol, interval)
        ).fetchone()[0]
        print(f"  {symbol} {interval}: {count} 筆")
        print(f"    最新: {latest}")
        print(f"    最早: {earliest}")
    conn.close()

if __name__ == '__main__':
    import time
    main()
