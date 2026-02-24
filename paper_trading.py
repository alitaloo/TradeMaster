#!/usr/bin/env python3
"""
Paper Trading Service - 模擬交易服務
包含下單、訂單查詢、成交處理等功能
"""
import os
import sys
from datetime import datetime
from typing import Optional, Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import PaperOrder, PaperPosition, SystemConfig

# 嘗試導入富途 SDK
try:
    from futu import (
        OpenQuoteContext, OpenUSTradeContext, 
        TrdMarket, TrdSide, OrderType, TrdEnv
    )
    FUTU_AVAILABLE = True
    print("✅ 富途 SDK 已載入")
except ImportError:
    FUTU_AVAILABLE = False
    print("⚠️  富途 SDK 未安裝，使用模擬模式")

# 富途 API 配置
FUTU_HOST = os.getenv('FUTU_HOST', '127.0.0.1')
FUTU_PORT = int(os.getenv('FUTU_PORT', 11111))


def get_trade_context(trading_mode=1):
    """
    獲取富途交易上下文
    
    Args:
        trading_mode: 1=模擬交易, 0=真實交易
    
    Returns:
        OpenUSTradeContext: 富途交易上下文
    """
    if not FUTU_AVAILABLE:
        return None
    
    # 富途 OpenD 本地服務
    host = os.getenv('FUTU_HOST', '127.0.0.1')
    port = int(os.getenv('FUTU_PORT', '11111'))
    
    # 交易環境：SIMULATE=模擬, REAL=真實
    
    try:
        context = OpenUSOpenUSTradeContext(host=host, port=port, trd_env=trd_env)
        return context
    except Exception as e:
        print(f"❌ 富途連接失敗: {e}")
        return None


def call_futu_api(method, trading_mode=1, **kwargs):
    """
    呼叫富途 API
    
    如果富途 SDK 可用則使用實際 API，否則使用模擬
    """
    if FUTU_AVAILABLE and method == 'place_order':
        context = get_trade_context(trading_mode)
        if context:
            try:
                # 轉換參數
                symbol = kwargs.get('symbol')
                order_type = kwargs.get('order_type')  # BUY/SELL
                quantity = kwargs.get('quantity')
                price = kwargs.get('price')
                
                # 富途股票代碼格式: US.AAPL
                if '.' not in symbol:
                    symbol = f"US.{symbol}"
                
                # 交易方向
                trd_side = TrdSide.BUY if order_type == 'BUY' else TrdSide.SELL
                
                # 下單
                ret, data = context.place_order(
                    price=price if price else 0,  # 0 = 市價單
                    qty=quantity,
                    code=symbol,
                    trd_side=trd_side,
                    trd_market=TrdMarket.US,
                    order_type=OrderType.NORMAL
                )
                
                if ret == 0:
                    order_id = str(data['order_id'][0]) if 'order_id' in data else None
                    return {'status': 'ok', 'order_id': order_id}
                else:
                    return {'status': 'error', 'error': str(data)}
                    
            except Exception as e:
                print(f"❌ 富途下單失敗: {e}")
                return {'status': 'error', 'error': str(e)}
            finally:
                context.close()
    
    # 模擬回應
    return {
        'status': 'ok',
        'order_id': f'PAPER_{datetime.now().strftime("%Y%m%d%H%M%S")}',
    }


