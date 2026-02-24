#!/usr/bin/env python3
"""使用 yfinance 獲取最新 K 線數據"""

import yfinance as yf
import sqlite3
from datetime import datetime, timedelta

DB_PATH = '/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/kline_cache.db'
INTERVALS = {
    '5m': ('5m', '7d'),      # 5分鐘線，最近7天
    '1h': ('1h', '730d'),   # 1小時線，最近2年
    '1d': ('1d', '5y'),     # 日線，最近5年
}

def main():
    print("📈 從 Yahoo Finance 獲取最新數據...")
    
    symbol = 'AAPL'
    now = datetime.now()
    
    for interval_name, (yf_interval, period) in INTERVALS.items():
        print(f"\n📊 {interval_name} ({yf_interval})...")
        
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(interval=yf_interval, period=period)
            
            if df.empty:
                print(f"  ⚠️ 無數據")
                continue
            
            # 轉換時區為台北時間
            df.index = df.index.tz_convert('Asia/Taipei')
            
            # 插入數據庫
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            count = 0
            
            for idx, row in df.iterrows():
                timestamp = idx.strftime('%Y-%m-%d %H:%M:%S')
                
                # 檢查是否已存在
                cursor.execute(
                    'SELECT 1 FROM kline_cache WHERE symbol=? AND interval=? AND timestamp=?',
                    (f'US.{symbol}', interval_name, timestamp)
                )
                if cursor.fetchone():
                    continue
                
                cursor.execute('''
                    INSERT INTO kline_cache
                    (symbol, interval, timestamp, open, high, low, close, volume, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    f'US.{symbol}', interval_name,
                    timestamp,
                    float(row['Open']), float(row['High']), 
                    float(row['Low']), float(row['Close']),
                    int(row['Volume']), now.isoformat()
                ))
                count += 1
            
            conn.commit()
            conn.close()
            
            print(f"  ✅ 新增 {count} 筆")
            
            # 統計
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            total = cursor.execute(
                'SELECT COUNT(*) FROM kline_cache WHERE symbol=? AND interval=?', 
                (f'US.{symbol}', interval_name)
            ).fetchone()[0]
            latest = cursor.execute(
                'SELECT MAX(timestamp) FROM kline_cache WHERE symbol=? AND interval=?', 
                (f'US.{symbol}', interval_name)
            ).fetchone()[0]
            print(f"  📊 總計: {total} 筆 (最新: {latest})")
            conn.close()
            
        except Exception as e:
            print(f"  ❌ 錯誤: {e}")
    
    print("\n✅ 完成!")

if __name__ == '__main__':
    main()
