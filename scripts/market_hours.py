#!/usr/bin/env python3
"""
美股交易時間判斷工具
自動處理冬令時/夏令時 (DST)
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

# 時區定義
TZ_TAIWAN = ZoneInfo('Asia/Taipei')
TZ_US_EASTERN = ZoneInfo('America/New_York')

# 美股交易時間 (Eastern Time)
MARKET_OPEN = time(9, 30)   # 9:30 AM ET
MARKET_CLOSE = time(16, 0)  # 4:00 PM ET

# 盤前盤後
PRE_MARKET_OPEN = time(4, 0)    # 4:00 AM ET
AFTER_HOURS_CLOSE = time(20, 0)  # 8:00 PM ET


def is_dst_us() -> bool:
    """
    判斷美國東部是否為夏令時
    
    Returns:
        bool: True = 夏令時 (EDT, UTC-4), False = 冬令時 (EST, UTC-5)
    """
    now_et = datetime.now(TZ_US_EASTERN)
    # 如果 dst() 返回非零值，表示當前是夏令時
    return now_et.dst().total_seconds() > 0


def get_market_hours_taiwan() -> dict:
    """
    獲取美股交易時間 (以台灣時間表示)
    
    Returns:
        dict: {
            'pre_market_open': time,  # 盤前開始 (台灣時間)
            'market_open': time,       # 正式開盤 (台灣時間)
            'market_close': time,      # 收盤 (台灣時間)
            'after_hours_close': time, # 盤後結束 (台灣時間)
            'is_dst': bool,            # 是否夏令時
            'offset_hours': int        # 台灣與美東時差
        }
    """
    is_dst = is_dst_us()
    
    # 時差計算：台灣 UTC+8，美東 UTC-5 (冬) / UTC-4 (夏)
    # 台灣比美東快 13 小時 (冬) / 12 小時 (夏)
    offset_hours = 12 if is_dst else 13
    
    def et_to_taiwan(et_time: time) -> time:
        """將美東時間轉換為台灣時間"""
        hour = (et_time.hour + offset_hours) % 24
        return time(hour, et_time.minute)
    
    return {
        'pre_market_open': et_to_taiwan(PRE_MARKET_OPEN),
        'market_open': et_to_taiwan(MARKET_OPEN),
        'market_close': et_to_taiwan(MARKET_CLOSE),
        'after_hours_close': et_to_taiwan(AFTER_HOURS_CLOSE),
        'is_dst': is_dst,
        'offset_hours': offset_hours
    }


def is_market_open() -> bool:
    """
    判斷美股是否正在交易 (正式交易時段)
    
    Returns:
        bool: True = 正在交易
    """
    now_et = datetime.now(TZ_US_EASTERN)
    current_time = now_et.time()
    weekday = now_et.weekday()  # 0=Monday, 6=Sunday
    
    # 週末不開盤
    if weekday >= 5:  # Saturday or Sunday
        return False
    
    # 檢查是否在交易時間內
    return MARKET_OPEN <= current_time <= MARKET_CLOSE


def is_extended_hours() -> bool:
    """
    判斷是否在盤前或盤後時段
    
    Returns:
        bool: True = 盤前或盤後
    """
    now_et = datetime.now(TZ_US_EASTERN)
    current_time = now_et.time()
    weekday = now_et.weekday()
    
    # 週末不開盤
    if weekday >= 5:
        return False
    
    # 盤前: 4:00 AM - 9:30 AM
    pre_market = PRE_MARKET_OPEN <= current_time < MARKET_OPEN
    # 盤後: 4:00 PM - 8:00 PM
    after_hours = MARKET_CLOSE < current_time <= AFTER_HOURS_CLOSE
    
    return pre_market or after_hours


def should_update_kline() -> bool:
    """
    判斷是否應該更新 K 線數據
    (交易時段 + 盤前盤後都應更新)
    
    Returns:
        bool: True = 應該更新
    """
    return is_market_open() or is_extended_hours()


def get_cron_schedule() -> dict:
    """
    根據當前是否夏令時，返回建議的 Cron 時間
    
    Returns:
        dict: {
            'evening_start': int,  # 晚間開始時間 (台灣時間)
            'evening_end': int,    # 晚間結束時間 (台灣時間)
            'morning_start': int,  # 凌晨開始時間 (台灣時間)
            'morning_end': int,    # 凌晨結束時間 (台灣時間)
        }
    """
    is_dst = is_dst_us()
    
    if is_dst:
        # 夏令時：美股 9:30 AM ET = 台灣 21:30
        return {
            'evening_start': 21,
            'evening_end': 23,
            'morning_start': 0,
            'morning_end': 4,
            'note': '夏令時 (EDT)'
        }
    else:
        # 冬令時：美股 9:30 AM ET = 台灣 22:30
        return {
            'evening_start': 22,
            'evening_end': 23,
            'morning_start': 0,
            'morning_end': 5,
            'note': '冬令時 (EST)'
        }


def print_status():
    """打印當前市場狀態"""
    print("=" * 50)
    print("📊 美股市場狀態")
    print("=" * 50)
    
    is_dst = is_dst_us()
    hours = get_market_hours_taiwan()
    
    print(f"🕐 當前模式: {'夏令時 (EDT)' if is_dst else '冬令時 (EST)'}")
    print(f"⏰ 時差: 台灣比美東快 {hours['offset_hours']} 小時")
    print()
    print("📅 美股交易時間 (台灣時間):")
    print(f"   盤前開始: {hours['pre_market_open'].strftime('%H:%M')}")
    print(f"   正式開盤: {hours['market_open'].strftime('%H:%M')}")
    print(f"   正式收盤: {hours['market_close'].strftime('%H:%M')}")
    print(f"   盤後結束: {hours['after_hours_close'].strftime('%H:%M')}")
    print()
    print(f"🔔 市場狀態: {'開盤中' if is_market_open() else '休市'}")
    print(f"📈 盤前/盤後: {'是' if is_extended_hours() else '否'}")
    print(f"🔄 應該更新K線: {'是' if should_update_kline() else '否'}")
    print("=" * 50)


if __name__ == '__main__':
    print_status()
