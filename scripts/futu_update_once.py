#!/usr/bin/env python3
"""
富途牛牛 K 線更新（單次運行）
用於 Cron 定時任務
自動判斷冬令時/夏令時
寫入 MySQL 數據庫
"""

import futu as ft
import pymysql
import os
import sys
from datetime import datetime, timezone
import time

# 導入市場時間判斷模組
try:
    from market_hours import should_update_kline, is_dst_us, print_status
    HAS_MARKET_HOURS = True
except ImportError:
    HAS_MARKET_HOURS = False

# MySQL 配置 - 從統一配置導入
import os
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
try:
    from config.database import PYMYSQL_CONFIG as MYSQL_CONFIG
except ImportError:
    # 備用配置
    MYSQL_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster',
        'charset': 'utf8mb4'
    }

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

def get_watchlist():
    """從數據庫獲取啟用的股票清單"""
    try:
        conn = pymysql.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM stocks WHERE enabled = 1 ORDER BY symbol")
        stocks = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        print(f"📋 從數據庫載入 {len(stocks)} 檔股票")
        return stocks
    except Exception as e:
        print(f"⚠️ 無法從數據庫獲取股票清單: {e}")
        # 備用清單
        return [
            "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
            "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
            "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
            "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
        ]

WATCHLIST = get_watchlist()

KL_TYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
    '1M': ft.KLType.K_MON,
}

INTERVALS = ['5m', '1h', '1d', '1w', '1M']

def get_mysql_connection():
    return pymysql.connect(**MYSQL_CONFIG)

def normalize_timestamp(time_key):
    """確保 timestamp 格式一致"""
    ts = str(time_key)
    # 如果只有日期沒有時間，補上 00:00:00
    if len(ts) == 10:  # YYYY-MM-DD
        ts = ts + ' 00:00:00'
    return ts

def main():
    now = datetime.now()
    print(f"\n⏰ [{now.strftime('%Y-%m-%d %H:%M:%S')}] 開始更新...")
    
    # 檢查是否在交易時段 (自動判斷冬令時/夏令時)
    if HAS_MARKET_HOURS:
        dst_status = "夏令時" if is_dst_us() else "冬令時"
        print(f"📅 當前模式: {dst_status}")
        
        if not should_update_kline():
            print("⏸️ 非交易時段，跳過更新")
            print(f"⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 結束")
            return
        print("✅ 交易時段，開始更新...")
    
    # 連接富途牛牛
    quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    print(f"✅ 連接成功")
    sys.stdout.flush()
    
    total = 0
    conn = get_mysql_connection()
    cursor = conn.cursor()
    
    # 先訂閱所有股票的 K 線（用於 get_cur_kline）
    print("📡 訂閱即時報價...")
    for symbol in WATCHLIST:
        quote_ctx.subscribe(symbol, KL_TYPE_MAP.values())
    time.sleep(1)  # 等待訂閱生效
    
    for symbol in WATCHLIST:
        for interval in INTERVALS:
            print(f"Fetching {symbol} {interval}...", flush=True)
            sys.stdout.flush()
            
            ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
            
            # 優先使用 get_cur_kline（訂閱方式，數據更齊全）
            ret, data = quote_ctx.get_cur_kline(symbol, 100, ktype)
            
            if ret == ft.RET_OK and data is not None and not data.empty:
                kline_data = data
            else:
                # 備用：使用歷史 K 線 API
                from datetime import timedelta
                from zoneinfo import ZoneInfo
                
                tz_us = ZoneInfo('America/New_York')
                now_us = datetime.now(tz_us)
                one_day_ago_us = (now_us - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
                
                result = quote_ctx.request_history_kline(
                    symbol,
                    start=one_day_ago_us,
                    end=now_us.strftime('%Y-%m-%d %H:%M:%S'),
                    ktype=ktype
                )
                
                if len(result) == 3:
                    ret, data, extra = result
                    kline_data = data if ret == ft.RET_OK else None
                else:
                    continue
            
            if ret == ft.RET_OK and data is not None and not data.empty:
                kline_data = data
                
            if kline_data is not None and not kline_data.empty:
                now_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
                count = 0
                
                for _, row in kline_data.iterrows():
                    try:
                        timestamp = normalize_timestamp(row['time_key'])
                        
                        cursor.execute('''
                            INSERT INTO kline_cache 
                            (symbol, interval_val, timestamp, open_price, high_price, low_price, close_price, volume, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                            open_price = VALUES(open_price),
                            high_price = VALUES(high_price),
                            low_price = VALUES(low_price),
                            close_price = VALUES(close_price),
                            volume = VALUES(volume),
                            updated_at = VALUES(updated_at)
                        ''', (
                            symbol, interval, timestamp,
                            float(row['open']), float(row['high']), 
                            float(row['low']), float(row['close']),
                            int(row['volume']), now_utc
                        ))
                        count += 1
                    except Exception as e:
                        print(f"Error inserting {symbol} {interval}: {e}")
                        pass
                
                conn.commit()
                total += count
            
            time.sleep(0.2)
    
    cursor.close()
    conn.close()
    quote_ctx.close()
    
    print(f"✅ 完成！新增 {total} 筆數據")
    print(f"⏰ [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 更新結束")

if __name__ == '__main__':
    main()
