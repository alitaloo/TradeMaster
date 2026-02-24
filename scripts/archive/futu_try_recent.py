#!/usr/bin/env python3
"""嘗試獲取富途 AAPL 更近的數據"""

import futu as ft
import sqlite3
from datetime import datetime

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'

KL_TYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
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
    
    for interval_name, ktype in KL_TYPE_MAP.items():
        print(f"\n📊 {interval_name}...")
        
        all_data = []
        
        # 更近的日期範圍
        ranges = [
            ('2025-06-01', now.strftime('%Y-%m-%d')),
            ('2025-08-01', now.strftime('%Y-%m-%d')),
            ('2025-10-01', now.strftime('%Y-%m-%d')),
            ('2025-12-01', now.strftime('%Y-%m-%d')),
        ]
        
        for start, end in ranges:
            print(f"  嘗試: {start} ~ {end}")
            
            result = quote_ctx.request_history_kline(
                code='US.AAPL',
                start=start,
                end=end,
                ktype=ktype,
                autype=ft.AuType.QFQ,
                max_count=1000
            )
            
            if len(result) == 3:
                ret_code, resp_data, page_req_key = result
            else:
                continue
            
            if ret_code != 0:
                print(f"    ❌ 錯誤: {resp_data}")
                continue
            
            if resp_data is None or resp_data.empty:
                print(f"    ⚠️ 無數據")
                continue
            
            count = len(resp_data)
            print(f"    ✅ {count} 筆")
            all_data.extend(resp_data.to_dict('records'))
            
            time.sleep(0.5)
        
        # 去重並保存
        if all_data:
            seen = set()
            unique_data = []
            for d in all_data:
                key = str(d['time_key'])
                if key not in seen:
                    seen.add(key)
                    unique_data.append(d)
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            now_iso = now.isoformat()
            count = 0
            
            # 只刪除舊數據，保留最新的
            cursor.execute(
                "DELETE FROM kline_cache WHERE symbol='US.AAPL' AND interval=?",
                (interval_name,)
            )
            
            for row in unique_data:
                try:
                    cursor.execute('''
                        INSERT INTO kline_cache
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
            print(f"  💾 保存 {count} 筆")
        
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
    print(f"\n✅ 完成!")

if __name__ == '__main__':
    import time
    main()
