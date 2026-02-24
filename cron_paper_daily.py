#!/usr/bin/env python3
"""
Cron Job: Daily Paper Trading Push
每日結算推送到 Successor Bot
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_reports import push_paper_daily_summary, generate_paper_report
from models import SystemConfig
from datetime import datetime

def main():
    """主函數"""
    # 檢查是否啟用模擬交易
    if not SystemConfig.is_paper_trading():
        print("模擬交易未啟用，跳過")
        return
    
    print(f"[{datetime.now()}] 開始每日結算...")
    
    try:
        # 生成報告
        report_result = generate_paper_report()
        if report_result.get('success'):
            print(f"✅ 報告生成完成: {report_result['date']}")
            print(f"   總資產: ${report_result['summary']['total_value']:,.2f}")
        
        # 推送到 Successor Bot
        push_result = push_paper_daily_summary()
        if push_result.get('success'):
            print(f"✅ 推送完成")
            print(f"\n{push_result['message'][:200]}...")
        else:
            print(f"⚠️ 推送失敗: {push_result.get('error')}")
    
    except Exception as e:
        print(f"❌ 每日結算失敗: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
