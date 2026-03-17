#!/usr/bin/env python3
"""
Futu Order Watcher - 富途訂單狀態推送監聽
用 TradeOrderHandlerBase 即時接收訂單狀態更新，
比每分鐘輪詢更即時可靠。

Usage:
    python3 scripts/futu_order_watcher.py

會持續運行，收到訂單狀態推送時自動更新本地 paper_orders。
"""
import sys
import os
import time
import signal

# 加入項目根目錄到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import futu
from futu import (
    OpenUSTradeContext, TradeOrderHandlerBase, TrdEnv, RET_OK
)

FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111
TRD_ENV = TrdEnv.SIMULATE

running = True

def signal_handler(sig, frame):
    global running
    print("\n🛑 收到停止信號，關閉中...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class OrderUpdateHandler(TradeOrderHandlerBase):
    """處理富途訂單狀態推送"""
    
    def on_recv_rsp(self, rsp_pb):
        """收到訂單更新推送"""
        ret, data = super().on_recv_rsp(rsp_pb)
        if ret != RET_OK:
            print(f"⚠️ 訂單推送解析失敗: {data}")
            return ret, data
        
        if data is None or len(data) == 0:
            return ret, data
        
        for _, row in data.iterrows():
            try:
                order_id = str(row.get('order_id', ''))
                code = row.get('code', '')
                status = str(row.get('order_status', ''))
                trd_side = str(row.get('trd_side', ''))
                dealt_qty = int(float(row.get('dealt_qty', 0) or 0))
                dealt_avg_price = float(row.get('dealt_avg_price', 0) or 0)
                
                print(f"📨 訂單推送: {code} {trd_side} | status={status} | dealt={dealt_qty} @ ${dealt_avg_price:.2f} | futu_id={order_id}")
                
                # 只處理有意義的狀態變更
                if 'FILLED' in status or 'CANCELLED' in status or 'FAILED' in status:
                    self._update_local_order(order_id, code, trd_side, status, dealt_qty, dealt_avg_price)
                    
            except Exception as e:
                print(f"❌ 處理訂單推送異常: {e}")
        
        return ret, data
    
    def _update_local_order(self, futu_order_id, code, trd_side, futu_status, dealt_qty, dealt_price):
        """更新本地訂單狀態"""
        try:
            from config.database import get_db_cursor
            from paper_trading import update_order_status
            
            # 轉換狀態
            if 'FILLED_ALL' in futu_status:
                local_status = 'filled'
            elif 'FILLED_PART' in futu_status:
                local_status = 'partial'
            elif 'CANCELLED' in futu_status:
                local_status = 'cancelled'
            elif 'FAILED' in futu_status or 'REJECT' in futu_status:
                local_status = 'failed'
            else:
                return
            
            # 找本地訂單
            with get_db_cursor() as c:
                c.execute("SELECT id, status, order_type FROM paper_orders WHERE futu_order_id = %s", (futu_order_id,))
                order = c.fetchone()
            
            if not order:
                print(f"  ⚠️ 本地找不到 futu_order_id={futu_order_id}，跳過")
                return
            
            if order['status'] == local_status:
                print(f"  ℹ️ 訂單 {order['id']} 狀態已是 {local_status}，跳過")
                return
            
            # 更新狀態
            update_order_status(order['id'], local_status, dealt_qty, dealt_price)
            print(f"  ✅ 更新訂單 {order['id']} ({code}): {order['status']} → {local_status}")
            
            # 如果成交，觸發持倉更新
            if local_status in ('filled', 'partial') and dealt_qty > 0:
                from paper_trading import handle_buy_fill, handle_sell_fill
                if order['order_type'] == 'BUY':
                    handle_buy_fill(order['id'])
                    print(f"  ✅ 觸發 BUY fill 處理: 訂單 {order['id']}")
                elif order['order_type'] == 'SELL':
                    handle_sell_fill(order['id'])
                    print(f"  ✅ 觸發 SELL fill 處理: 訂單 {order['id']}")
                    
        except Exception as e:
            print(f"  ❌ 更新本地訂單失敗: {e}")


def main():
    global running
    
    print("=" * 50)
    print("  Futu Order Watcher - 訂單狀態即時推送")
    print("=" * 50)
    print(f"  Host: {FUTU_HOST}:{FUTU_PORT}")
    print(f"  Env: SIMULATE")
    print()
    
    ctx = None
    try:
        ctx = OpenUSTradeContext(host=FUTU_HOST, port=FUTU_PORT)
        handler = OrderUpdateHandler()
        ctx.set_handler(handler)
        
        # 訂閱訂單推送
        print("✅ 已連接富途，正在監聽訂單推送...")
        print("   按 Ctrl+C 停止\n")
        
        while running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 手動停止")
    except Exception as e:
        print(f"❌ 連接失敗: {e}")
    finally:
        if ctx:
            ctx.close()
            print("✅ 已斷開富途連接")


if __name__ == '__main__':
    main()
