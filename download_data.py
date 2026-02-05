#!/usr/bin/env python3
"""
TradeMaster v2 - 歷史數據下載 (Stooq)

功能:
1. 從 Stooq 下載股票日線數據
2. 保存到本地 CSV
"""

import pandas as pd
import urllib.request
import ssl
import time
from datetime import datetime
from pathlib import Path

# SSL 上下文（忽略證書驗證）
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# 路徑配置
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data" / "historical"

# 16 隻股票
STOCKS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA",  # 科技巨頭
    "TSM", "AMD", "INTC", "AVGO",                       # 半導體
    "UBER", "ORCL",                                     # 軟體/服務
    "WDC", "MU",                                        # 儲存/記憶體
    "COIN",                                             # 加密
    "RKLB"                                              # 太空
]


def ensure_dirs():
    """確保目錄存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📁 數據目錄: {DATA_DIR}")


def download_from_stooq(symbol: str) -> pd.DataFrame:
    """從 Stooq 下載日線數據"""
    try:
        # Stooq URL format: daily data for US stocks
        url = f"https://stooq.com/q/d/l/?s={symbol.lower()}.us&i=d"
        
        with urllib.request.urlopen(url, context=ssl_context, timeout=10) as response:
            df = pd.read_csv(response)
        
        if df is not None and not df.empty:
            # Stooq columns: Date, Open, High, Low, Close, Volume
            df = df.rename(columns={
                'Date': 'Date',
                'Open': 'Open',
                'High': 'High',
                'Low': 'Low',
                'Close': 'Close',
                'Volume': 'Volume'
            })
            df = df.sort_values('Date')
            return df
        
    except Exception as e:
        print(f"   ⚠️ Stooq 失敗: {e}")
    
    return None


def download_stock(symbol: str) -> pd.DataFrame:
    """下載單一股票數據"""
    print(f"📥 下載 {symbol}...", end=" ", flush=True)
    
    df = download_from_stooq(symbol)
    
    if df is not None and not df.empty:
        print(f"✅ {len(df)} 天")
        return df
    
    print("❌ 失敗")
    return None


def save_to_csv(df: pd.DataFrame, symbol: str):
    """保存到 CSV"""
    filepath = DATA_DIR / f"{symbol}.csv"
    df.to_csv(filepath)


def download_all():
    """下載所有股票"""
    print("\n" + "=" * 60)
    print("           TradeMaster v2 - 數據下載 (Stooq)")
    print("=" * 60)
    print(f"\n📊 股票數: {len(STOCKS)}")
    
    ensure_dirs()
    
    success = 0
    failed = []
    
    for symbol in STOCKS:
        df = download_stock(symbol)
        
        if df is not None and not df.empty:
            save_to_csv(df, symbol)
            success += 1
        else:
            failed.append(symbol)
        
        time.sleep(1)  # 避免過快請求
    
    print(f"\n✅ 成功: {success}/{len(STOCKS)}")
    if failed:
        print(f"❌ 失敗: {', '.join(failed)}")
    
    return success, failed


def list_data():
    """列出已下載的數據"""
    print("\n📊 已下載的股票數據:")
    print("-" * 50)
    print(f"{'股票':<10} {'開始日期':<12} {'結束日期':<12} {'天數':<8}")
    print("-" * 50)
    
    for symbol in STOCKS:
        filepath = DATA_DIR / f"{symbol}.csv"
        if filepath.exists():
            try:
                df = pd.read_csv(filepath)
                if not df.empty:
                    print(f"{symbol:<10} {df['Date'].iloc[0]} {df['Date'].iloc[-1]} {len(df)}")
            except:
                print(f"{symbol:<10} 讀取錯誤")
    
    print("-" * 50)


def load_stock(symbol: str) -> pd.DataFrame:
    """讀取股票數據"""
    filepath = DATA_DIR / f"{symbol}.csv"
    if filepath.exists():
        return pd.read_csv(filepath)
    return None


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="TradeMaster v2 數據管理 (Stooq)")
    parser.add_argument("--download", action="store_true", help="下載所有數據")
    parser.add_argument("--list", action="store_true", help="列出已下載數據")
    parser.add_argument("--symbol", type=str, help="指定股票")
    
    args = parser.parse_args()
    
    if args.download:
        download_all()
    elif args.list:
        list_data()
    elif args.symbol:
        df = download_stock(args.symbol)
        if df is not None:
            save_to_csv(df, args.symbol)
            print(f"✅ 已保存: {DATA_DIR / f'{args.symbol}.csv'}")
    else:
        print("使用方法:")
        print("  python3 download_data.py --download   # 下載所有數據")
        print("  python3 download_data.py --list       # 列出已下載數據")
        print("  python3 download_data.py --symbol AAPL  # 下載單一股票")
        list_data()
