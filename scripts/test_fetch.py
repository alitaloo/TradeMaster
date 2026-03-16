#!/usr/bin/env python3
"""
測試富途牛牛獲取單個股票歷史數據（→ MySQL）
已從 SQLite (kline_cache.db) 遷移至 MySQL (2026-03-06)
"""

import futu as ft
import sys
import os
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_connection

KL_TYPE_MAP = {
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
    '1M': ft.KLType.K_MON,
}


def main():
    print("=" * 60)
    print("📊 測試富途牛牛獲取數據 (→ MySQL)")
    print("=" * 60)

    print("🔗 連接富途牛牛...")
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

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

        now = datetime.now()
        with get_db_connection() as conn:
            cursor = conn.cursor()
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
                except Exception:
                    pass
            conn.commit()
        print(f"\n✅ 已存入 MySQL")
    else:
        print(f"❌ 失敗: {data}")

    quote_ctx.close()

    # 統計
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM kline_cache")
        count = cursor.fetchone()[0]
    print(f"\n📊 MySQL kline_cache 總筆數: {count}")


if __name__ == '__main__':
    main()
