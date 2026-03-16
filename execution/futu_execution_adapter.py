from __future__ import annotations

from typing import Any, Dict

from paper_trading import submit_paper_order


class FutuExecutionAdapter:
    def submit_order(self, *, symbol: str, action: str, quantity: float, price: float,
                     source_signal_id: int | None = None, stop_loss: float | None = None,
                     take_profit: float | None = None) -> Dict[str, Any]:
        order_type = 'BUY' if action == 'buy' else 'SELL'
        try:
            result = submit_paper_order(
                symbol=symbol,
                order_type=order_type,
                quantity=int(quantity),
                price=price,
                source_signal_id=source_signal_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        except Exception as exc:
            return {
                'success': False,
                'broker': 'futu',
                'broker_order_id': None,
                'status': 'error',
                'raw': {},
                'error_message': str(exc),
                'account_type': 'futu_sim',
                'order_type': order_type,
                'qty': quantity,
                'price': price,
            }

        success = bool(result.get('success'))
        broker_order_id = result.get('futu_order_id') or result.get('order_id')
        status = result.get('status') or ('pending' if success else 'error')
        return {
            'success': success,
            'broker': 'futu',
            'broker_order_id': str(broker_order_id) if broker_order_id is not None else None,
            'status': status,
            'raw': result,
            'error_message': result.get('error'),
            'account_type': 'futu_sim',
            'order_type': order_type,
            'qty': quantity,
            'price': price,
        }
