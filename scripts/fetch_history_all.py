#!/usr/bin/env python3
"""
[已廢棄] 使用 yfinance 獲取所有股票的歷史 K 線數據
2026-03-06: 此腳本已停用。yfinance / Yahoo Finance 依賴已全面移除。

替代方案：
  - 歷史 K線 (MySQL): scripts/backfill_futu_kline_mysql.py（富途 → MySQL）
  - 多週期 K線: scripts/fetch_futu_5intervals.py（富途 → MySQL）
"""

print("❌ 此腳本已廢棄。yfinance / Yahoo Finance 已於 2026-03-06 移除。")
print("請改用以下富途數據腳本：")
print("  - 歷史補充 (MySQL): python3 scripts/backfill_futu_kline_mysql.py")
print("  - 多週期數據: python3 scripts/fetch_futu_5intervals.py")
