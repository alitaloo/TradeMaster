#!/usr/bin/env python3
"""
使用富途牛牛獲取所有股票的歷史 K 線數據
"""

import futu as ft
import sqlite3
import os
from datetime import datetime
import time

# 數據庫路徑
DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'

# 富途連接配置
FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

# 股票清單（美股）
WATCHLIST = [
    "US.AAPL", "US.MSFT", "US.NVDA", "US.GOOGL", "US.AMZN",
    "US.META", "US.TSM", "US.AMD", "US.MU", "US.ORCL",
    "US.GOOG", "US.NFLX", "US.ADBE", "US.CRM", "US.QCOM",
    "US.TXN", "US.AVGO", "US.COIN", "US.MSTR", "US.UBER"
]

# 富途 K 線類型對應
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

# 時間週期列表（按優先級）
INTERVALS = ['1d', '1w', '1M', '1h', '5m', '15m', '30m', '1m']

# 歷史範圍
PERIOD_MAP = {
    '1d': '1y',   # 日線取1年
    '1w': '2y',   # 週線取2年
    '1M': '5y',   # 月線取5年
    '1h': '3mo',  # 小時線取3個月
    '5m': '1mo',  # 5分鐘取1個月
    '15m': '1mo', # 15分鐘取1個月
    '30m': '1mo', # 30分鐘取1個月
    '1m': '5d'    # 1分鐘取5天
}

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
    print("✅ 數據庫初始化完成")

class FutuDataFetcher:
    """富途數據獲取器"""
    
    def __init__(self):
        self.quote_ctx = None
    
    def connect(self):
        """連接富途牛牛"""
        print(f"🔗 連接富途牛牛 ({FUTU_HOST}:{FUTU_PORT})...")
        self.quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
        
        # 檢查連接狀態
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
        """斷開連接"""
        if self.quote_ctx:
            self.quote_ctx.close()
            print("🔌 已斷開富途牛牛連接")
    
    def fetch_kline(self, symbol, interval='1d', period='1y'):
        """獲取單個股票的 K 線數據"""
        ktype = KL_TYPE_MAP.get(interval, ft.KLType.K_DAY)
        
        # 請求歷史 K 線（富途返回 3 個值）
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
        """存入數據庫"""
        if data is None or data.empty:
            return 0
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        now = datetime.now().isoformat()
        count = 0
        
        for _, row in data.iterrows():
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO kline_cache
                    (symbol, interval, timestamp, open, high, low, close, volume, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    symbol, interval,
                    str(row['time_key']),
                    row['open'], row['high'], row['low'], row['close'],
                    int(row['volume']), now
                ))
                count += 1
            except Exception as e:
                pass
        
        conn.commit()
        conn.close()
        return count

def main():
    """主函數"""
    print("=" * 60)
    print("📊 使用富途牛牛獲取所有股票歷史數據")
    print("=" * 60)
    
    # 初始化數據庫
    init_db()
    
    # 連接富途牛牛
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
                        print(f"  ✅ {interval}: {count} 筆")
                        total_fetched += count
                    else:
                        print(f"  ❌ {interval}: 無數據")
                        total_errors += 1
                    
                    # 避免請求過快
                    time.sleep(0.5)
                    
                except Exception as e:
                    print(f"  ❌ {interval}: {e}")
                    total_errors += 1
    
    finally:
        fetcher.disconnect()
    
    print("\n" + "=" * 60)
    print(f"✅ 完成！共獲取 {total_fetched} 筆數據")
    print(f"❌ 失敗: {total_errors} 次")
    print("=" * 60)

if __name__ == '__main__':
    main()
