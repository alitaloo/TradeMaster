#!/usr/bin/env python3
"""Backfill Futu K-lines into MySQL kline_cache with pagination.

Goal:
- Fill missing / incomplete 5m and 1h bars for the trading universe (MySQL stocks.enabled=1)
- Date range: [start, end] (inclusive)

Why:
- Futu request_history_kline returns max_count bars per call (default 1000). Without paging,
  intraday intervals (5m/1h) will only contain a small number of days.

Usage:
  python3 backfill_futu_klines.py --start 2025-01-01 --end 2026-02-18 --intervals 5m,1h

Notes:
- Requires Futu OpenD running (QuoteContext on 127.0.0.1:11111)
- Writes to MySQL table: kline_cache (PK: symbol, interval_val, timestamp)
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import futu as ft
import pymysql

# project root
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config.database import PYMYSQL_CONFIG as MYSQL_CONFIG
except Exception:
    MYSQL_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster',
        'charset': 'utf8mb4',
    }

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

KL_TYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
    '1M': ft.KLType.K_MON,
}


def normalize_timestamp(time_key) -> str:
    """Normalize timestamp string to 'YYYY-MM-DD HH:MM:SS' (drop microseconds)."""
    ts = str(time_key)
    if len(ts) == 10:  # YYYY-MM-DD
        ts = ts + ' 00:00:00'
    # drop microseconds if any
    if '.' in ts:
        ts = ts.split('.')[0]
    return ts


def get_watchlist(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stocks WHERE enabled=1 ORDER BY symbol")
        return [r[0] for r in cur.fetchall()]


def upsert_page(cursor, symbol: str, interval: str, df):
    now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    sql = (
        "INSERT INTO kline_cache "
        "(symbol, interval_val, timestamp, open_price, high_price, low_price, close_price, volume, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE "
        "open_price=VALUES(open_price), high_price=VALUES(high_price), low_price=VALUES(low_price), "
        "close_price=VALUES(close_price), volume=VALUES(volume), updated_at=VALUES(updated_at)"
    )

    vals = []
    for _, row in df.iterrows():
        ts = normalize_timestamp(row['time_key'])
        vals.append(
            (
                symbol,
                interval,
                ts,
                float(row['open']),
                float(row['high']),
                float(row['low']),
                float(row['close']),
                int(row['volume']),
                now_utc,
            )
        )

    cursor.executemany(sql, vals)
    return len(vals)


def fetch_paged_kline(
    quote_ctx,
    symbol: str,
    interval: str,
    start: str,
    end: str,
    max_count: int = 1000,
    sleep_s: float = 0.15,
    retries: int = 3,
):
    """Yield pandas DataFrame pages for given symbol/interval within a (start,end) window.

    We still page using page_req_key, but callers should prefer chunking windows for intraday intervals
    to reduce timeouts.
    """
    ktype = KL_TYPE_MAP.get(interval)
    if ktype is None:
        raise ValueError(f"Unsupported interval: {interval}")

    page_req_key = None
    while True:
        last_err = None
        for attempt in range(1, retries + 1):
            try:
                ret, data, page_req_key = quote_ctx.request_history_kline(
                    symbol,
                    start=start,
                    end=end,
                    ktype=ktype,
                    max_count=max_count,
                    page_req_key=page_req_key,
                )
                last_err = None
                break
            except Exception as e:
                last_err = e
                time.sleep(min(2.0, 0.3 * attempt))

        if last_err is not None:
            raise RuntimeError(f"Futu request_history_kline exception: {symbol} {interval} {start}->{end}: {last_err}")

        if ret != ft.RET_OK:
            raise RuntimeError(f"Futu request_history_kline failed: {symbol} {interval} {start}->{end}: {data}")

        if data is None or data.empty:
            break

        yield data

        if not page_req_key:
            break

        time.sleep(sleep_s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start', required=True, help='YYYY-MM-DD')
    ap.add_argument('--end', required=True, help='YYYY-MM-DD')
    ap.add_argument('--intervals', default='5m,1h', help='Comma separated, e.g. 5m,1h')
    ap.add_argument('--symbols', default='', help='Comma separated override; empty uses stocks.enabled=1')
    ap.add_argument('--max-count', type=int, default=1000)
    ap.add_argument('--commit-every-pages', type=int, default=1)
    ap.add_argument('--sleep', type=float, default=0.15)
    ap.add_argument('--retries', type=int, default=3)
    ap.add_argument(
        '--chunk-days',
        default='5m:7,1h:120,1d:365',
        help='Chunk calendar days per interval, e.g. 5m:7,1h:120',
    )
    args = ap.parse_args()

    intervals = [s.strip() for s in args.intervals.split(',') if s.strip()]

    # parse chunk-days map
    chunk_days_map = {}
    for part in (args.chunk_days or '').split(','):
        part = part.strip()
        if not part or ':' not in part:
            continue
        k, v = part.split(':', 1)
        k = k.strip()
        try:
            chunk_days_map[k] = int(v)
        except Exception:
            pass

    from datetime import timedelta
    start_date = datetime.strptime(args.start, '%Y-%m-%d').date()
    end_date = datetime.strptime(args.end, '%Y-%m-%d').date()

    conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        if args.symbols.strip():
            symbols = [s.strip() for s in args.symbols.split(',') if s.strip()]
        else:
            symbols = get_watchlist(conn)

        print(f"Backfill range: {args.start} -> {args.end}")
        print(f"Symbols: {len(symbols)} | Intervals: {intervals}")
        sys.stdout.flush()

        quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        try:
            total_rows = 0
            for sym_i, symbol in enumerate(symbols, 1):
                for interval in intervals:
                    print(f"[{sym_i}/{len(symbols)}] {symbol} {interval} backfilling ...", flush=True)

                    pages = 0
                    inserted = 0

                    chunk_days = int(chunk_days_map.get(interval, 30))
                    cur_d = start_date

                    with conn.cursor() as cursor:
                        while cur_d <= end_date:
                            chunk_end = min(cur_d + timedelta(days=chunk_days - 1), end_date)
                            chunk_start_s = cur_d.strftime('%Y-%m-%d')
                            chunk_end_s = chunk_end.strftime('%Y-%m-%d')

                            for page in fetch_paged_kline(
                                quote_ctx,
                                symbol=symbol,
                                interval=interval,
                                start=chunk_start_s,
                                end=chunk_end_s,
                                max_count=args.max_count,
                                sleep_s=args.sleep,
                                retries=args.retries,
                            ):
                                pages += 1
                                inserted += upsert_page(cursor, symbol, interval, page)

                                if pages % args.commit_every_pages == 0:
                                    conn.commit()

                            # next chunk
                            cur_d = chunk_end + timedelta(days=1)

                        conn.commit()

                    total_rows += inserted
                    print(f"  -> pages={pages} upserted_rows={inserted}")

                    # small pause between symbols/intervals to avoid stressing OpenD
                    time.sleep(0.2)

            print(f"✅ DONE. Total upserted rows: {total_rows}")

        finally:
            quote_ctx.close()

    finally:
        conn.close()


if __name__ == '__main__':
    main()
