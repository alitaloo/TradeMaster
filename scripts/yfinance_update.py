#!/usr/bin/env python3
"""
[已廢棄] 使用 yfinance 獲取最新 K 線數據
2026-03-06: 此腳本已停用。yfinance / Yahoo Finance 依賴已全面移除。

替代方案：
  - 歷史 K線: scripts/backfill_futu_kline_mysql.py（富途 → MySQL）
  - 即時 K線: scripts/futu_polling.py（富途輪詢 → MySQL kline_cache）
"""

print("❌ 此腳本已廢棄。yfinance / Yahoo Finance 已於 2026-03-06 移除。")
print("請改用以下富途數據腳本：")
print("  - 歷史補充: python3 scripts/backfill_futu_kline_mysql.py")
print("  - 即時更新: python3 scripts/futu_polling.py")
