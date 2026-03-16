#!/usr/bin/env python3
"""
使用富途牛牛獲取所有股票的歷史 K 線數據
已從 SQLite (kline_cache.db) 遷移至 MySQL (2026-03-06)
"""

import futu as ft
import sys
import os
from datetime import datetime
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
from config.database import get_db_connection

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

KL_TYPE_MAP = {
    '1m': ft.KLType.K_1M,
    '5m': ft.KLType.K_5M,
    '15m': ft.KLType.K_15M,
    '30m': ft.KLType.K_30M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
    '1M': ft.KLType.K_MON
}

INTERVALS = ['1d', '1w', '1M', '1h', '5m', '15m', '30m', '1m']

PERIOD_MAP = {
    '1d': '1y', '1w': '2y', '1M': '5y',
    '1h': '3mo', '5m': '1mo', '15m': '1mo', '30m': '1mo', '1m': '5d'
}


class FutuDataFetcher:
    """富途數據獲取器"""

    def __init__(self):
        self.quote_ctx = None

    def connect(self):
        """連接富途牛牛"""
        print(f"🔗 連接富途牛牛 ({FUTU_HOST}:{FUTU_PORT})...")
        self.quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)

        result = self.quote_ctx.get_user_info()
        if len(result) == 3:
            ret, data, extra = result
        else:
            print(f"❌ 連接失敗: 未知的返回格式")
            return False

        if ret == ft.RET_OK:
            print(f"✅ 連接成功！用戶: {data.get('nick_name', 'Unknown')}")
            return True
        else:
            print(f"❌ 連接失敗: {data}")
            return False

    def disconnect(self):
        if self.quote_ctx:
            self.quote_ctx.close()
            print("🔌 已斷開富途牛牛連接")

    def fetch_kline(self, symbol, interval='1d', period='1y'):
        """獲取單個股票的 K 線數據"""
        ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)

        result = self.quote_ctx.request_history_kline(
            symbol,
            start='2020-01-01',
            end=datetime.now().strftime('%Y-%m-%d'),
            ktype=ktype
        )

        if len(result) == 3:
            ret, data, extra = result
        else:
            return None

        if ret == ft.RET_OK:
            return data
        else:
            print(f"❌ {symbol} {interval}: {data}")
            return None

    def save_to_db(self, symbol, interval, data):
        """存入 MySQL kline_cache"""
        if data is None or data.empty:
            return 0

        now = datetime.now()
        count = 0

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
                    count += 1
                except Exception:
                    pass
            conn.commit()
        return count


def main():
    """主函數"""
    print("=" * 60)
    print("📊 使用富途牛牛獲取所有股票歷史數據 (→ MySQL)")
    print("=" * 60)

    fetcher = FutuDataFetcher()
    if not fetcher.connect():
        print("❌ 無法連接富途牛牛，請確保客戶端已打開")
        return

    total_fetched = 0
    total_errors = 0

    try:
        for symbol in WATCHLIST:
            print(f"\n📈 {symbol}")

            for interval in INTERVALS:
                try:
                    period = PERIOD_MAP.get(interval, '1y')
                    data = fetcher.fetch_kline(symbol, interval, period)

                    if data is not None and not data.empty:
                        count = fetcher.save_to_db(symbol, interval, data)
                        print(f"  ✅ {interval}: {count} 筆 (MySQL)")
                        total_fetched += count
                    else:
                        print(f"  ❌ {interval}: 無數據")
                        total_errors += 1

                    time.sleep(0.5)

                except Exception as e:
                    print(f"  ❌ {interval}: {e}")
                    total_errors += 1

    finally:
        fetcher.disconnect()

    print("\n" + "=" * 60)
    print(f"✅ 完成！共獲取 {total_fetched} 筆數據 (MySQL)")
    print(f"❌ 失敗: {total_errors} 次")
    print("=" * 60)


if __name__ == '__main__':
    main()
