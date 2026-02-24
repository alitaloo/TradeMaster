#!/usr/bin/env python3
"""使用富途分頁獲取完整 K 線數據"""

import futu as ft
import sqlite3
from datetime import datetime, timedelta

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
    
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d')
    
    for interval_name, ktype in KL_TYPE_MAP.items():
        print(f"\n📊 {interval_name}...")
        
        # 分頁獲取，每次800筆
        page = 1
        total_count = 0
        
        while page <= 50:
            # 每次獲取800筆
            result = quote_ctx.request_history_kline(
                code='US.AAPL',
                start='2024-01-01',
                end=now_str,
                ktype=ktype,
                autype=ft.AuType.QFQ,
                max_count=800
            )
            
            if len(result) == 3:
                ret_code, resp_data, page_req_key = result
            else:
                break
            
            if ret_code != 0:
                print(f"  ❌ Page {page} 錯誤: {resp_data}")
                break
            
            if resp_data is None or resp_data.empty:
                print(f"  ✅ 完成，總計 {total_count} 筆")
                break
            
            # 保存到數據庫
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            now_iso = now.isoformat()
            count = 0
            
            for _, row in resp_data.iterrows():
                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO kline_cache
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        'US.AAPL', interval_name,
                        str(row['time_key']),
                        float(row['open']), float(row['high']), 
                        float(row['low']), float(row['close']),
                        int(row['volume']), now_iso
                    ))
                    count += 1
                except:
                    pass
            
            conn.commit()
            conn.close()
            
            total_count += count
            print(f"  📄 Page {page}: +{count} 筆")
            
            if not page_req_key:
                break
            
            page += 1
            time.sleep(0.3)
        
        time.sleep(1)
    
    quote_ctx.close()
    
    # 統計
    print(f"\n📊 數據庫統計:")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for interval_name in KL_TYPE_MAP.keys():
        count = cursor.execute(
            "SELECT COUNT(*) FROM kline_cache WHERE symbol='US.AAPL' AND interval=?", 
            (interval_name,)
        ).fetchone()[0]
        
        if count > 0:
            latest = cursor.execute(
                "SELECT MAX(timestamp) FROM kline_cache WHERE symbol='US.AAPL' AND interval=?", 
                (interval_name,)
            ).fetchone()[0]
            earliest = cursor.execute(
                "SELECT MIN(timestamp) FROM kline_cache WHERE symbol='US.AAPL' AND interval=?", 
                (interval_name,)
            ).fetchone()[0]
            print(f"  AAPL {interval_name}: {count} 筆")
            print(f"    最早: {earliest}")
            print(f"    最新: {latest}")
        else:
            print(f"  AAPL {interval_name}: 0 筆")
    
    conn.close()

if __name__ == '__main__':
    import time
    main()
