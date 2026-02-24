#!/usr/bin/env python3
"""Backfill Futu historical klines into MySQL kline_cache.

Goal: fill 5m/1h for enabled stocks from start->end (inclusive).

Notes:
- Uses proper pagination via page_req_key (fixes the common bug where only the first page is fetched).
- Writes into MySQL `kline_cache` with ON DUPLICATE KEY UPDATE.
- Normalizes timestamp to second precision: YYYY-MM-DD HH:MM:SS

Usage:
  python3 backfill_futu_kline_mysql.py --start 2025-01-01 --end 2026-02-18 --intervals 5m,1h
"""

import argparse
import sys
import time
from datetime import datetime

import futu as ft
import pymysql

# ---- config ----
PROJECT_ROOT = "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config.database import PYMYSQL_CONFIG as MYSQL_CONFIG
except Exception:
    MYSQL_CONFIG = {
        "host": "localhost",
        "user": "alita",
        "password": "alitamysql",
        "database": "trademaster",
        "charset": "utf8mb4",
    }

FUTU_HOST = "127.0.0.1"
FUTU_PORT = 11111

KLTYPE_MAP = {
    "5m": ft.KLType.K_5M,
    "1h": ft.KLType.K_60M,
    "1d": ft.KLType.K_DAY,
}


def norm_ts(time_key) -> str:
    """Normalize Futu time_key to 'YYYY-MM-DD HH:MM:SS' (second precision)."""
    s = str(time_key)
    # Common formats:
    # - 'YYYY-MM-DD'
    # - 'YYYY-MM-DD HH:MM:SS'
    # - 'YYYY-MM-DD HH:MM:SS.ssssss'
    if len(s) == 10:
        return s + " 00:00:00"
    if len(s) >= 19:
        return s[:19]
    # fallback
    try:
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return s


def get_enabled_symbols(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT symbol FROM stocks WHERE enabled=1 ORDER BY symbol")
        return [r[0] for r in cur.fetchall()]


def upsert_page(conn, symbol: str, interval: str, df) -> int:
    if df is None or df.empty:
        return 0

    now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for _, r in df.iterrows():
        try:
            ts = norm_ts(r["time_key"])
            rows.append(
                (
                    symbol,
                    interval,
                    ts,
                    float(r["open"]),
                    float(r["high"]),
                    float(r["low"]),
                    float(r["close"]),
                    int(r["volume"]),
                    now_utc,
                )
            )
        except Exception:
            continue

    if not rows:
        return 0

    sql = """
    INSERT INTO kline_cache
      (symbol, interval_val, timestamp, open_price, high_price, low_price, close_price, volume, updated_at)
    VALUES
      (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      open_price=VALUES(open_price),
      high_price=VALUES(high_price),
      low_price=VALUES(low_price),
      close_price=VALUES(close_price),
      volume=VALUES(volume),
      updated_at=VALUES(updated_at)
    """

    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()
    return len(rows)


def backfill_symbol_interval(quote_ctx, mysql_conn, symbol: str, interval: str, start: str, end: str, sleep_s: float) -> int:
    ktype = KLTYPE_MAP.get(interval)
    if not ktype:
        raise ValueError(f"Unsupported interval: {interval}")

    total = 0
    page_req_key = None
    page = 0
    seen_keys = set()

    while True:
        page += 1
        ret, data, page_req_key = quote_ctx.request_history_kline(
            code=symbol,
            start=start,
            end=end,
            ktype=ktype,
            autype=ft.AuType.QFQ,
            max_count=1000,
            page_req_key=page_req_key,
        )

        if ret != ft.RET_OK:
            raise RuntimeError(f"Futu error: {data}")

        if data is None or data.empty:
            break

        inserted = upsert_page(mysql_conn, symbol, interval, data)
        total += inserted

        print(f"[{symbol} {interval}] page={page} rows={len(data)} upserted={inserted} total={total}", flush=True)

        if not page_req_key:
            break

        # defensive: avoid infinite loop on repeated keys
        if page_req_key in seen_keys:
            print(f"[{symbol} {interval}] WARNING: repeated page_req_key, break.", flush=True)
            break
        seen_keys.add(page_req_key)

        time.sleep(sleep_s)

    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True, help="YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD")
    ap.add_argument("--intervals", default="5m,1h", help="comma separated: 5m,1h")
    ap.add_argument("--symbols", default="", help="optional comma separated symbols (default: enabled stocks)")
    ap.add_argument("--sleep", type=float, default=0.25, help="sleep seconds between futu page requests")
    args = ap.parse_args()

    intervals = [s.strip() for s in args.intervals.split(",") if s.strip()]

    mysql_conn = pymysql.connect(**MYSQL_CONFIG)
    try:
        if args.symbols.strip():
            symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        else:
            symbols = get_enabled_symbols(mysql_conn)

        print(f"Backfill range: {args.start} -> {args.end}")
        print(f"Symbols: {len(symbols)}")
        print(f"Intervals: {intervals}")

        quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        try:
            grand_total = 0
            for sym in symbols:
                for iv in intervals:
                    try:
                        n = backfill_symbol_interval(quote_ctx, mysql_conn, sym, iv, args.start, args.end, args.sleep)
                        grand_total += n
                    except Exception as e:
                        print(f"[{sym} {iv}] ERROR: {e}", flush=True)
                        # continue other symbols
                        time.sleep(1)

            print(f"DONE. total_upserted={grand_total}")
        finally:
            quote_ctx.close()

    finally:
        mysql_conn.close()


if __name__ == "__main__":
    main()
