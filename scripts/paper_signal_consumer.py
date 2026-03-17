#!/usr/bin/env python3
"""
Signal Consumption - 信號消費
將 PENDING 信號轉換為模擬訂單，同時輪詢訂單狀態
"""
import os
import sys
from decimal import Decimal
from typing import List, Dict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PaperOrder, SystemConfig
from config.database import get_db_cursor
from paper_position_reconciliation import reconcile_paper_positions, reconcile_single_filled_order
import socket


def is_futu_available() -> bool:
    """檢查富途 API 是否可用"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex(('127.0.0.1', 11111))
        sock.close()
        return result == 0
    except Exception:
        return False


def get_pending_signals(limit: int = 100) -> List[Dict]:
    """
    獲取 pending 信號

    Args:
        limit: 最多獲取數量

    Returns:
        list: 信號列表
    """
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM signals
            WHERE status = 'PENDING'
            ORDER BY created_at ASC
            LIMIT %s
        """, (limit,))
        return cursor.fetchall()


def update_signal_status(signal_id: int, status: str) -> bool:
    """
    更新信號狀態

    Args:
        signal_id: 信號 ID
        status: 新狀態

    Returns:
        bool: 是否成功
    """
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE signals SET status = %s, updated_at = NOW() WHERE id = %s
        """, (status, signal_id))
        return cursor.rowcount > 0


def get_pending_orders() -> List[Dict]:
    """獲取待輪詢訂單（pending / partial）。"""
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM paper_orders
            WHERE status IN ('pending', 'partial')
            ORDER BY created_at ASC
        """)
        return cursor.fetchall()


def update_order_status(order_id: int, status: str, filled_quantity: int = 0, filled_price: float = 0, filled_at=None):
    """更新訂單狀態"""
    with get_db_cursor() as cursor:
        effective_filled_at = filled_at or (datetime.now() if status in ('filled', 'partial') and filled_quantity > 0 else None)

        cursor.execute("""
            UPDATE paper_orders
            SET status = %s, filled_quantity = %s, filled_price = %s, filled_at = %s, updated_at = %s
            WHERE id = %s
        """, (status, filled_quantity, filled_price, effective_filled_at, datetime.now(), order_id))
        print(f"✅ 更新訂單狀態: ID={order_id}, status={status}")


def handle_buy_fill(order: Dict):
    """處理買入成交：統一改用 paper_orders 重建持倉。"""
    result = reconcile_single_filled_order(order['id'], apply=True)
    if not result.get('success'):
        print(f"❌ 處理買入失敗: order_id={order['id']}, result={result}")
    else:
        print(f"✅ 更新持倉: {order['symbol']}")


def handle_sell_fill(order: Dict):
    """處理賣出成交：統一改用 paper_orders 重建持倉。"""
    result = reconcile_single_filled_order(order['id'], apply=True)
    if not result.get('success'):
        print(f"❌ 處理賣出失敗: order_id={order['id']}, result={result}")
    else:
        print(f"✅ 處理賣出: {order['symbol']}")


