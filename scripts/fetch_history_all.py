#!/usr/bin/env python3
"""
獲取所有股票的歷史 K 線數據
"""

import sqlite3
import yfinance as yf
from datetime import datetime
import time
import os

# 數據庫路徑
DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'

# 股票清單
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSM", "AMZN", 
    "META", "UBER", "MU", "AMD", "ORCL",
    "GOOGL", "GOOG", "NFLX", "ADBE", "CRM",
    "QCOM", "TXN", "AVGO", "COIN", "MSTR"
]

# 時間週期
INTERVALS = ['1m', '5m', '15m', '30m', '1h', '1d', '1w', '1M']

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

def fetch_history(symbol, interval='1d', period='1y'):
    """獲取單個股票的歷史數據"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            return []
        
        now = datetime.now().isoformat()
        data = []
        
        for idx, row in df.iterrows():
            data.append({
                'symbol': symbol,
                'interval': interval,
                'timestamp': idx.isoformat(),
                'open': round(row['Open'], 2),
                'high': round(row['High'], 2),
                'low': round(row['Low'], 2),
                'close': round(row['Close'], 2),
                'volume': int(row['Volume']),
                'updated_at': now
            })
        
        return data
        
    except Exception as e:
        print(f"❌ {symbol} {interval}: {e}")
        return []

def save_to_db(data_list):
    """存入數據庫"""
    if not data_list:
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for data in data_list:
        cursor.execute('''
            INSERT OR REPLACE INTO kline_cache
            (symbol, interval, timestamp, open, high, low, close, volume, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['symbol'], data['interval'], data['timestamp'],
            data['open'], data['high'], data['low'], data['close'],
            data['volume'], data['updated_at']
        ))
    
    conn.commit()
    conn.close()

def main():
    """主函數"""
    print("=" * 60)
    print("📊 獲取所有股票歷史數據")
    print("=" * 60)
    
    init_db()
    
    total_fetched = 0
    total_failed = 0
    
    for symbol in WATCHLIST:
        print(f"\n📈 {symbol}")
        
        # 優先獲取日線和長週期數據
        for interval in ['1d', '1w', '1M', '1h', '5m', '15m', '30m', '1m']:
            try:
                # 日線獲取 1 年歷史
                if interval == '1d':
                    data = fetch_history(symbol, interval, '1y')
                # 週線獲取 2 年歷史
                elif interval == '1w':
                    data = fetch_history(symbol, interval, '2y')
                # 月線獲取 5 年歷史
                elif interval == '1M':
                    data = fetch_history(symbol, interval, '5y')
                # 小時線獲取 1 個月歷史
                elif interval in ['1h', '30m', '15m']:
                    data = fetch_history(symbol, interval, '1mo')
                # 分鐘線獲取 5 天歷史
                else:
                    data = fetch_history(symbol, interval, '5d')
                
                if data:
                    save_to_db(data)
                    print(f"  ✅ {interval}: {len(data)} 筆")
                    total_fetched += len(data)
                else:
                    print(f"  ❌ {interval}: 無數據")
                
                # 避免 Rate Limit
                time.sleep(1)
                
            except Exception as e:
                print(f"  ❌ {interval}: {e}")
                total_failed += 1
    
    print("\n" + "=" * 60)
    print(f"✅ 完成！共獲取 {total_fetched} 筆數據")
    print(f"❌ 失敗: {total_failed} 次")
    print("=" * 60)

if __name__ == '__main__':
    main()