def submit_paper_order(symbol: str, order_type: str, quantity: int, 
                       price: Optional[float] = None,
                       source_signal_id: Optional[int] = None,
                       stop_loss: Optional[float] = None,
                       take_profit: Optional[float] = None) -> Dict:
    """
    提交模擬訂單（真實調用富途 API）
    
    Args:
        symbol: 股票代碼 (如 US.AAPL)
        order_type: BUY 或 SELL
        quantity: 股數
        price: 委託價格 (None 為市價單)
        source_signal_id: 來源信號 ID
        stop_loss: 止損價格
        take_profit: 止盈價格
    
    Returns:
        dict: 訂單結果
    """
    # 檢查是否啟用模擬交易
    if not SystemConfig.is_paper_trading():
        return {
            'success': False,
            'error': '模擬交易未啟用'
        }
    
    # 驗證參數
    if order_type not in ['BUY', 'SELL']:
        return {
            'success': False,
            'error': 'order_type 必須是 BUY 或 SELL'
        }
    
    if quantity <= 0:
        return {
            'success': False,
            'error': 'quantity 必须大于 0'
        }
    
    # 呼叫富途 API (真實調用)
    try:
        import futu as ft
        
        # 連接富途交易API（美股）
        trade_ctx = ft.OpenUSTradeContext(host='127.0.0.1', port=11111)
        
        # 判斷訂單方向
        trd_side = ft.TrdSide.BUY if order_type == 'BUY' else ft.TrdSide.SELL
        
        # 市價單下單
        ret, data = trade_ctx.place_order(
            price=0,  # 0 表示市價單
            qty=quantity,
            code=symbol,
            trd_side=trd_side,
            order_type=ft.OrderType.MARKET,
            trd_env=ft.TrdEnv.SIMULATE  # 模擬交易
        )
        
        trade_ctx.close()
        
        if ret != ft.RET_OK:
            return {
                'success': False,
                'error': f'富途下單失敗: {data}'
            }
        
        # 獲取富途訂單 ID
        futu_order_id = data['order_id'][0]
        
        # 建立訂單記錄
        order = PaperOrder(
            symbol=symbol,
            order_type=order_type,
            quantity=quantity,
            price=price or 0,
            status='pending',
            source_signal_id=source_signal_id,
            futu_order_id=futu_order_id,
            filled_quantity=0,
            filled_price=None,
            filled_at=None
        )
        order.save()
        
        return {
            'success': True,
            'order_id': order.id,
            'futu_order_id': futu_order_id,
            'status': 'pending',
            'symbol': symbol,
            'order_type': order_type,
            'quantity': quantity,
            'price': price,
            'stop_loss': stop_loss,
            'take_profit': take_profit
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def query_order(order_id: int) -> Optional[Dict]:
    """
    查詢訂單狀態
    
    Args:
        order_id: 訂單 ID
    
    Returns:
        dict: 訂單資訊
    """
    order = PaperOrder.find_by_id(order_id)
    if not order:
        return None
    
    # 呼叫富途 API 查詢最新狀態
    # TODO: 實際調用富途 API
    # result = call_futu_api('order_info', trading_mode=trading_mode,
    #                         order_id=order.futu_order_id)
    
    return order.to_dict()


def update_order_status(order_id: int, status: str, 
                        filled_quantity: int = 0, 
                        filled_price: float = None) -> bool:
    """
    更新訂單狀態
    
    Args:
        order_id: 訂單 ID
        status: 新狀態 (pending/partial/filled/cancelled)
        filled_quantity: 成交數量
        filled_price: 成交價格
    
    Returns:
        bool: 是否成功
    """
    order = PaperOrder.find_by_id(order_id)
    if not order:
        return False
    
    order.status = status
    order.filled_quantity = filled_quantity
    
    if filled_price:
        order.filled_price = filled_price
    
    if status == 'filled':
        order.filled_at = datetime.now()
    
    order.save()
    return True


def poll_paper_orders() -> List[Dict]:
    """
    輪詢所有 pending 訂單，更新狀態
    
    Returns:
        list: 更新後的訂單列表
    """
    pending_orders = PaperOrder.find_pending()
    results = []
    
    trading_mode = SystemConfig.get_trading_mode()
    
    for order in pending_orders:
        try:
            # TODO: 實際調用富途 API
            # result = call_futu_api('order_info', trading_mode=trading_mode,
            #                         order_id=order.futu_order_id)
            
            # 模擬: 假設所有訂單都成交了
            # 實際應該根據 API 回應判斷
            filled_qty = order.quantity
            filled_prc = order.price or 100.0  # 如果是市價單，用假設價格
            
            # 更新訂單狀態
            update_order_status(order.id, 'filled', filled_qty, filled_prc)
            
            # 處理成交
            if order.order_type == 'BUY':
                handle_buy_fill(order.id)
            elif order.order_type == 'SELL':
                handle_sell_fill(order.id)
            
            results.append({
                'order_id': order.id,
                'status': 'filled',
                'filled_quantity': filled_qty,
                'filled_price': filled_prc
            })
            
        except Exception as e:
            results.append({
                'order_id': order.id,
                'error': str(e)
            })
    
    return results


def handle_buy_fill(order_id: int) -> bool:
    """
    處理買入成交
    
    Args:
        order_id: 訂單 ID
    
    Returns:
        bool: 是否成功
    """
    order = PaperOrder.find_by_id(order_id)
    if not order or order.status != 'filled':
        return False
    
    symbol = order.symbol
    filled_qty = order.filled_quantity
    filled_prc = float(order.filled_price)
    
    # 檢查是否已有持倉
    existing = PaperPosition.find_by_symbol(symbol)
    
    if existing:
        # 計算新的平均成本
        total_cost = (existing.quantity * existing.average_cost) + (filled_qty * filled_prc)
        total_qty = existing.quantity + filled_qty
        new_avg_cost = total_cost / total_qty
        
        existing.quantity = total_qty
        existing.average_cost = new_avg_cost
        existing.calculate_pnl(existing.current_price)
        existing.save()
    else:
        # 新建持倉
        pos = PaperPosition(
            symbol=symbol,
            quantity=filled_qty,
            average_cost=filled_prc,
            current_price=filled_prc,
            market_value=filled_qty * filled_prc,
            unrealized_pnl=0,
            unrealized_pnl_pct=0,
            realized_pnl=0
        )
        pos.save()
    
    return True


def handle_sell_fill(order_id: int) -> bool:
    """
    處理賣出成交
    
    Args:
        order_id: 訂單 ID
    
    Returns:
        bool: 是否成功
    """
    order = PaperOrder.find_by_id(order_id)
    if not order or order.status != 'filled':
        return False
    
    symbol = order.symbol
    filled_qty = order.filled_quantity
    filled_prc = float(order.filled_price)
    
    # 檢查持倉
    pos = PaperPosition.find_by_symbol(symbol)
    if not pos:
        return False
    
    # 計算已實現損益
    pnl = (filled_prc - pos.average_cost) * filled_qty
    pos.realized_pnl = float(pos.realized_pnl or 0) + pnl
    pos.quantity -= filled_qty
    
    if pos.quantity <= 0:
        # 全部賣出，刪除持倉
        PaperPosition.delete_by_symbol(symbol)
    else:
        pos.calculate_pnl(filled_prc)
        pos.save()
    
    return True


def close_position(symbol: str) -> Optional[Dict]:
    """
    平倉 (賣出全部)
    
    Args:
        symbol: 股票代碼
    
    Returns:
        dict: 新訂單結果
    """
    pos = PaperPosition.find_by_symbol(symbol)
    if not pos or pos.quantity <= 0:
        return {
            'success': False,
            'error': '無持倉'
        }
    
    return submit_paper_order(
        symbol=symbol,
        order_type='SELL',
        quantity=pos.quantity,
        price=pos.current_price
    )


def cancel_paper_order(order_id: int) -> bool:
    """
    取消訂單
    
    Args:
        order_id: 訂單 ID
    
    Returns:
        bool: 是否成功
    """
    order = PaperOrder.find_by_id(order_id)
    if not order or order.status != 'pending':
        return False
    
    trading_mode = SystemConfig.get_trading_mode()
    
    try:
        # TODO: 實際調用富途 API
        # call_futu_api('cancel_order', trading_mode=trading_mode,
        #               order_id=order.futu_order_id)
        
        order.status = 'cancelled'
        order.save()
        return True
        
    except Exception:
        return False


if __name__ == '__main__':
    # 測試
    print('=== Paper Trading Service 測試 ===')
    
    # 測試下單
    result = submit_paper_order('AAPL', 'BUY', 100, 150.0)
    print(f'下單結果: {result}')
    
    # 測試查詢
    if result.get('success'):
        order = query_order(result['order_id'])
        print(f'查詢結果: {order}')
    
    print('測試完成!')