def poll_orders():
    """輪詢訂單狀態"""
    # 🔧 修復：檢查已成交但信號未更新的情況
    with get_db_cursor() as cursor:
        cursor.execute("""
            UPDATE signals s
            SET s.status = 'FILLED', s.updated_at = NOW()
            WHERE s.status != 'FILLED'
            AND EXISTS (
                SELECT 1 FROM paper_orders o
                WHERE o.source_signal_id = s.id
                AND o.status = 'filled'
            )
        """)
        if cursor.rowcount > 0:
            print(f"🔧 修復: {cursor.rowcount} 個信號狀態已更新")

    try:
        from futu.quote.open_quote_context import OpenQuoteContext
        from futu.trade.open_trade_context import OpenUSTradeContext
        from futu.common.constant import OrderStatus
        ft = type('FT', (), {
            'OpenQuoteContext': OpenQuoteContext,
            'OpenUSTradeContext': OpenUSTradeContext,
            'OrderStatus': OrderStatus,
            'TrdEnv': type('TrdEnv', (), {'SIMULATE': 'SIMULATE'})(),
            'RET_OK': 0,
            'OrderType': type('OrderType', (), {'NORMAL': 'NORMAL'})()
        })()
    except ImportError:
        ft = None
    import socket

    orders = get_pending_orders()
    if not orders:
        print("📊 無待處理訂單")
        return

    # 檢查 Futu API 是否可用
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        result = sock.connect_ex(('127.0.0.1', 11111))
        sock.close()
        if result != 0:
            print("⚠️  富途 API 未連接，跳過訂單輪詢")
            return
    except Exception:
        print("⚠️  富途 API 未連接，跳過訂單輪詢")
        return

    print(f"📊 共 {len(orders)} 個待輪詢訂單 (pending/partial)")

    trade_ctx = ft.OpenUSTradeContext(host='127.0.0.1', port=11111)

    try:
        for order in orders:
            order_id = order['id']
            futu_order_id = order['futu_order_id']
            symbol = order['symbol']
            order_type = order['order_type']

            # 檢查訂單是否超時 (5分鐘)
            created_at = order.get('created_at')
            if created_at:
                if isinstance(created_at, str):
                    created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                age = datetime.now() - created_at
                if age > timedelta(minutes=5):
                    # 超時，嘗試從富途取消訂單
                    print(f"⏰ 訂單超時 {symbol} (age: {age.seconds//60}分鐘)，嘗試取消...")
                    try:
                        # 嘗試調用富途 API 取消訂單
                        ret_cancel, data_cancel = trade_ctx.modify_order(
                            order_id=futu_order_id,
                            new_price=0,
                            new_qty=0,
                            trd_env=ft.TrdEnv.SIMULATE
                        )
                        
                        if ret_cancel == 0:
                            print(f"✅ 富途取消訂單成功: {symbol}")
                        else:
                            print(f"⚠️ 富途取消訂單失敗: {data_cancel}")
                        
                        # 無論富途 API 是否成功，都標記本地訂單為 expired
                        update_order_status(order_id, 'expired')
                        if order.get('source_signal_id'):
                            update_signal_status(order['source_signal_id'], 'PROCESSED')
                        print(f"✅ 訂單已標記為過期: {symbol}")
                    except Exception as e:
                        print(f"❌ 取消訂單異常: {e}")
                        # 即使異常也標記為過期
                        try:
                            update_order_status(order_id, 'expired')
                            if order.get('source_signal_id'):
                                update_signal_status(order['source_signal_id'], 'PROCESSED')
                        except:
                            pass
                    continue

            # 查詢富途訂單狀態
            ret, data = trade_ctx.order_list_query(
                order_id=futu_order_id,
                trd_env=ft.TrdEnv.SIMULATE
            )

            if ret != ft.RET_OK or data.empty:
                print(f"⚠️ 查詢訂單失敗: {symbol}, ret={ret}, data={data}")
                continue

            futu_status = data.iloc[0]['order_status']
            dealt_qty = int(data.iloc[0].get('dealt_qty', 0) or 0)
            dealt_price = float(data.iloc[0].get('dealt_avg_price', 0) or 0)
            filled_at = data.iloc[0].get('updated_time') or data.iloc[0].get('create_time')

            print(f"🔍 訂單狀態: {symbol}, futu_status={futu_status}, dealt_qty={dealt_qty}")

            if futu_status == ft.OrderStatus.FILLED_ALL:
                update_order_status(order_id, 'filled', dealt_qty, dealt_price, filled_at)
                order['filled_quantity'] = dealt_qty
                order['filled_price'] = dealt_price

                if order_type == 'BUY':
                    handle_buy_fill(order)
                else:
                    handle_sell_fill(order)

                # 更新对应信号为 FILLED
                if order.get('source_signal_id'):
                    update_signal_status(order['source_signal_id'], 'FILLED')

                print(f"✅ 訂單成交: {symbol}")
            elif futu_status == ft.OrderStatus.FILLED_PART:
                update_order_status(order_id, 'partial', dealt_qty, dealt_price, filled_at)
                # 部分成交也要觸發持倉更新（用已成交數量）
                order['filled_quantity'] = dealt_qty
                order['filled_price'] = dealt_price
                if order_type == 'BUY':
                    handle_buy_fill(order)
                else:
                    handle_sell_fill(order)
                print(f"⏳ 部分成交: {symbol} {dealt_qty}股 @${dealt_price:.2f}")
            elif futu_status == ft.OrderStatus.CANCELLED_ALL:
                update_order_status(order_id, 'cancelled', dealt_qty, dealt_price, filled_at)
                print(f"❌ 訂單取消: {symbol}")
            elif 'FAILED' in str(futu_status) or 'REJECT' in str(futu_status):
                update_order_status(order_id, 'failed', dealt_qty, dealt_price, filled_at)
                print(f"❌ 訂單失敗: {symbol}, status={futu_status}")
            else:
                update_order_status(order_id, 'partial' if dealt_qty > 0 else 'pending', dealt_qty, dealt_price, filled_at)
                print(f"⏳ 訂單待成交: {symbol}, status={futu_status}, dealt_qty={dealt_qty}")

    finally:
        trade_ctx.close()
        # 自癒：每次輪詢完成後都用 filled orders 對帳一次本地持倉。
        # 使用 quick_check 模式，只有在新 filled 訂單時才全量重建
        reconcile_paper_positions(apply=True, quick_check=True)


