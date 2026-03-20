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
    OpenUSTradeContext, TradeOrderHandlerBase, TradeDealHandlerBase, TrdEnv, RET_OK
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


def sync_positions_from_futu():
    """共用：從富途同步持倉到本地 DB"""
    try:
        import subprocess
        script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'sync_positions_from_futu.py'
        )
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if result.returncode == 0:
            print(f"  ✅ 持倉已從富途同步")
        else:
            print(f"  ❌ 同步失敗: {result.stderr[-200:]}")
    except Exception as e:
        print(f"  ❌ 同步異常: {e}")


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
            
            # 如果成交，直接從 Futu sync 持倉（最可靠的 source of truth）
            if local_status in ('filled', 'partial') and dealt_qty > 0:
                print(f"  🔄 成交後同步持倉 (訂單 {order['id']} {code})...")
                sync_positions_from_futu()
                    
        except Exception as e:
            print(f"  ❌ 更新本地訂單失敗: {e}")


class DealUpdateHandler(TradeDealHandlerBase):
    """處理富途成交即時推送 - 成交後直接從富途同步持倉"""
    
    def on_recv_rsp(self, rsp_pb):
        ret, data = super().on_recv_rsp(rsp_pb)
        if ret != RET_OK or data is None or len(data) == 0:
            return ret, data
        
        for _, row in data.iterrows():
            try:
                code = row.get('code', '')
                qty = int(float(row.get('qty', 0) or 0))
                price = float(row.get('price', 0) or 0)
                trd_side = str(row.get('trd_side', ''))
                order_id = str(row.get('order_id', ''))
                
                print(f"💰 成交推送: {code} {trd_side} {qty}股 @ ${price:.2f} | order_id={order_id}")
                
                # 成交後直接從富途同步持倉（用富途作 source of truth）
                sync_positions_from_futu()
                
            except Exception as e:
                print(f"❌ 處理成交推送異常: {e}")
        
        return ret, data
    
    # _sync_from_futu 已改為模組級共用函數 sync_positions_from_futu()


def main():
    global running
    
    RECONNECT_INTERVAL = 30  # 30 秒後重試
    
    print("=" * 50)
    print("  Futu Order Watcher - 訂單/成交即時推送")
    print("=" * 50)
    print(f"  Host: {FUTU_HOST}:{FUTU_PORT}")
    print(f"  Env: SIMULATE")
    print()
    
    while running:
        ctx = None
        try:
            ctx = OpenUSTradeContext(host=FUTU_HOST, port=FUTU_PORT)
            order_handler = OrderUpdateHandler()
            deal_handler = DealUpdateHandler()
            ctx.set_handler(order_handler)   # 訂單狀態推送
            ctx.set_handler(deal_handler)    # 成交即時推送
            
            print(f"✅ 已連接富途，正在監聽訂單/成交推送...")
            print("   按 Ctrl+C 停止\n")
            
            while running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 手動停止")
            break
        except Exception as e:
            print(f"❌ 連接失敗: {e}")
            if running:
                print(f"⏳ {RECONNECT_INTERVAL}秒後重試...")
                time.sleep(RECONNECT_INTERVAL)
        finally:
            if ctx:
                try:
                    ctx.close()
                except:
                    pass
    
    print("✅ 已停止 watcher")


if __name__ == '__main__':
    main()
