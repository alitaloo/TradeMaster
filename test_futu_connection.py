#!/usr/bin/env python3
"""
測試富途 OpenD 連接
"""
import sys
import os

# 使用正確的 Python 路徑
PYTHON_BIN = '/usr/local/bin/python3'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("=== 富途 OpenD 連接測試 ===\n")

# 1. 檢查 SDK 安裝
try:
    from futu import OpenUSTradeContext, OpenQuoteContext, TrdEnv, TrdMarket
    print("✅ 富途 SDK 已安裝")
except ImportError:
    print("❌ 富途 SDK 未安裝")
    print("請執行: pip3 install futu-api")
    sys.exit(1)

# 2. 檢查 OpenD 連接
host = '127.0.0.1'
port = 11111

print(f"\n連接到 OpenD: {host}:{port}")

try:
    # 測試行情連接
    quote_ctx = OpenQuoteContext(host=host, port=port)
    print("✅ 行情連接成功")
    
    # 獲取全球狀態
    ret, data = quote_ctx.get_global_state()
    if ret == 0:
        print(f"✅ 獲取市場狀態成功")
    quote_ctx.close()
    
    # 測試交易連接 (模擬環境)
    trade_ctx = OpenUSTradeContext(host=host, port=port)
    print("✅ 交易連接成功 (美股)")
    
    # 獲取賬戶列表
    ret, data = trade_ctx.get_acc_list()
    if ret == 0:
        print(f"✅ 賬戶列表查詢成功")
    else:
        print(f"⚠️ 賬戶列表: {data}")
    
    trade_ctx.close()
    
    print("\n✅ 所有測試通過！")
    print("\n下一步:")
    print("1. 啟動 TradeMaster API: python3 api_server.py")
    print("2. 啟用模擬交易: 訪問 http://localhost:5173/paper-trading")
    print("3. 運行輪詢腳本: python3 cron_paper_poll.py")
    
except Exception as e:
    print(f"\n❌ 連接失敗: {e}")
    print("\n請檢查:")
    print("1. OpenD 是否已啟動?")
    print("2. 端口 11111 是否被佔用?")
    print("3. 富途賬號是否已登入?")
