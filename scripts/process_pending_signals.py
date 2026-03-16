#!/usr/bin/env python3
"""
模擬交易信號消費與自動下單模組 (Phase 4)
從 signals 表讀取 PENDING 信號，呼叫富途 API 下單，輪詢訂單狀態並更新持倉

用法:
    python process_pending_signals.py [--dry-run] [--poll-only]
"""

import futu as ft
import pymysql
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
import argparse
import time
from functools import wraps

from paper_position_reconciliation import reconcile_paper_positions, reconcile_single_filled_order

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 富途配置
FUTU_HOST = '127.0.0.1'
FUTU_PORT = 11111

# 數據庫配置
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config.database import PYMYSQL_CONFIG as DB_CONFIG
except ImportError:
    DB_CONFIG = {
        'host': 'localhost',
        'user': 'alita',
        'password': 'alitamysql',
        'database': 'trademaster',
        'charset': 'utf8mb4'
    }


# ==================== 重試機制 ====================
def retry_api(max_retries: int = 3, delay: float = 1, backoff: float = 2):
    """API 重試裝飾器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = delay * (backoff ** attempt)
                        logger.warning(
                            f"API 異常 (attempt {attempt + 1}/{max_retries}), "
                            f"等待 {wait_time:.1f}s 後重試... 原因: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"API 異常已達最大重試次數: {e}")
            raise last_exception
        return wrapper
    return decorator


# ==================== 數據庫操作 ====================
def get_db_connection():
    """獲取數據庫連接"""
    return pymysql.connect(**DB_CONFIG)


def get_pending_signals() -> List[Dict]:
    """讀取 PENDING 信號"""
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM signals 
            WHERE status = 'PENDING' 
            AND signal_type IN ('BUY', 'SELL')
            ORDER BY created_at ASC
        """)
        signals = cursor.fetchall()
        return signals
    finally:
        cursor.close()
        conn.close()


def update_signal_status(signal_id: int, status: str):
    """更新信號狀態"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE signals 
            SET status = %s, updated_at = %s 
            WHERE id = %s
        """, (status, datetime.now(), signal_id))
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ==================== 富途 API 下單 ====================
@retry_api(max_retries=3)
def submit_paper_order(signal: Dict, trade_ctx: ft.OpenUSTradeContext) -> Optional[str]:
    """
    提交模擬訂單到富途
    Returns: 富途訂單 ID，失敗返回 None
    """
    symbol = signal['symbol']
    signal_type = signal['signal_type']
    quantity = signal['quantity']
    price = signal.get('price', 0)
    
    # 判斷訂單方向
    trd_side = ft.TrdSide.BUY if signal_type == 'BUY' else ft.TrdSide.SELL
    
    # 市價單
    ret, data = trade_ctx.place_order(
        price=0,  # 0 表示市價單
        qty=quantity,
        code=symbol,
        trd_side=trd_side,
        order_type=ft.OrderType.MARKET,
        trd_env=ft.TrdEnv.SIMULATE  # 模擬交易
    )
    
    if ret == ft.RET_OK:
        futu_order_id = data['order_id'][0]
        logger.info(f"✅ 富途下單成功: {symbol} {signal_type} {quantity}股, 訂單ID={futu_order_id}")
        return futu_order_id
    else:
        logger.error(f"❌ 富途下單失敗: {symbol} {signal_type}, 錯誤: {data}")
        return None


