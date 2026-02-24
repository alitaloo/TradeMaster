#!/usr/bin/env python3
"""
Cron Wrapper - 模擬交易訂單處理
由 OpenClow cron 每分鐘調用
1. 讀取 PENDING 信號 -> 下單到富途
2. 輪詢訂單狀態 -> 更新持倉
"""

import sys
import os

# 添加項目路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.process_pending_signals import poll_paper_orders, process_pending_signals

if __name__ == '__main__':
    print("=" * 60)
    print("📡 模擬交易信號處理...")
    
    # 1. 處理 PENDING 信號（下單）
    print("\n[1/2] 讀取 PENDING 信號並下單...")
    result = process_pending_signals(dry_run=False)
    print(f"   結果: {result}")
    
    # 2. 輪詢訂單狀態
    print("\n[2/2] 輪詢訂單狀態...")
    poll_paper_orders(dry_run=False)
    
    print("\n✅ 模擬交易處理完成")
    print("=" * 60)
