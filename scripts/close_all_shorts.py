#!/usr/bin/env python3
"""
一次性腳本：平掉所有空頭持倉
Z 授權：2026-03-17 13:00
"""
import os
import sys

# 清除代理
for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy'):
    os.environ.pop(k, None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.database import get_db_cursor
from paper_trading import submit_paper_order
from paper_trading_portfolio import get_current_price


def main():
    # 查所有空頭持倉
    with get_db_cursor() as c:
        c.execute("SELECT symbol, quantity FROM paper_positions WHERE quantity < 0")
        shorts = c.fetchall()

    if not shorts:
        print("✅ 沒有空頭持倉，無需操作")
        return

    print(f"📊 找到 {len(shorts)} 個空頭持倉，開始平倉...\n")

    results = []
    for s in shorts:
        symbol = s['symbol']
        qty = abs(s['quantity'])
        
        # 取現價
        price = get_current_price(symbol)
        if not price:
            print(f"❌ {symbol}: 無法取得現價，跳過")
            results.append({'symbol': symbol, 'success': False, 'error': '無法取得現價'})
            continue

        print(f"🔄 {symbol}: 買入 {qty} 股 @ ${price:.2f} (平空頭)")
        
        result = submit_paper_order(
            symbol=symbol,
            order_type='BUY',
            quantity=qty,
            price=price,
            source_type='close_short'
        )
        
        if result.get('success'):
            print(f"  ✅ 下單成功: order_id={result['order_id']}, futu_id={result.get('futu_order_id')}")
        else:
            print(f"  ❌ 下單失敗: {result.get('error')}")
        
        results.append({'symbol': symbol, **result})

    print(f"\n{'='*40}")
    ok = sum(1 for r in results if r.get('success'))
    print(f"完成: {ok}/{len(results)} 筆下單成功")


if __name__ == '__main__':
    main()
