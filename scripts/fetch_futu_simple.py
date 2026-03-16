#!/usr/bin/env python3
"""
獲取所有股票的歷史 K 線數據（富途牛牛版）
已從 SQLite (kline_cache.db) 遷移至 MySQL (2026-03-06)
"""

import futu as ft
import sys
import os
from datetime import datetime
import time

# 導入 MySQL 配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_connection, MYSQL_CONFIG

WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]
KL_TYPE_MAP = {
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
}


def fetch_and_save(symbol, interval, quote_ctx):
    ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)

    result = quote_ctx.request_history_kline(
        symbol,
        start='2024-01-01',
        end='2025-01-31',
        ktype=ktype
    )

    if len(result) == 3:
        ret, data, extra = result
    else:
        return 0

    if ret == ft.RET_OK and data is not None and not data.empty:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now()
            count = 0

            for _, row in data.iterrows():
                time_key = str(row['time_key'])
                # 補全時間格式
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
                        (
                            symbol, interval, timestamp,
                            row['open'], row['high'], row['low'], row['close'],
                            int(row['volume']), now
                        )
                    )
                    count += 1
                except Exception:
                    pass

            conn.commit()
        return count
    else:
        return 0


def main():
    print("=" * 60)
    print("📊 獲取所有股票歷史數據（富途牛牛 → MySQL）")
    print("=" * 60)

    print("🔗 連接富途牛牛...")
    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

    total = 0
    for symbol in WATCHLIST:
        for interval in ['1d', '1w']:
            count = fetch_and_save(symbol, interval, quote_ctx)
            if count > 0:
                print(f"  ✅ {symbol} {interval}: {count} 筆")
                total += count
            else:
                print(f"  ❌ {symbol} {interval}: 0 筆")

            time.sleep(0.3)

    quote_ctx.close()

    # 統計
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM kline_cache")
        final_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT symbol) FROM kline_cache")
        symbol_count = cursor.fetchone()[0]

    print("\n" + "=" * 60)
    print(f"✅ 完成！共 {symbol_count} 支股票，{final_count} 筆數據（MySQL）")
    print("=" * 60)


if __name__ == '__main__':
    main()
