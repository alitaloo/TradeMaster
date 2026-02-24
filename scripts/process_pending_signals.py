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
    """獲取待處理的訂單"""
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        cursor.execute("""
            SELECT * FROM paper_orders 
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


@retry_api(max_retries=2)
def query_order_status(futu_order_id: str, trade_ctx: ft.OpenUSTradeContext) -> Optional[Dict]:
    """查詢富途訂單狀態"""
    ret, data = trade_ctx.order_list_query(
        order_id=futu_order_id,
        trd_env=ft.TrdEnv.SIMULATE
    )
    
    if ret == ft.RET_OK and not data.empty:
        order_info = data.iloc[0].to_dict()
        return order_info
    else:
        logger.warning(f"⚠️ 查詢訂單失敗: {futu_order_id}")
        return None


def update_order_status(order_id: int, status: str, filled_quantity: int = 0, filled_price: float = 0):
    """更新訂單狀態"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        filled_at = datetime.now() if status == 'filled' else None
        
        cursor.execute("""
            UPDATE paper_orders 
            SET status = %s, filled_quantity = %s, filled_price = %s, filled_at = %s, updated_at = %s
            WHERE id = %s
        """, (status, filled_quantity, filled_price, filled_at, datetime.now(), order_id))
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
    """處理買入成交"""
    symbol = order['symbol']
    quantity = order['filled_quantity']
    price = order['filled_price']
    
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 查詢是否已有持倉
        cursor.execute("SELECT * FROM paper_positions WHERE symbol = %s", (symbol,))
        position = cursor.fetchone()
        
        if position:
            # 更新持倉：計算新平均成本
            old_qty = position['quantity']
            old_cost = position['average_cost']
            new_qty = old_qty + quantity
            new_cost = (old_cost * old_qty + price * quantity) / new_qty
            
            cursor.execute("""
                UPDATE paper_positions 
                SET quantity = %s, average_cost = %s, updated_at = %s
                WHERE symbol = %s
            """, (new_qty, new_cost, datetime.now(), symbol))
            logger.info(f"✅ 更新持倉: {symbol} 數量={new_qty}, 成本=${new_cost:.2f}")
        else:
            # 新增持倉
            cursor.execute("""
                INSERT INTO paper_positions 
                (symbol, quantity, average_cost, current_price, updated_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (symbol, quantity, price, price, datetime.now()))
            logger.info(f"✅ 新增持倉: {symbol} 數量={quantity}, 成本=${price:.2f}")
        
        conn.commit()
    except Exception as e:
        logger.error(f"❌ 處理買入成交失敗: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


def handle_sell_fill(order: Dict):
    """處理賣出成交"""
    symbol = order['symbol']
    quantity = order['filled_quantity']
    price = order['filled_price']
    
    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    try:
        # 查詢持倉
        cursor.execute("SELECT * FROM paper_positions WHERE symbol = %s", (symbol,))
        position = cursor.fetchone()
        
        if not position:
            logger.warning(f"⚠️ 找不到持倉: {symbol}")
            return
        
        # 計算已實現損益
        avg_cost = position['average_cost']
        realized_pnl = (price - avg_cost) * quantity
        
        # 更新持倉數量
        new_qty = position['quantity'] - quantity
        
        if new_qty <= 0:
            # 完全平倉
            cursor.execute("DELETE FROM paper_positions WHERE symbol = %s", (symbol,))
            logger.info(f"✅ 完全平倉: {symbol}, 已實現損益=${realized_pnl:.2f}")
        else:
            # 部分平倉
            old_realized = position.get('realized_pnl', 0) or 0
            new_realized = old_realized + realized_pnl
            
            cursor.execute("""
                UPDATE paper_positions 
                SET quantity = %s, realized_pnl = %s, updated_at = %s
                WHERE symbol = %s
            """, (new_qty, new_realized, datetime.now(), symbol))
            logger.info(f"✅ 部分平倉: {symbol} 剩餘={new_qty}, 已實現損益=${realized_pnl:.2f}")
        
        conn.commit()
    except Exception as e:
        logger.error(f"❌ 處理賣出成交失敗: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


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
        # 獲取 pending 訂單
        orders = get_pending_paper_orders()
        logger.info(f"📊 共 {len(orders)} 個待處理訂單")
        
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
                update_order_status(order_id, 'filled', dealt_qty, dealt_avg_price)
                
                # 更新持倉
                order['filled_quantity'] = dealt_qty
                order['filled_price'] = dealt_avg_price
                
                if order_type == 'BUY':
                    handle_buy_fill(order)
                else:
                    handle_sell_fill(order)
                
                logger.info(f"✅ 訂單成交: {symbol} {dealt_qty}股 @${dealt_avg_price:.2f}")
            
            elif futu_status == ft.OrderStatus.FILLED_PART:
                # 部分成交
                update_order_status(order_id, 'partial', dealt_qty, dealt_avg_price)
                logger.info(f"⏳ 部分成交: {symbol} {dealt_qty}股")
            
            elif futu_status == ft.OrderStatus.CANCELLED:
                # 已取消
                update_order_status(order_id, 'cancelled')
                logger.info(f"❌ 訂單取消: {symbol}")
            
            else:
                logger.info(f"⏳ 訂單待成交: {symbol}, status={futu_status}")
    
    finally:
        trade_ctx.close()
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
