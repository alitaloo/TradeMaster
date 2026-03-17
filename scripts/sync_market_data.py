#!/usr/bin/env python3
"""同步市場數據到 market 表"""
import os, sys
for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_db_cursor
from datetime import datetime

def sync():
    results = {}
    with get_db_cursor() as c:
        for symbol, label in [('US.SPY', 'SPY'), ('US.QQQ', 'QQQ')]:
            c.execute("SELECT close_price FROM kline_cache WHERE symbol=%s ORDER BY timestamp DESC LIMIT 1", (symbol,))
            row = c.fetchone()
            if row:
                results[label] = float(row['close_price'])
        
        # 計算 SPY 漲跌幅
        if 'SPY' in results:
            c.execute("SELECT close_price FROM kline_cache WHERE symbol='US.SPY' AND interval_val='5m' ORDER BY timestamp DESC LIMIT 80")
            rows = c.fetchall()
            if len(rows) >= 2:
                latest = float(rows[0]['close_price'])
                oldest = float(rows[-1]['close_price'])
                results['MARKET_DROP'] = round((latest - oldest) / oldest * 100, 2)
    
    # 更新 market 表
    with get_db_cursor() as c:
        for mtype, value in results.items():
            c.execute("UPDATE market SET value=%s, updated_at=NOW() WHERE type=%s", (value, mtype))
            if c.rowcount == 0:
                c.execute("INSERT INTO market (type, value, source, updated_at) VALUES (%s, %s, 'kline_cache', NOW())", (mtype, value))
            print(f"  ✅ {mtype} = {value}")
    
    print(f"✅ 已更新 {len(results)} 項")

if __name__ == '__main__':
    print(f"[{datetime.now()}] 同步市場數據...")
    sync()
