#!/usr/bin/env python3
"""同步市場數據到 market 表"""
import os, sys
for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_db_cursor
from datetime import datetime
import requests
import re


def fetch_vix() -> float:
    """從 Yahoo Finance 獲取 VIX 指數"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(
            'https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=2d',
            headers=headers, timeout=10
        )
        closes = r.json()['chart']['result'][0]['indicators']['quote'][0]['close']
        vix = [c for c in closes if c][-1]
        return round(vix, 2)
    except Exception:
        pass
    
    # Fallback: Google Finance
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get('https://www.google.com/finance/quote/VIX:INDEXCBOE', headers=headers, timeout=10)
        m = re.search(r'data-last-price="([0-9.]+)"', r.text)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    
    return 0.0


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
    
    # VIX
    vix = fetch_vix()
    if vix > 0:
        results['VIX'] = vix
    
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
