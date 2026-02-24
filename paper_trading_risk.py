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


def get_current_price(symbol: str) -> float:
    """
    取得現價
    TODO: 實際從富途 API 取得
    """
    # 模擬: 隨機價格
    import random
    return round(random.uniform(100, 200), 2)


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
    
    for pos in positions:
        if pos.quantity <= 0:
            continue
        
        # 取得現價
        current_price = get_current_price(pos.symbol)
        pos.current_price = current_price
        pos.calculate_pnl(current_price)
        pos.save()
        
        # 檢查止損 (這裡應該從訂單或持倉記錄中取得止損止盈價格)
        # TODO: 從 paper_orders 或專門的止損止盈表取得
        stop_loss_price = None  # 假設 5% 止損
        take_profit_price = None  # 假設 10% 止盈
        
        # 計算止損止盈價格 (如果沒有設定)
        if not stop_loss_price:
            stop_loss_price = pos.average_cost * 0.95  # 5% 止損
        if not take_profit_price:
            take_profit_price = pos.average_cost * 1.10  # 10% 止盈
        
        # 檢查是否觸發
        if current_price <= stop_loss_price:
            # 觸發止損
            result = submit_paper_order(
                symbol=pos.symbol,
                order_type='SELL',
                quantity=pos.quantity,
                price=current_price,
                source_signal_id=None
            )
            triggered.append({
                'symbol': pos.symbol,
                'type': 'STOP_LOSS',
                'trigger_price': current_price,
                'stop_loss': stop_loss_price,
                'result': result
            })
            print(f'🚨 觸發止損: {pos.symbol} @ {current_price} (止損: {stop_loss_price})')
            
        elif current_price >= take_profit_price:
            # 觸發止盈
            result = submit_paper_order(
                symbol=pos.symbol,
                order_type='SELL',
                quantity=pos.quantity,
                price=current_price,
                source_signal_id=None
            )
            triggered.append({
                'symbol': pos.symbol,
                'type': 'TAKE_PROFIT',
                'trigger_price': current_price,
                'take_profit': take_profit_price,
                'result': result
            })
            print(f'🎯 觸發止盈: {pos.symbol} @ {current_price} (止盈: {take_profit_price})')
    
    return triggered


if __name__ == '__main__':
    print('=== 止損止盈監控測試 ===')
    results = check_stop_loss_take_profit()
    print(f'觸發數量: {len(results)}')
