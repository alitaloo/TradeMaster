#!/usr/bin/env python3
"""
TradeMaster v2 - 每日信號推送腳本
功能：
1. 檢查數據狀態
2. 生成信號
3. 發送摘要
"""

import subprocess
import json
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# 台北時區
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# 數據目錄
DATA_DIR = Path(__file__).parent / "data" / "historical"

# 導入統一股票配置
from config.constants import STOCKS as DEFAULT_STOCKS

# 2026-02-12: 優化股票池 - 剔除 TSLA、INTC、RKLB（高波動/下降趨勢股票）
# 專注於：科技巨頭、半導體龍頭、穩定成長股
# 注意：若需要自定義股票池，可在運行時覆蓋
STOCKS = DEFAULT_STOCKS


def check_data_status() -> tuple:
    """檢查數據狀態"""
    utc_today = datetime.now(timezone.utc).date()
    
    data_info = []
    for stock in STOCKS:
        file_path = DATA_DIR / f"{stock}.csv"
        if file_path.exists():
            try:
                df = pd.read_csv(file_path, index_col=0, parse_dates=True)
                if not df.empty:
                    last_date = df.index[-1].date()
                    age = (utc_today - last_date).days
                    data_info.append((stock, last_date, age))
            except:
                data_info.append((stock, None, -1))
        else:
            data_info.append((stock, None, -1))
    
    return data_info


def main():
    """主函數"""
    print("=" * 60)
    print("           TradeMaster v2 - 每日信號推送")
    print(f"           {datetime.now()}")
    print("=" * 60)
    
    # 1. 檢查數據
    print("\n1️⃣ 檢查數據狀態...")
    data_info = check_data_status()
    
    # 找出最舊的數據日期
    valid_dates = [d for d in data_info if d[1] is not None]
    if valid_dates:
        oldest = min(valid_dates, key=lambda x: x[1])
        newest = max(valid_dates, key=lambda x: x[1])
        print(f"   數據範圍: {oldest[1]} ~ {newest[1]}")
        print(f"   ({newest[0]} 最新, {oldest[0]} 最舊)")
    
    # 2. 生成信號
    print("\n2️⃣ 生成信號...")
    result = subprocess.run(
        ["python3", "signal_local.py"],
        cwd=str(Path(__file__).parent),
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ 生成信號失敗")
        return False
    
    print("✅ 信號生成完成")
    
    # 3. 讀取信號（從 DB 優先）
    print("\n3️⃣ 讀取信號...")
    
    import pymysql
    DB_CONFIG = {
        "host": "localhost",
        "port": 3306,
        "user": "alita",
        "password": "alitamysql",
        "database": "trademaster",
        "charset": "utf8mb4",
    }
    
    # 嘗試從 DB 讀取
    all_signals = {}
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, signal_type, price, quantity, confidence, created_at
                FROM signals
                WHERE status = 'pending'
                ORDER BY created_at DESC
            """)
            for row in cur.fetchall():
                symbol, signal_type, price, quantity, confidence, created_at = row
                all_signals[symbol] = {
                    'signal': signal_type,
                    'price': float(price) if price else 0,
                    'quantity': quantity,
                    'confidence': float(confidence) if confidence else 0
                }
        conn.close()
        
        if all_signals:
            print(f"   從 DB 讀取 {len(all_signals)} 筆 pending 信號")
    except Exception as e:
        print(f"   ⚠️ DB 讀取失敗: {e}")
        # fallback to JSON
        signals_file = Path(__file__).parent / "signals" / "latest_signals.json"
        if signals_file.exists():
            with open(signals_file, 'r') as f:
                signals = json.load(f)
                all_signals = signals.get('signals', {})
            print(f"   從 JSON 讀取 {len(all_signals)} 筆信號")
        else:
            print(f"❌ 信號文件不存在")
            return False
    
    # 4. 讀取 PENDING 信號並更新為 SENT
    pending_signals = {}
    try:
        import pymysql
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # 讀取 PENDING 信號
            cur.execute("""
                SELECT symbol, signal_type, price, quantity, confidence
                FROM signals
                WHERE status = 'PENDING'
                AND created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
            """)
            for row in cur.fetchall():
                symbol, signal_type, price, quantity, confidence = row
                pending_signals[symbol] = {
                    'signal': signal_type,
                    'price': float(price) if price else 0,
                    'quantity': quantity,
                    'confidence': float(confidence) if confidence else 0
                }
            
            # 更新狀態為 SENT
            if pending_signals:
                cur.execute("""
                    UPDATE signals 
                    SET status = 'SENT', sent_at = NOW()
                    WHERE status = 'PENDING'
                    AND created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
                """)
                conn.commit()
                print(f"   ✅ 已更新 {len(pending_signals)} 筆信號為 SENT")
        
        conn.close()
        
        if pending_signals:
            print(f"   📥 找到 {len(pending_signals)} 筆 PENDING 信號")
    except Exception as e:
        print(f"   ⚠️ DB 操作失敗: {e}")
        pending_signals = {}
    
    # 5. 分類 (使用 DB 數據)
    long_list = [s for s, d in all_signals.items() if d.get('signal') == 'LONG']
    short_list = [s for s, d in all_signals.items() if d.get('signal') == 'SHORT']
    
    # 5. 生成消息（台北時間）
    taipei_time = datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")
    
    # 檢查數據是否過期
    warning = ""
    if valid_dates:
        newest = max(valid_dates, key=lambda x: x[1])
        if newest[2] > 1:
            warning = f"⚠️ 數據可能過期 (最新: {newest[1]})"
    
    message = f"📈 **每日交易信號**\n"
    message += f"⏰ {taipei_time} (台北)\n"
    if warning:
        message += f"{warning}\n"
    message += "\n"
    
    message += f"🟢 **LONG** ({len(long_list)}檔):\n"
    if long_list:
        message += ", ".join(sorted(long_list)) + "\n"
    else:
        message += "無\n"
    
    message += f"\n🔴 **SHORT** ({len(short_list)}檔):\n"
    if short_list:
        message += ", ".join(sorted(short_list)) + "\n"
    else:
        message += "無\n"
    
    message += f"\n📈 **市場情緒**: {overview.get('market_sentiment', 'N/A')}\n"
    
    # 6. 保存消息
    msg_file = Path(__file__).parent / "signals" / "telegram_message.txt"
    with open(msg_file, 'w') as f:
        f.write(message)
    
    print("✅ 消息已保存")
    print(f"\n📱 消息內容:\n{message}")
    
    return True


if __name__ == "__main__":
    main()
