#!/usr/bin/env python3
"""快速測試：只獲取 AAPL 數據"""

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
    
    # 只獲取 AAPL
    symbol = 'US.AAPL'
    for interval in ['5m', '1h', '1d']:
        print(f"\n📈 {symbol} {interval}...")
        ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
        
        result = quote_ctx.request_history_kline(
            symbol,
            start='2025-01-01',
            end='2025-01-31',
            ktype=ktype
        )
        
        if len(result) == 3:
            ret, data, extra = result
        else:
            continue
        
        if ret == 0 and data is not None and not data.empty:
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
            print(f"  ✅ {interval}: {count} 筆")
        else:
            print(f"  ❌ 無數據: {data}")
        
        time.sleep(0.3)
    
    quote_ctx.close()
    
    # 檢查
    count = sqlite3.connect(DB_PATH).cursor().execute(
        "SELECT COUNT(*) FROM kline_cache WHERE symbol=?", (symbol,)
    ).fetchone()[0]
    print(f"\n✅ AAPL 總計: {count} 筆")

if __name__ == '__main__':
    import time
    main()
