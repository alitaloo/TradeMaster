#!/usr/bin/env python3
"""
Signal Consumption - 信號消費
將 PENDING 信號轉換為模擬訂單，同時輪詢訂單狀態
"""
import os
import sys
from typing import List, Dict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PaperOrder, SystemConfig
from config.database import get_db_cursor


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
    """獲取待處理的訂單"""
    with get_db_cursor() as cursor:
        cursor.execute("""
            SELECT * FROM paper_orders 
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """)
        return cursor.fetchall()


def update_order_status(order_id: int, status: str, filled_quantity: int = 0, filled_price: float = 0):
    """更新訂單狀態"""
    with get_db_cursor() as cursor:
        filled_at = datetime.now() if status == 'filled' else None
        
        cursor.execute("""
            UPDATE paper_orders 
            SET status = %s, filled_quantity = %s, filled_price = %s, filled_at = %s, updated_at = %s
            WHERE id = %s
        """, (status, filled_quantity, filled_price, filled_at, datetime.now(), order_id))
        print(f"✅ 更新訂單狀態: ID={order_id}, status={status}")


def handle_buy_fill(order: Dict):
    """處理買入成交"""
    symbol = order['symbol']
    quantity = order['filled_quantity']
    price = order['filled_price']
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM paper_positions WHERE symbol = %s", (symbol,))
        position = cursor.fetchone()
        
        if position:
            old_qty = position['quantity']
            old_cost = position['average_cost']
            new_qty = old_qty + quantity
            new_cost = (float(old_cost) * old_qty + price * quantity) / new_qty
            
            cursor.execute("""
                UPDATE paper_positions 
                SET quantity = %s, average_cost = %s, updated_at = %s
                WHERE symbol = %s
            """, (new_qty, new_cost, datetime.now(), symbol))
        else:
            cursor.execute("""
                INSERT INTO paper_positions 
                (symbol, quantity, average_cost, current_price, updated_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (symbol, quantity, price, price, datetime.now()))
        
        print(f"✅ 更新持倉: {symbol}")


def handle_sell_fill(order: Dict):
    """處理賣出成交"""
    symbol = order['symbol']
    quantity = order['filled_quantity']
    price = order['filled_price']
    
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM paper_positions WHERE symbol = %s", (symbol,))
        position = cursor.fetchone()
        
        if position:
            avg_cost = position['average_cost']
            realized_pnl = (price - avg_cost) * quantity
            new_qty = position['quantity'] - quantity
            
            if new_qty <= 0:
                cursor.execute("DELETE FROM paper_positions WHERE symbol = %s", (symbol,))
            else:
                old_realized = position.get('realized_pnl', 0) or 0
                cursor.execute("""
                    UPDATE paper_positions 
                    SET quantity = %s, realized_pnl = %s, updated_at = %s
                    WHERE symbol = %s
                """, (new_qty, old_realized + realized_pnl, datetime.now(), symbol))
        
        print(f"✅ 處理賣出: {symbol}")


def poll_orders():
    """輪詢訂單狀態"""
    import futu as ft
    
    orders = get_pending_orders()
    if not orders:
        print("📊 無待處理訂單")
        return
    
    print(f"📊 共 {len(orders)} 個待處理訂單")
    
    trade_ctx = ft.OpenUSTradeContext(host='127.0.0.1', port=11111)
    
    try:
        for order in orders:
            order_id = order['id']
            futu_order_id = order['futu_order_id']
            symbol = order['symbol']
            order_type = order['order_type']
            
            # 查詢富途訂單狀態
            ret, data = trade_ctx.order_list_query(
                order_id=futu_order_id,
                trd_env=ft.TrdEnv.SIMULATE
            )
            
            if ret != ft.RET_OK or data.empty:
                continue
            
            futu_status = data.iloc[0]['order_status']
            dealt_qty = int(data.iloc[0].get('dealt_qty', 0))
            dealt_price = float(data.iloc[0].get('dealt_avg_price', 0))
            
            if futu_status == ft.OrderStatus.FILLED_ALL:
                update_order_status(order_id, 'filled', dealt_qty, dealt_price)
                order['filled_quantity'] = dealt_qty
                order['filled_price'] = dealt_price
                
                if order_type == 'BUY':
                    handle_buy_fill(order)
                else:
                    handle_sell_fill(order)
                    
                print(f"✅ 訂單成交: {symbol}")
            elif futu_status == ft.OrderStatus.FILLED_PART:
                update_order_status(order_id, 'partial', dealt_qty, dealt_price)
                print(f"⏳ 部分成交: {symbol}")
            elif futu_status == ft.OrderStatus.CANCELLED_ALL:
                update_order_status(order_id, 'cancelled')
                print(f"❌ 訂單取消: {symbol}")
    
    finally:
        trade_ctx.close()


def process_pending_signals(paper_trading: bool = True, dry_run: bool = False) -> Dict:
    """
    處理 pending 信號，轉換為模擬訂單
    
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
    
    # 獲取 pending 信號
    signals = get_pending_signals()
    
    if not signals:
        return {
            'success': True,
            'message': '無 pending 信號',
            'processed': 0
        }
    
    processed = 0
    errors = []
    
    for signal in signals:
        try:
            if dry_run:
                print(f'[Dry Run] 模擬下單: {signal["symbol"]} {signal["order_type"]} {signal["quantity"]}')
                continue
            
            # 提交模擬訂單
            from paper_trading import submit_paper_order
            
            # 信號表用 signal_type，轉換為 order_type
            order_type = signal['signal_type']
            
            result = submit_paper_order(
                symbol=signal['symbol'],
                order_type=order_type,
                quantity=signal['quantity'],
                price=float(signal['price']) if signal['price'] else None,
                source_signal_id=signal['id']
            )
            
            if result.get('success'):
                # 更新信號狀態為 PROCESSING
                update_signal_status(signal['id'], 'PROCESSING')
                processed += 1
                print(f'✅ 信號 {signal["id"]} -> 訂單 {result["order_id"]}')
            else:
                errors.append(f'信號 {signal["id"]}: {result.get("error")}')
                
        except Exception as e:
            errors.append(f'信號 {signal["id"]}: {str(e)}')
    
    return {
        'success': True,
        'processed': processed,
        'total': len(signals),
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
    
    # 1. 處理 PENDING 信號（下單）
    if not args.poll_only:
        print("\n[1/2] 處理 PENDING 信號...")
        result = process_pending_signals(
            paper_trading=args.paper_trading,
            dry_run=args.dry_run
        )
        print(f'結果: {result}')
    
    # 2. 輪詢訂單狀態
    print("\n[2/2] 輪詢訂單狀態...")
    poll_orders()
    
    print("\n✅ 完成")
