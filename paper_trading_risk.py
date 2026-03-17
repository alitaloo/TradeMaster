#!/usr/bin/env python3
"""
Paper Trading Service - 止損止盈監控
"""
import os
import sys
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PaperPosition
from paper_trading import submit_paper_order, update_order_status
from paper_trading_portfolio import get_current_price
from config.database import get_db_connection
import logging

logger = logging.getLogger(__name__)


def get_stop_loss_take_profit(symbol: str) -> tuple:
    """
    從 signals 表或 paper_orders 表獲取止損止盈價格
    
    Returns:
        tuple: (stop_loss_price, take_profit_price) - 如果沒有則返回 (None, None)
    """
    try:
        from config.database import get_db_cursor
        
        with get_db_cursor() as cursor:
            # 查詢最新的信號（持倉建倉時的信號）
            cursor.execute("""
                SELECT stop_loss, take_profit 
                FROM signals 
                WHERE symbol = %s AND stop_loss IS NOT NULL
                ORDER BY created_at DESC 
                LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            
            if row:
                return (row['stop_loss'], row['take_profit'])
    except Exception as e:
        logger.debug(f"從 signals 表獲取止損止盈失敗: {e}")
    
    # 也嘗試從 paper_orders 表獲取
    try:
        from config.database import get_db_cursor
        
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT stop_loss, take_profit 
                FROM paper_orders 
                WHERE symbol = %s AND stop_loss IS NOT NULL
                ORDER BY created_at DESC 
                LIMIT 1
            """, (symbol,))
            row = cursor.fetchone()
            
            if row:
                return (row['stop_loss'], row['take_profit'])
    except Exception as e:
        logger.debug(f"從 paper_orders 表獲取止損止盈失敗: {e}")
    
    return (None, None)


def check_stop_loss_take_profit() -> List[Dict]:
    """
    檢查止損止盈
    
    遍歷所有持倉，檢查是否觸發止損或止盈
    
    Returns:
        list: 觸發的訂單列表
    """
    from models import SystemConfig
    
    if not SystemConfig.is_paper_trading():
        return []
    
    positions = PaperPosition.find_all()
    triggered = []
    
    # 默認止損止盈比例（僅當數據庫中沒有設定時使用）
    DEFAULT_STOP_LOSS_PCT = 0.05   # 5%
    DEFAULT_TAKE_PROFIT_PCT = 0.10  # 10%
    
    for pos in positions:
        if pos.quantity <= 0:
            continue
        
        # 安全檢查：只管理我們系統下的單（本地 paper_orders 有 BUY 記錄的）
        from config.database import get_db_cursor
        with get_db_cursor() as _c:
            _c.execute(
                "SELECT COUNT(*) as cnt FROM paper_orders WHERE symbol = %s AND order_type = 'BUY' AND status = 'filled'",
                (pos.symbol,)
            )
            has_local_buy = _c.fetchone()['cnt'] > 0
        
        if not has_local_buy:
            logger.info(f"跳過 {pos.symbol}：本地無 BUY 記錄，可能是手動買入的持倉")
            continue
        
        # 取得現價
        current_price = get_current_price(pos.symbol)
        if current_price is None:
            logger.warning(f"無法獲取 {pos.symbol} 價格，跳過止損止盈檢查")
            continue
            
        pos.current_price = current_price
        pos.calculate_pnl(current_price)
        pos.save()
        
        # 從信號或訂單表獲取止損止盈價格
        stop_loss_price, take_profit_price = get_stop_loss_take_profit(pos.symbol)
        
        # 合理性檢查：stop_loss 不能低於成本的 50%，take_profit 不能高於成本的 300%
        avg_cost = float(pos.average_cost)
        if stop_loss_price and float(stop_loss_price) < avg_cost * 0.5:
            logger.warning(f"⚠️ {pos.symbol} stop_loss={stop_loss_price} 不合理（< 成本 50%），改用預設值")
            stop_loss_price = None
        if take_profit_price and float(take_profit_price) > avg_cost * 3.0:
            logger.warning(f"⚠️ {pos.symbol} take_profit={take_profit_price} 不合理（> 成本 300%），改用預設值")
            take_profit_price = None
        
        # 如果沒有設定，從持倉成本計算（使用預設比例）
        if not stop_loss_price:
            stop_loss_price = avg_cost * (1 - DEFAULT_STOP_LOSS_PCT)  # 5% 止損
        if not take_profit_price:
            take_profit_price = avg_cost * (1 + DEFAULT_TAKE_PROFIT_PCT)  # 10% 止盈
        
        # 禁止做空：賣出數量不能超過目前持倉
        sell_quantity = pos.quantity
        
        # 檢查是否觸發
        if current_price <= float(stop_loss_price):
            # 觸發止損
            result = submit_paper_order(
                symbol=pos.symbol,
                order_type='SELL',
                quantity=sell_quantity,
                price=current_price,
                source_signal_id=None,
                source_type='stop_loss'
            )
            triggered.append({
                'symbol': pos.symbol,
                'type': 'STOP_LOSS',
                'trigger_price': current_price,
                'stop_loss': float(stop_loss_price),
                'quantity': sell_quantity,
                'result': result
            })
            print(f'🚨 觸發止損: {pos.symbol} {sell_quantity}股 @ {current_price} (止損: {stop_loss_price})')
            
        elif current_price >= float(take_profit_price):
            # 觸發止盈
            result = submit_paper_order(
                symbol=pos.symbol,
                order_type='SELL',
                quantity=sell_quantity,
                price=current_price,
                source_signal_id=None,
                source_type='take_profit'
            )
            triggered.append({
                'symbol': pos.symbol,
                'type': 'TAKE_PROFIT',
                'trigger_price': current_price,
                'take_profit': float(take_profit_price),
                'quantity': sell_quantity,
                'result': result
            })
            print(f'🎯 觸發止盈: {pos.symbol} {sell_quantity}股 @ {current_price} (止盈: {take_profit_price})')
    
    return triggered


if __name__ == '__main__':
    print('=== 止損止盈監控測試 ===')
    results = check_stop_loss_take_profit()
    print(f'觸發數量: {len(results)}')
