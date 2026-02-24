#!/usr/bin/env python3
"""
開盤時間自動更新 K 線數據
- 週期：5m, 1h, 1d, 1w, 1M
- 開盤時間（美股 9:30-16:00 ET）每 5 分鐘更新
- 使用富途牛牛實時 K 線接口
"""

import futu as ft
import sqlite3
import os
from datetime import datetime, timezone
import time
import schedule
import signal
import sys

# 配置
DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'
FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111
UPDATE_INTERVAL = 5  # 分鐘

# 股票清單
WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

# 富途 K 線類型
KL_TYPE_MAP = {
    '5m': ft.KLType.K_5M,
    '1h': ft.KLType.K_60M,
    '1d': ft.KLType.K_DAY,
    '1w': ft.KLType.K_WEEK,
    '1M': ft.KLType.K_MON,
}

INTERVALS = ['5m', '1h', '1d', '1w', '1M']

# 全局變量
quote_ctx = None
running = True

def signal_handler(sig, frame):
    """處理退出信號"""
    global running
    print("\n🛑 收到退出信號，正在停止...")
    running = False
    if quote_ctx:
        quote_ctx.close()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def init_db():
    """初始化數據庫"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS kline_cache (
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (symbol, interval, timestamp)
        )
    ''')
    conn.commit()
    conn.close()

def connect_futu():
    """連接富途牛牛"""
    global quote_ctx
    print(f"🔗 連接富途牛牛 ({FUTU_HOST}:{FUTU_PORT})...")
    quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    
    ret, data = quote_ctx.get_user_info()
    if ret == ft.RET_OK:
        print(f"✅ 連接成功！用戶: {data.get('nick_name', 'Unknown')}")
        return True
    else:
        print(f"❌ 連接失敗: {data}")
        return False

def disconnect_futu():
    """斷開富途牛牛"""
    global quote_ctx
    if quote_ctx:
        quote_ctx.close()
        print("🔌 已斷開富途牛牛連接")

def fetch_and_save(symbol, interval):
    """獲取並保存 K 線"""
    if not quote_ctx:
        return 0
    
    ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
    
    # 獲取最近 10 根 K 線
    result = quote_ctx.request_history_kline(
        symbol,
        start='2025-01-01',
        end=datetime.now().strftime('%Y-%m-%d'),
        ktype=ktype
    )
    
    if len(result) == 3:
        ret, data, extra = result
    else:
        return 0
    
    if ret == ft.RET_OK and data is not None and not data.empty:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
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
        return count
    return 0

def update_all():
    """更新所有股票的 K 線"""
    if not quote_ctx:
        if not connect_futu():
            return
    
    now = datetime.now()
    print(f"\n⏰ [{now.strftime('%H:%M:%S')}] 開始更新 K 線數據...")
    
    total = 0
    for symbol in WATCHLIST:
        for interval in INTERVALS:
            count = fetch_and_save(symbol, interval)
            if count > 0:
                total += count
            time.sleep(0.2)  # 避免請求過快
    
    print(f"✅ [{now.strftime('%H:%M:%S')}] 完成！新增 {total} 筆數據")

def is_market_open():
    """檢查美股是否開盤"""
    now = datetime.now()
    # 美股時間 (ET)
    et_hour = (now.hour - 12) % 24  # 台北 +12 = ET
    
    # 開盤: 9:30 - 16:00 ET
    return 9 <= et_hour < 16

def main():
    """主函數"""
    print("=" * 60)
    print("📊 富途牛牛 K 線自動更新服務")
    print("=" * 60)
    print(f"股票數量: {len(WATCHLIST)}")
    print(f"更新週期: {INTERVALS}")
    print(f"更新間隔: 每 {UPDATE_INTERVAL} 分鐘")
    print(f"數據庫: {DB_PATH}")
    print("=" * 60)
    
    init_db()
    
    if not connect_futu():
        print("❌ 無法連接富途牛牛，退出")
        return
    
    # 設置定時任務
    schedule.every(UPDATE_INTERVAL).minutes.do(update_all)
    
    # 立即執行一次
    print("\n🚀 立即執行第一次更新...")
    update_all()
    
    print("\n" + "=" * 60)
    print("📡 服務已啟動，等待定時任務...")
    print("按 Ctrl+C 退出")
    print("=" * 60)
    
    # 主循環
    while running:
        schedule.run_pending()
        time.sleep(1)
    
    disconnect_futu()
    print("👋 服務已停止")

if __name__ == '__main__':
    main()