def create_paper_order(signal: Dict, futu_order_id: str) -> Optional[int]:
    """寫入 paper_orders 表"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO paper_orders 
            (symbol, order_type, quantity, price, status, source_signal_id, futu_order_id, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            signal['symbol'],
            signal['signal_type'],
            signal['quantity'],
            signal.get('price', 0),
            'pending',
            signal['id'],
            futu_order_id,
            datetime.now()
        ))
        conn.commit()
        order_id = cursor.lastrowid
        logger.info(f"✅ 寫入 paper_orders: ID={order_id}")
        return order_id
    except Exception as e:
        logger.error(f"❌ 寫入 paper_orders 失敗: {e}")
        conn.rollback()
        return None
    finally:
        cursor.close()
        conn.close()


# ==================== 訂單輪詢與狀態更新 ====================
def get_pending_paper_orders() -> List[Dict]:
    """獲取待輪詢訂單（pending / partial）。"""
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM paper_orders 
            WHERE status IN ('pending', 'partial')
            ORDER BY created_at ASC
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


@retry_api(max_retries=2)
def query_order_status(futu_order_id: str, trade_ctx: ft.OpenUSTradeContext) -> Optional[Dict]:
    """查詢富途訂單狀態，回傳 polling/lifecycle 可直接使用的欄位。"""
    ret, data = trade_ctx.order_list_query(
        order_id=futu_order_id,
        trd_env=ft.TrdEnv.SIMULATE
    )

    if ret != ft.RET_OK or data.empty:
        logger.warning(f"⚠️ 查詢訂單失敗: {futu_order_id}")
        return None

    order_info = data.iloc[0].to_dict()
    dealt_qty = int(order_info.get('dealt_qty', 0) or 0)
    dealt_avg_price = float(order_info.get('dealt_avg_price', 0) or 0)
    updated_time = order_info.get('updated_time') or order_info.get('create_time')

    order_info['futu_order_id'] = str(order_info.get('order_id') or futu_order_id)
    order_info['normalized_status'] = str(order_info.get('order_status'))
    order_info['filled_quantity'] = dealt_qty
    order_info['filled_price'] = dealt_avg_price if dealt_qty > 0 else 0
    order_info['filled_at'] = updated_time if dealt_qty > 0 else None
    return order_info


def update_order_status(order_id: int, status: str, filled_quantity: int = 0, filled_price: float = 0, filled_at=None):
    """更新訂單狀態"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        effective_filled_at = filled_at or (datetime.now() if status in ('filled', 'partial') and filled_quantity > 0 else None)
        
        cursor.execute("""
            UPDATE paper_orders 
            SET status = %s, filled_quantity = %s, filled_price = %s, filled_at = %s, updated_at = %s
            WHERE id = %s
        """, (status, filled_quantity, filled_price, effective_filled_at, datetime.now(), order_id))
        conn.commit()
        logger.info(f"✅ 更新訂單狀態: ID={order_id}, status={status}")
    except Exception as e:
        logger.error(f"❌ 更新訂單狀態失敗: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


# ==================== 持倉更新 ====================
def handle_buy_fill(order: Dict):
    """處理買入成交：統一改用 paper_orders 重建持倉。"""
    result = reconcile_single_filled_order(order['id'], apply=True)
    if not result.get('success'):
        logger.error(f"❌ 處理買入成交失敗: order_id={order['id']}, result={result}")
    else:
        logger.info(f"✅ 已重建持倉: {order['symbol']} (BUY fill applied)")


def handle_sell_fill(order: Dict):
    """處理賣出成交：統一改用 paper_orders 重建持倉。"""
    result = reconcile_single_filled_order(order['id'], apply=True)
    if not result.get('success'):
        logger.error(f"❌ 處理賣出成交失敗: order_id={order['id']}, result={result}")
    else:
        logger.info(f"✅ 已重建持倉: {order['symbol']} (SELL fill applied)")


# ==================== 主流程 ====================
def process_pending_signals(dry_run: bool = False):
    """處理 PENDING 信號並下單"""
    logger.info("=" * 60)
    logger.info("📋 處理 PENDING 信號")
    
    # 連接富途（美股）
    trade_ctx = ft.OpenUSTradeContext(host=FUTU_HOST, port=FUTU_PORT)
    
    try:
        # 獲取 PENDING 信號
        signals = get_pending_signals()
        logger.info(f"📊 共 {len(signals)} 個 PENDING 信號")
        
        if not signals:
            logger.info("✅ 無待處理信號")
            return
        
        for signal in signals:
            symbol = signal['symbol']
            signal_type = signal['signal_type']
            signal_id = signal['id']
            
            logger.info(f"\n🔄 處理信號: ID={signal_id}, {symbol} {signal_type}")
            
            if dry_run:
                logger.info(f"   [Dry Run] 模擬下單")
                continue
            
            # 提交訂單
            futu_order_id = submit_paper_order(signal, trade_ctx)
            
            if futu_order_id:
                # 寫入 paper_orders
                order_id = create_paper_order(signal, futu_order_id)
                
                if order_id:
                    # 更新信號狀態
                    update_signal_status(signal_id, 'PROCESSING')
                    logger.info(f"✅ 信號處理完成: {symbol}")
                else:
                    logger.error(f"❌ 創建訂單失敗: {symbol}")
            else:
                logger.error(f"❌ 下單失敗: {symbol}")
                update_signal_status(signal_id, 'FAILED')
    
    finally:
        trade_ctx.close()
        logger.info("=" * 60)


def poll_paper_orders(dry_run: bool = False):
    """輪詢訂單狀態並更新"""
    logger.info("=" * 60)
    logger.info("🔍 輪詢訂單狀態")
    
    # 連接富途（美股）
    trade_ctx = ft.OpenUSTradeContext(host=FUTU_HOST, port=FUTU_PORT)
    
    try:
        # 獲取待輪詢訂單（包含 pending / partial）
        orders = get_pending_paper_orders()
        logger.info(f"📊 共 {len(orders)} 個待輪詢訂單 (pending/partial)")
        
        if not orders:
            logger.info("✅ 無待處理訂單")
            return
        
        for order in orders:
            order_id = order['id']
            futu_order_id = order['futu_order_id']
            symbol = order['symbol']
            order_type = order['order_type']
            
            logger.info(f"\n🔄 查詢訂單: ID={order_id}, {symbol} {order_type}")
            
            if dry_run:
                logger.info(f"   [Dry Run] 模擬查詢")
                continue
            
            # 查詢富途訂單狀態
            order_info = query_order_status(futu_order_id, trade_ctx)
            
            if not order_info:
                continue
            
            # 富途訂單狀態
            futu_status = order_info.get('order_status')
            dealt_qty = int(order_info.get('dealt_qty', 0))
            dealt_avg_price = float(order_info.get('dealt_avg_price', 0))
            
            # 狀態映射
            if futu_status == ft.OrderStatus.FILLED_ALL:
                # 完全成交
                update_order_status(order_id, 'filled', dealt_qty, dealt_avg_price, order_info.get('filled_at'))
                
                # 更新持倉
                order['filled_quantity'] = dealt_qty
                order['filled_price'] = dealt_avg_price
                
                if order_type == 'BUY':
                    handle_buy_fill(order)
                else:
                    handle_sell_fill(order)
                
                logger.info(f"✅ 訂單成交: {symbol} {dealt_qty}股 @${dealt_avg_price:.2f}")
            
            elif futu_status == ft.OrderStatus.FILLED_PART:
                # 部分成交：保留在 partial，後續 cron 會持續輪詢直到 filled/cancelled/failed
                update_order_status(order_id, 'partial', dealt_qty, dealt_avg_price, order_info.get('filled_at'))
                logger.info(f"⏳ 部分成交: {symbol} {dealt_qty}股 @${dealt_avg_price:.2f}")
            
            elif futu_status == ft.OrderStatus.CANCELLED:
                # 已取消：若有部分成交，保留已成交欄位做對帳
                update_order_status(order_id, 'cancelled', dealt_qty, dealt_avg_price, order_info.get('filled_at'))
                logger.info(f"❌ 訂單取消: {symbol}")

            elif 'FAILED' in str(futu_status) or 'REJECT' in str(futu_status):
                update_order_status(order_id, 'failed', dealt_qty, dealt_avg_price, order_info.get('filled_at'))
                logger.info(f"❌ 訂單失敗: {symbol}, status={futu_status}")
            
            else:
                # pending / submitted / 未完全成交狀態都會持續被下次 polling 再追一次
                update_order_status(order_id, 'partial' if dealt_qty > 0 else 'pending', dealt_qty, dealt_avg_price, order_info.get('filled_at'))
                logger.info(f"⏳ 訂單待成交: {symbol}, status={futu_status}, dealt_qty={dealt_qty}")
    
    finally:
        trade_ctx.close()
        # 自癒：即使本輪沒有新成交，也從 filled orders 修補一次本地持倉。
        reconcile_paper_positions(apply=True)
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='模擬交易信號消費與自動下單')
    parser.add_argument('--dry-run', action='store_true', help='模擬運行，不實際下單')
    parser.add_argument('--poll-only', action='store_true', help='只輪詢訂單狀態，不處理新信號')
    args = parser.parse_args()
    
    try:
        if args.poll_only:
            poll_paper_orders(dry_run=args.dry_run)
        else:
            # 處理新信號
            process_pending_signals(dry_run=args.dry_run)
            # 輪詢訂單狀態
            poll_paper_orders(dry_run=args.dry_run)
    
    except Exception as e:
        logger.error(f"❌ 執行失敗: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
