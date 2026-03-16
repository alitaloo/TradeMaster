#!/usr/bin/env python3
"""分頁獲取 AAPL 完整歷史數據（富途 → MySQL）
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
    now = datetime.now()

    for interval in ['5m', '1h', '1d']:
        print(f"\n📊 {interval}...")
        ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)

        page = 1
        total_count = 0

        while page <= 10:  # 最多 10 頁
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

            with get_db_connection() as conn:
                cursor = conn.cursor()
                count = 0

                for _, row in resp_data.iterrows():
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
                             float(row['open']), float(row['high']),
                             float(row['low']), float(row['close']),
                             int(row['volume']), now)
                        )
                        count += 1
                    except Exception:
                        pass
                conn.commit()

            total_count += count
            print(f"  📄 Page {page}: {count} 筆 (MySQL)")

            if not page_req_key:
                break

            page += 1
            time.sleep(0.5)

        print(f"  ✅ {interval} 總計: {total_count} 筆")
        time.sleep(1)

    quote_ctx.close()

    # 統計 (MySQL)
    print(f"\n📊 數據庫統計 (MySQL):")
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for interval in ['5m', '1h', '1d']:
            cursor.execute(
                "SELECT COUNT(*), MAX(timestamp), MIN(timestamp) FROM kline_cache "
                "WHERE symbol = %s AND interval_val = %s",
                (symbol, interval)
            )
            row = cursor.fetchone()
            print(f"  {symbol} {interval}: {row[0]} 筆")
            print(f"    最新: {row[1]}  最早: {row[2]}")


if __name__ == '__main__':
    main()
