#!/usr/bin/env python3
"""富途報價 + K線輪詢服務 - 每分鐘更新所有週期數據
已從 SQLite (kline_cache.db + realtime_quote) 全面遷移至 MySQL (2026-03-06)
"""

import futu as ft
import time
import os
import sys
import signal
import mysql.connector
from datetime import datetime, timezone

# MySQL 配置 - 從統一配置導入
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from config.database import MYSQL_CONFIG, get_db_connection
except ImportError:
    MYSQL_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster',
        'charset': 'utf8mb4'
    }
    from contextlib import contextmanager
    @contextmanager
    def get_db_connection():
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        try:
            yield conn
        finally:
            conn.close()


def get_watchlist():
    """從數據庫獲取啟用的股票清單"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM stocks WHERE enabled = 1 ORDER BY symbol")
            stocks = [row[0] for row in cursor.fetchall()]
        print(f"📋 從數據庫載入 {len(stocks)} 檔股票")
        return stocks
    except Exception as e:
        print(f"⚠️ 無法從數據庫獲取股票清單: {e}")
        return [
            'US.AAPL', 'US.MSFT', 'US.NVDA', 'US.GOOGL', 'US.AMZN',
            'US.META', 'US.TSM', 'US.AMD', 'US.MU', 'US.ORCL',
            'US.GOOG', 'US.NFLX', 'US.ADBE', 'US.CRM', 'US.QCOM',
            'US.TXN', 'US.AVGO', 'US.COIN', 'US.MSTR', 'US.UBER'
        ]


WATCHLIST = get_watchlist()

# K線類型映射
KTYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY
}
SUB_MAP = {
    '5m': ft.SubType.K_5M,
    '1h': ft.SubType.K_60M,
    '1d': ft.SubType.K_DAY
}

print(f"📡 Starting with {len(WATCHLIST)} stocks, {len(KTYPE_MAP)} timeframes")

running = True


def signal_handler(sig, frame):
    global running
    print("\n🛑 Stopping...")
    running = False


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_mysql_conn():
    return mysql.connector.connect(**MYSQL_CONFIG)


def update_quotes(quote_ctx):
    """更新即時報價至 MySQL realtime_quote 表"""
    try:
        ret, data = quote_ctx.get_stock_quote(WATCHLIST)
        if ret != 0 or data is None:
            return False

        with get_db_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

            for _, row in data.iterrows():
                code = row['code']
                cursor.execute(
                    '''
                    INSERT INTO realtime_quote
                        (symbol, last_price, open_price, high_price, low_price,
                         prev_close, volume, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        last_price = VALUES(last_price),
                        open_price = VALUES(open_price),
                        high_price = VALUES(high_price),
                        low_price = VALUES(low_price),
                        prev_close = VALUES(prev_close),
                        volume = VALUES(volume),
                        updated_at = VALUES(updated_at)
                    ''',
                    (
                        code,
                        row.get('last_price', 0),
                        row.get('open_price', 0),
                        row.get('high_price', 0),
                        row.get('low_price', 0),
                        row.get('prev_close_price', 0),
                        row.get('volume', 0),
                        now
                    )
                )
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ Quote Error: {e}")
        return False


def update_klines(quote_ctx):
    """更新 K線數據到 MySQL"""
    mysql_conn = get_mysql_conn()
    mysql_cursor = mysql_conn.cursor()

    total_updated = 0

    for symbol in WATCHLIST:
        for tf, ktype in KTYPE_MAP.items():
            try:
                ret, data = quote_ctx.get_cur_kline(symbol, num=50, ktype=ktype)
                if ret != 0 or data is None:
                    continue

                for _, row in data.iterrows():
                    time_key = str(row['time_key'])
                    timestamp = time_key if ' ' in time_key else time_key + ' 00:00:00'

                    mysql_cursor.execute(
                        """
                        INSERT INTO kline_cache
                        (symbol, interval_val, timestamp, open_price, high_price,
                         low_price, close_price, volume, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON DUPLICATE KEY UPDATE
                            open_price = VALUES(open_price),
                            high_price = VALUES(high_price),
                            low_price = VALUES(low_price),
                            close_price = VALUES(close_price),
                            volume = VALUES(volume),
                            updated_at = NOW()
                        """,
                        (
                            symbol, tf, timestamp,
                            row.get('open', 0), row.get('high', 0), row.get('low', 0),
                            row.get('close', 0), row.get('volume', 0)
                        )
                    )
                    total_updated += 1

            except Exception:
                continue

    mysql_conn.commit()
    mysql_conn.close()
    return total_updated


def main():
    global running

    quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

    # 訂閱所有 K線類型
    for sub in SUB_MAP.values():
        quote_ctx.subscribe(WATCHLIST, [sub])
    print("📊 Subscribed to all types")

    time.sleep(3)

    poll_count = 0
    while running:
        poll_count += 1

        # 更新報價 (每分鐘) → MySQL
        if update_quotes(quote_ctx):
            if poll_count % 5 == 1:
                print(f"✅ [{poll_count}] Quotes updated (MySQL)")

        # 每5分鐘更新一次 K線
        if poll_count % 5 == 1:
            print(f"📈 [{poll_count}] Updating K-lines...")
            klines_updated = update_klines(quote_ctx)
            print(f"  → Updated {klines_updated} K-line records (MySQL)")

        time.sleep(60)

    quote_ctx.close()
    print("👋 Stopped")


if __name__ == '__main__':
    main()
