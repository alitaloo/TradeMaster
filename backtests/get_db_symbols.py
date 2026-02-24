"""從 MySQL 獲取實盤股票清單和 K 線數據"""
import pymysql
import pandas as pd
from datetime import datetime, timedelta

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'alita',
    'password': 'alitamysql',
    'database': 'trademaster'
}

def get_trading_symbols():
    """從 MySQL stocks 表獲取實盤股票"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    cursor.execute("SELECT symbol FROM stocks WHERE enabled = 1")
    rows = cursor.fetchall()
    
    symbols = [r[0] for r in rows]  # 保留完整 symbol 如 US.AAPL
    
    conn.close()
    return symbols


def get_kline_data(symbol: str, days: int = 500, interval: str = '1d') -> pd.DataFrame:
    """
    從 MySQL kline_cache 獲取 K 線數據
    
    Args:
        symbol: 股票代碼 (如 'US.AAPL')
        days: 獲取最近 N 天的數據
        interval: K 線週期 (如 '1d', '1h', '5m')
    
    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 計算截止日期
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # 查詢 kline_cache 表
    cursor.execute("""
        SELECT timestamp, open_price, high_price, low_price, close_price, volume
        FROM kline_cache 
        WHERE symbol = %s AND interval_val = %s AND timestamp >= %s
        ORDER BY timestamp ASC
    """, (symbol, interval, cutoff))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return pd.DataFrame()
    
    # 轉換為 DataFrame，與 backtest 引擎相容
    df = pd.DataFrame(rows, columns=['Date', 'Open', 'High', 'Low', 'Close', 'Volume'])
    # timestamp 欄位在 DB 可能有秒/微秒混合格式
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce', format='mixed')
    df.set_index('Date', inplace=True)
    
    # 確保數值類型正確
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df = df.dropna()
    
    return df


if __name__ == '__main__':
    symbols = get_trading_symbols()
    print(f"實盤股票清單 ({len(symbols)}): {symbols}")
