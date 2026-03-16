#!/usr/bin/env python3
"""快速測試：只獲取 AAPL 數據（富途 → MySQL）
已從 SQLite (kline_cache.db) 遷移至 MySQL (2026-03-06)
"""

import futu as ft
import sys
import os
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_connection

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
            with get_db_connection() as conn:
                cursor = conn.cursor()
                now = datetime.now()
                count = 0

                for _, row in data.iterrows():
                    time_key = str(row['time_key'])
                    timestamp = time_key if ' ' in time_key else time_key + ' 00:00:00'
                    try:
                        cursor.execute(
                            '''
                            INSERT INTO kline_cache
                                (symbol, interval_val, timestamp, open_price, high_price,
                                 low_price, close_price, volume, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                                open_price = VALUES(open_price),
                                high_price = VALUES(high_price),
                                low_price = VALUES(low_price),
                                close_price = VALUES(close_price),
                                volume = VALUES(volume),
                                updated_at = VALUES(updated_at)
                            ''',
                            (symbol, interval, timestamp,
                             row['open'], row['high'], row['low'], row['close'],
                             int(row['volume']), now)
                        )
                        count += 1
                    except Exception:
                        pass
                conn.commit()
            print(f"  ✅ {interval}: {count} 筆 (MySQL)")
        else:
            print(f"  ❌ 無數據: {data}")

        time.sleep(0.3)

    quote_ctx.close()

    # 統計
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM kline_cache WHERE symbol = %s", (symbol,)
        )
        count = cursor.fetchone()[0]
    print(f"\n✅ AAPL 總計: {count} 筆 (MySQL)")


if __name__ == '__main__':
    main()
