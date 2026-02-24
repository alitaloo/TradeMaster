import futu as ft

# 測試 API 返回格式
quote_ctx = ft.OpenQuoteContext(host='127.0.0.1', port=11111)
ret, data = quote_ctx.request_history_kline(
    "US.AAPL",
    start='2025-01-01',
    end='2025-01-10',
    ktype=ft.KLType.K_DAY,
    fields=['time', 'open', 'close', 'high', 'low', 'volume']
)

print(f"ret type: {type(ret)}")
print(f"ret value: {ret}")
print(f"data type: {type(data)}")
print(f"data: {data}")

quote_ctx.close()
