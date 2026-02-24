#!/usr/bin/env python3
"""
Cron Job: Paper Order Polling
每分鐘輪詢訂單狀態
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_trading import poll_paper_orders
from models import SystemConfig

def main():
    """主函數"""
    # 檢查是否啟用模擬交易
    if not SystemConfig.is_paper_trading():
        print("模擬交易未啟用，跳過")
        return
    
    print(f"[{datetime.now()}] 開始輪詢訂單...")
    
    try:
        results = poll_paper_orders()
        print(f"輪詢完成: {len(results)} 筆訂單處理")
        
        for result in results:
            if 'error' in result:
                print(f"  ❌ 訂單 {result.get('order_id')}: {result['error']}")
            else:
                print(f"  ✅ 訂單 {result.get('order_id')}: {result.get('status')}")
    
    except Exception as e:
        print(f"❌ 輪詢失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    from datetime import datetime
    main()