def cleanup_stale_signals(hours: int = 24) -> Dict:
    """
    清理过期的 PENDING 信号（没有生成订单的）

    Args:
        hours: 超过多少小时没处理的信号算是过期

    Returns:
        dict: 清理结果
    """
    from config.database import get_db_cursor

    with get_db_cursor() as cursor:
        # 找出超过 hours 小时的 PENDING 信号（没有生成订单的）
        cursor.execute("""
            SELECT s.id, s.symbol, s.signal_type, s.created_at
            FROM signals s
            LEFT JOIN paper_orders o ON o.source_signal_id = s.id
            WHERE s.status = 'PENDING'
              AND o.id IS NULL
              AND s.created_at < NOW() - INTERVAL %s HOUR
        """, (hours,))

        stale_signals = cursor.fetchall()

        if not stale_signals:
            return {'success': True, 'message': '没有过期的信号', 'cleaned': 0}

        # 标记这些信号为超时 (EXPIRED)
        signal_ids = [s['id'] for s in stale_signals]
        placeholders = ','.join(['%s'] * len(signal_ids))

        cursor.execute(f"""
            UPDATE signals
            SET status = 'EXPIRED', updated_at = NOW()
            WHERE id IN ({placeholders})
        """, signal_ids)

        return {
            'success': True,
            'message': f'清理 {len(signal_ids)} 个过期信号',
            'cleaned': len(signal_ids),
            'signals': [(s['symbol'], s['signal_type'], str(s['created_at'])) for s in stale_signals]
        }


