import futu as ft
import sys

print("連接富途牛牛...")
quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)

print("請求歷史 K 線...")
result = quote_ctx.request_history_kline(
    "US.AAPL",
    start='2025-01-01',
    end='2025-01-05',
    ktype=ft.KLType.K_DAY,
    fields=['time', 'open', 'close', 'high', 'low', 'volume']
)

print(f"返回類型: {type(result)}")
print(f"返回長度: {len(result)}")
print(f"返回內容: {result}")

quote_ctx.close()
