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
from paper_position_reconciliation import reconcile_single_filled_order, reconcile_paper_positions

# 嘗試導入富途 SDK
try:
    from futu_api import (
        OpenQuoteContext, OpenUSTradeContext, 
        TrdMarket, TrdSide, OrderType, TrdEnv
    )
    FUTU_AVAILABLE = True
    print("✅ 富途 SDK 已載入")
except ImportError:
    try:
        from futu.quote.open_quote_context import OpenQuoteContext
        from futu.trade.open_trade_context import OpenUSTradeContext
        from futu.common.constant import TrdMarket, TrdSide, OrderType, TrdEnv
        FUTU_AVAILABLE = True
        print("✅ 富途 SDK 已載入 (futu)")
    except ImportError as e:
        FUTU_AVAILABLE = False
        print(f"⚠️  富途 SDK 未安裝，使用模擬模式: {e}")

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

    if int(trading_mode) != 1:
        raise RuntimeError(f"sim_only_guard=true blocked trade context creation for trading_mode={trading_mode}")
    
    # 富途 OpenD 本地服務
    host = os.getenv('FUTU_HOST', '127.0.0.1')
    port = int(os.getenv('FUTU_PORT', '11111'))
    
    try:
        context = OpenUSTradeContext(host=host, port=port)
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
            'error': '模擬交易未啟用',
            'sim_only_guard': True,
        }

    trading_mode = SystemConfig.get_trading_mode()
    if int(trading_mode) != 1:
        return {
            'success': False,
            'error': f'sim_only_guard=true blocked submit because paper_trading_mode={trading_mode}',
            'sim_only_guard': True,
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
    
    # 限價單必須有價格
    if price is None or price <= 0:
        return {
            'success': False,
            'error': '限價單必須提供有效的價格'
        }
    
    # SELL 订单检查持仓（禁止做空）
    if order_type == 'SELL':
        from models import PaperPosition
        position = PaperPosition.find_by_symbol(symbol)
        available_qty = position.quantity if position else 0
        
        if available_qty < quantity:
            return {
                'success': False,
                'error': f'持仓不足: 可用 {available_qty} 股, 尝试卖出 {quantity} 股'
            }
    
    # BUY 订单需要通过风控检查（卖出不需要，因为止损止盈要能卖出）
    if order_type == 'BUY':
        from core.risk_engine import check_signal_risk
        signal_data = {
            'symbol': symbol,
            'confidence': 0.7,  # 默认信心度
            'stop_loss': stop_loss,
            'take_profit': take_profit,
        }
        risk_result = check_signal_risk(signal_data, price, quantity)
        if not risk_result.get('passed'):
            return {
                'success': False,
                'error': f'风控检查未通过: {risk_result.get("warnings")}',
                'risk_result': risk_result,
            }
    
    # 呼叫富途 API (真實調用)
    try:
        from futu.quote.open_quote_context import OpenQuoteContext
        from futu.trade.open_trade_context import OpenUSTradeContext
        from futu.common.constant import TrdMarket, TrdSide, OrderType, TrdEnv
        ft = type('FT', (), {
            'OpenQuoteContext': OpenQuoteContext,
            'OpenUSTradeContext': OpenUSTradeContext,
            'TrdMarket': TrdMarket,
            'TrdSide': TrdSide,
            'OrderType': OrderType,
            'TrdEnv': TrdEnv,
            'RET_OK': 0
        })()
        
        # 連接富途交易API（美股）
        trade_ctx = ft.OpenUSTradeContext(host='127.0.0.1', port=11111)
        
        # 判斷訂單方向
        trd_side = ft.TrdSide.BUY if order_type == 'BUY' else ft.TrdSide.SELL
        
        # 限價單下單
        ret, data = trade_ctx.place_order(
            price=price,  # 使用信號價格作為限價
            qty=quantity,
            code=symbol,
            trd_side=trd_side,
            order_type=ft.OrderType.NORMAL,  # 限價單
            trd_env=ft.TrdEnv.SIMULATE  # 模擬交易
        )
        
        trade_ctx.close()
        
        if ret != ft.RET_OK:
            return {
                'success': False,
                'error': f'富途下單失敗: {data}',
                'sim_only_guard': True,
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
            filled_at=None,
            stop_loss=stop_loss,
            take_profit=take_profit
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
            'take_profit': take_profit,
            'sim_only_guard': True,
            'trading_mode': 1,
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'sim_only_guard': True,
        }


def query_order_status(futu_order_id: str) -> Optional[Dict]:
    """向 Futu SIM 查詢單一訂單，回傳 polling/lifecycle 可直接使用欄位。"""
    if not FUTU_AVAILABLE:
        return None

    context = get_trade_context(SystemConfig.get_trading_mode())
    if not context:
        return None

    try:
        ret, data = context.order_list_query(order_id=futu_order_id, trd_env=TrdEnv.SIMULATE)
        if ret != 0 or data is None or getattr(data, 'empty', False):
            return None
        row = data.iloc[0].to_dict()
        dealt_qty = int(row.get('dealt_qty', 0) or 0)
        dealt_avg_price = float(row.get('dealt_avg_price', 0) or 0)
        filled_at = row.get('updated_time') or row.get('create_time') if dealt_qty > 0 else None
        row['futu_order_id'] = str(row.get('order_id') or futu_order_id)
        row['filled_quantity'] = dealt_qty
        row['filled_price'] = dealt_avg_price if dealt_qty > 0 else None
        row['filled_at'] = filled_at
        return row
    except Exception as e:
        print(f"⚠️  查詢富途訂單失敗 {futu_order_id}: {e}")
        return None
    finally:
        context.close()


def query_order(order_id: int) -> Optional[Dict]:
    """
    查詢訂單狀態
    """
    order = PaperOrder.find_by_id(order_id)
    if not order:
        return None

    latest = query_order_status(order.futu_order_id) if order.futu_order_id else None
    payload = order.to_dict()
    if latest:
        payload['broker_status'] = str(latest.get('order_status'))
        payload['filled_quantity'] = latest.get('filled_quantity', payload.get('filled_quantity'))
        payload['filled_price'] = latest.get('filled_price', payload.get('filled_price'))
        payload['filled_at'] = latest.get('filled_at', payload.get('filled_at'))
        payload['futu_order_id'] = latest.get('futu_order_id', payload.get('futu_order_id'))
    return payload


def update_order_status(order_id: int, status: str, 
                        filled_quantity: int = 0, 
                        filled_price: float = None,
                        filled_at=None) -> bool:
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
    
    if filled_price is not None:
        order.filled_price = filled_price
    
    if filled_at is not None:
        order.filled_at = filled_at
    elif status in ('filled', 'partial') and filled_quantity > 0:
        order.filled_at = datetime.now()
    
    order.save()
    return True


def poll_paper_orders() -> List[Dict]:
    """
    輪詢所有待追蹤訂單（pending / partial），優先以 Futu SIM order_list_query 回寫 paper_orders。
    partial 會持續保留在輪詢集合中，直到 filled / cancelled / failed。

    額外做一次 reconciliation self-heal：
    若過去曾出現「order 已 filled 但 paper_positions 未同步」的缺口，
    本次輪詢也會自動以 paper_orders 重建本地持倉。
    """
    pending_orders = PaperOrder.find_pending()
    results = []

    for order in pending_orders:
        try:
            order_info = query_order_status(order.futu_order_id) if order.futu_order_id else None
            if not order_info:
                results.append({
                    'order_id': order.id,
                    'futu_order_id': order.futu_order_id,
                    'status': order.status,
                    'filled_quantity': order.filled_quantity,
                    'filled_price': float(order.filled_price) if order.filled_price else None,
                    'filled_at': order.filled_at.isoformat() if order.filled_at else None,
                    'warning': 'futu order query unavailable'
                })
                continue

            futu_status = str(order_info.get('order_status'))
            filled_qty = int(order_info.get('filled_quantity', 0) or 0)
            filled_prc = float(order_info.get('filled_price') or order.price or 0)
            filled_at = order_info.get('filled_at')
            normalized_status = 'pending'

            if 'FILLED_ALL' in futu_status or futu_status.lower() in ('filled_all', 'filled all'):
                normalized_status = 'filled'
                update_order_status(order.id, normalized_status, filled_qty, filled_prc, filled_at)
                if order.order_type == 'BUY':
                    handle_buy_fill(order.id)
                elif order.order_type == 'SELL':
                    handle_sell_fill(order.id)
            elif 'FILLED_PART' in futu_status or futu_status.lower() in ('filled_part', 'filled part'):
                normalized_status = 'partial'
                update_order_status(order.id, normalized_status, filled_qty, filled_prc, filled_at)
                # 部分成交也要觸發持倉更新
                if order.order_type == 'BUY':
                    handle_buy_fill(order.id)
                elif order.order_type == 'SELL':
                    handle_sell_fill(order.id)
            elif 'CANCELLED' in futu_status or futu_status.lower().startswith('cancelled'):
                normalized_status = 'cancelled'
                update_order_status(order.id, normalized_status, filled_qty, filled_prc, filled_at)
            elif 'FAILED' in futu_status or 'REJECT' in futu_status:
                normalized_status = 'failed'
                update_order_status(order.id, normalized_status, filled_qty, filled_prc, filled_at)
            else:
                normalized_status = 'partial' if filled_qty > 0 else 'pending'
                update_order_status(order.id, normalized_status, filled_qty, filled_prc, filled_at)

            results.append({
                'order_id': order.id,
                'futu_order_id': order_info.get('futu_order_id'),
                'broker_status': futu_status,
                'status': normalized_status,
                'filled_quantity': filled_qty,
                'filled_price': filled_prc if filled_qty > 0 else None,
                'filled_at': filled_at
            })

        except Exception as e:
            results.append({
                'order_id': order.id,
                'futu_order_id': order.futu_order_id,
                'error': str(e)
            })

    # 自癒：即使本輪沒有新成交，仍用 filled orders 檢查/修補持倉缺口。
    # 使用 quick_check 模式，只有在新 filled 訂單時才全量重建
    reconcile_paper_positions(apply=True, quick_check=True)
    return results


def handle_buy_fill(order_id: int) -> bool:
    """
    處理買入成交。

    改為以 paper_orders 已成交紀錄為唯一來源做重建，
    避免「訂單已標記 filled，但本地持倉尚未同步」時資料永久分叉。
    """
    result = reconcile_single_filled_order(order_id, apply=True)
    return bool(result.get('success'))


def handle_sell_fill(order_id: int) -> bool:
    """
    處理賣出成交。

    改為以 paper_orders 已成交紀錄為唯一來源做重建，
    確保 quantity / realized_pnl / 清空持倉刪除都可由完整成交歷史可靠重放。
    """
    result = reconcile_single_filled_order(order_id, apply=True)
    return bool(result.get('success'))


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
    import logging
    logger = logging.getLogger(__name__)
    
    order = PaperOrder.find_by_id(order_id)
    if not order or order.status != 'pending':
        return False
    
    trading_mode = SystemConfig.get_trading_mode()
    
    # 嘗試調用富途 API 取消訂單
    if FUTU_AVAILABLE and order.futu_order_id:
        try:
            context = get_trade_context(trading_mode)
            if context:
                ret, data = context.modify_order(
                    order_id=order.futu_order_id,
                    new_price=0,
                    new_qty=0,
                    trd_env=TrdEnv.SIMULATE
                )
                context.close()
                
                if ret == 0:
                    logger.info(f"✅ 富途取消訂單成功: {order.futu_order_id}")
                else:
                    logger.warning(f"⚠️ 富途取消訂單失敗: {data}, 仍標記本地取消")
        except Exception as e:
            logger.warning(f"⚠️ 富途取消訂單異常: {e}, 仍標記本地取消")
    
    # 無論富途 API 是否成功，都標記本地訂單為取消
    try:
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