def process_pending_signals(paper_trading: bool = True, dry_run: bool = False) -> Dict:
    """
    處理 pending 信號，轉換為模擬訂單
    
    風控檢查：
    1. 下單前檢查可用現金
    2. 計算訂單金額 = price × quantity
    3. 如果金額 > 可用現金的 90%，按可用現金的 90% 重算 quantity
    4. 如果重算後 quantity < 1，跳過這個信號並記 warning
    5. BUY 時做風控檢查
    
    Args:
        paper_trading: 是否使用模擬交易
        dry_run: 是否模擬運行
    
    Returns:
        dict: 處理結果
    """
    if not paper_trading:
        return {
            'success': False,
            'message': '模擬交易未啟用'
        }
    
    if not SystemConfig.is_paper_trading():
        return {
            'success': False,
            'message': '系統配置: 模擬交易未啟用'
        }
    
    # 檢查富途 API 是否可用
    if not is_futu_available():
        return {
            'success': False,
            'message': '富途 API 未連接，無法處理信號'
        }

    # 獲取 pending 信號
    signals = get_pending_signals()
    
    if not signals:
        return {
            'success': True,
            'message': '無 pending 信號',
            'processed': 0
        }
    
    # 導入必要的模組
    from paper_trading_portfolio import get_paper_balance
    
    # 獲取可用現金
    available_cash = get_paper_balance()
    
    # 嘗試導入風控模組
    try:
        from core.risk_engine import check_signal_risk
        has_risk_engine = True
    except ImportError:
        has_risk_engine = False
        print("⚠️ 風控模組不可用，跳過風控檢查")
    
    processed = 0
    skipped = []
    errors = []
    
    for signal in signals:
        try:
            # 獲取信號參數
            symbol = signal['symbol']
            order_type = signal['signal_type']
            quantity = int(signal['quantity'])
            price = float(signal['price']) if signal['price'] else None
            
            if dry_run:
                print(f'[Dry Run] 模擬下單: {symbol} {order_type} {quantity}')
                continue
            
            # === 風控檢查：現金數量計算 ===
            
            # 如果沒有價格，嘗試獲取現價
            if price is None:
                from paper_trading_portfolio import get_current_price
                price = get_current_price(symbol)
                if price is None:
                    print(f"⚠️ 無法獲取 {symbol} 價格，跳過信號 {signal['id']}")
                    update_signal_status(signal['id'], 'FAIL')
                    errors.append(f'信號 {signal["id"]}: 無法獲取價格')
                    continue
            
            # 計算訂單金額
            order_amount = price * quantity
            
            # 現金檢查：如果是 BUY 類型
            if order_type.upper() == 'BUY':
                # 計算最大可用金額（現金的 90%）
                max_amount = available_cash * 0.9
                
                # 如果訂單金額超過可用金額的 90%，重算數量
                if order_amount > max_amount:
                    new_quantity = int(max_amount / price)
                    if new_quantity < 1:
                        # 金額太小，無法購買至少 1 股
                        print(f"⚠️ 現金不足，跳過信號 {signal['id']}: {symbol} {order_type} {quantity} @ ${price}")
                        update_signal_status(signal['id'], 'SKIPPED')
                        skipped.append(f'信號 {signal["id"]}: 現金不足 (需要 ${order_amount:.2f}, 可用 ${available_cash:.2f})')
                        continue
                    else:
                        print(f"⚠️ 數量調整: {symbol} {order_type} {quantity} -> {new_quantity} (金額 ${order_amount:.2f} > 90%可用 ${max_amount:.2f})")
                        quantity = new_quantity
                        order_amount = price * quantity
            
            # === 風控檢查：check_signal_risk ===
            if order_type.upper() == 'BUY' and has_risk_engine:
                try:
                    risk_check = check_signal_risk(
                        symbol=symbol,
                        signal_type=order_type,
                        quantity=quantity,
                        price=price
                    )
                    if not risk_check.get('approved', True):
                        reason = risk_check.get('reason', '風控不通過')
                        print(f"⚠️ 風控不通過，跳過信號 {signal['id']}: {symbol} {order_type} - {reason}")
                        update_signal_status(signal['id'], 'SKIPPED')
                        skipped.append(f'信號 {signal["id"]}: 風控不通過 - {reason}')
                        continue
                except Exception as e:
                    print(f"⚠️ 風控檢查異常: {e}，繼續下單")
            
            # 提交模擬訂單
            from paper_trading import submit_paper_order
            
            result = submit_paper_order(
                symbol=symbol,
                order_type=order_type,
                quantity=quantity,
                price=price,
                source_signal_id=signal['id'],
                source_type='signal'
            )
            
            if result.get('success') and result.get('order_id'):
                # 成功创建订单 → PROCESSING
                update_signal_status(signal['id'], 'PROCESSING')
                processed += 1
                print(f'✅ 信號 {signal["id"]} -> 訂單 {result["order_id"]} ({symbol} {order_type} {quantity} @ ${price})')
            else:
                # API 失败，标记为 FAIL
                update_signal_status(signal['id'], 'FAIL')
                errors.append(f'信號 {signal["id"]}: {result.get("error")}')
                
        except Exception as e:
            # 异常处理，标记为 FAIL
            update_signal_status(signal['id'], 'FAIL')
            errors.append(f'信號 {signal["id"]}: {str(e)}')
    
    return {
        'success': True,
        'processed': processed,
        'total': len(signals),
        'skipped': skipped,
        'errors': errors
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='信號消費 + 訂單輪詢')
    parser.add_argument('--dry-run', action='store_true', help='模擬運行')
    parser.add_argument('--paper-trading', action='store_true', default=True, help='模擬交易模式')
    parser.add_argument('--poll-only', action='store_true', help='只輪詢訂單，不處理信號')
    args = parser.parse_args()

    # 確保啟用模擬交易
    SystemConfig.set('paper_trading_enabled', 'true')

    # 0. 清理过期的 PENDING 信号
    print("\n[0/3] 清理过期信号...")
    cleanup_result = cleanup_stale_signals(hours=24)
    print(f"清理结果: {cleanup_result}")

    # 1. 處理 PENDING 信號（下單）
    if not args.poll_only:
        print("\n[1/3] 處理 PENDING 信號...")
        result = process_pending_signals(
            paper_trading=args.paper_trading,
            dry_run=args.dry_run
        )
        print(f'結果: {result}')

    # 2. 輪詢訂單狀態
    print("\n[2/3] 輪詢訂單狀態...")
    poll_orders()

    print("\n✅ 完成")
