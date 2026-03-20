#!/usr/bin/env python3
"""
Paper position reconciliation utilities.

以 paper_orders(status='filled') 為唯一真實來源，重建/對帳 paper_positions。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from config.database import get_db_connection, get_db_cursor
from models import PaperOrder, PaperPosition, SystemConfig


@dataclass
class RebuiltPosition:
    symbol: str
    quantity: int
    average_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    realized_pnl: float

    def to_db_tuple(self) -> Tuple:
        return (
            self.symbol,
            self.quantity,
            self.average_cost,
            self.current_price,
            self.market_value,
            self.unrealized_pnl,
            self.unrealized_pnl_pct,
            self.realized_pnl,
        )


def _to_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round_price(value: float) -> float:
    return round(_to_float(value), 4)


def _round_money(value: float) -> float:
    return round(_to_float(value), 2)


def _build_current_price_map() -> Dict[str, float]:
    price_map: Dict[str, float] = {}
    with get_db_cursor() as cursor:
        cursor.execute("SELECT symbol, current_price FROM paper_positions")
        for row in cursor.fetchall():
            price_map[row['symbol']] = _to_float(row.get('current_price'))
    return price_map


def fetch_filled_orders() -> List[Dict]:
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM paper_orders
            WHERE status = 'filled' AND COALESCE(filled_quantity, 0) > 0
            ORDER BY COALESCE(filled_at, created_at) ASC, id ASC
            """
        )
        return cursor.fetchall()


def rebuild_positions_from_orders(current_price_map: Optional[Dict[str, float]] = None) -> Dict[str, RebuiltPosition]:
    current_price_map = current_price_map or _build_current_price_map()
    ledger: Dict[str, Dict[str, float]] = {}

    for order in fetch_filled_orders():
        symbol = order['symbol']
        side = order['order_type']
        quantity = int(order.get('filled_quantity') or 0)
        price = _to_float(order.get('filled_price'))
        state = ledger.setdefault(symbol, {
            'quantity': 0,
            'average_cost': 0.0,
            'realized_pnl': 0.0,
        })

        if side == 'BUY':
            total_cost = state['quantity'] * state['average_cost'] + quantity * price
            state['quantity'] += quantity
            state['average_cost'] = (total_cost / state['quantity']) if state['quantity'] > 0 else 0.0
        elif side == 'SELL':
            if quantity > state['quantity']:
                # 記錄警告但不中斷重建，將 qty clamp 到可用量（歷史骯數據容錯）
                import logging
                logging.warning(
                    f"[reconcile] SELL {symbol} qty={quantity} exceeds available qty={state['quantity']} "
                    f"(order id={order['id']}) — clamping to available"
                )
                quantity = state['quantity']  # clamp 到可用量，繼續重建
            realized_delta = (price - state['average_cost']) * quantity
            state['realized_pnl'] += realized_delta
            state['quantity'] -= quantity
            if state['quantity'] == 0:
                state['average_cost'] = 0.0
        else:
            raise ValueError(f"Unsupported order_type={side} for order id={order['id']}")

    rebuilt: Dict[str, RebuiltPosition] = {}
    for symbol, state in ledger.items():
        if state['quantity'] <= 0:
            continue
        current_price = _to_float(current_price_map.get(symbol), state['average_cost'])
        market_value = state['quantity'] * current_price
        unrealized_pnl = (current_price - state['average_cost']) * state['quantity']
        unrealized_pnl_pct = ((current_price / state['average_cost']) - 1) * 100 if state['average_cost'] > 0 else 0.0
        rebuilt[symbol] = RebuiltPosition(
            symbol=symbol,
            quantity=int(state['quantity']),
            average_cost=_round_price(state['average_cost']),
            current_price=_round_price(current_price),
            market_value=_round_money(market_value),
            unrealized_pnl=_round_money(unrealized_pnl),
            unrealized_pnl_pct=_round_price(unrealized_pnl_pct),
            realized_pnl=_round_money(state['realized_pnl']),
        )

    return rebuilt


def load_current_positions() -> Dict[str, Dict]:
    current: Dict[str, Dict] = {}
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM paper_positions ORDER BY symbol ASC")
        for row in cursor.fetchall():
            current[row['symbol']] = {
                'symbol': row['symbol'],
                'quantity': int(row.get('quantity') or 0),
                'average_cost': _round_price(row.get('average_cost') or 0),
                'current_price': _round_price(row.get('current_price') or 0),
                'market_value': _round_money(row.get('market_value') or 0),
                'unrealized_pnl': _round_money(row.get('unrealized_pnl') or 0),
                'unrealized_pnl_pct': _round_price(row.get('unrealized_pnl_pct') or 0),
                'realized_pnl': _round_money(row.get('realized_pnl') or 0),
            }
    return current


def _compare_fields(current: Optional[Dict], rebuilt: Optional[RebuiltPosition]) -> Dict[str, Dict[str, float]]:
    fields = ['quantity', 'average_cost', 'realized_pnl']
    diffs: Dict[str, Dict[str, float]] = {}
    rebuilt_dict = asdict(rebuilt) if rebuilt else {}
    current = current or {}
    for field in fields:
        cur = current.get(field, 0)
        new = rebuilt_dict.get(field, 0)
        if _round_price(cur) != _round_price(new):
            diffs[field] = {
                'current': cur,
                'rebuilt': new,
            }
    return diffs


def calculate_rebuilt_assets(rebuilt_positions: Dict[str, RebuiltPosition]) -> Dict[str, float]:
    cash = _to_float(SystemConfig.get_initial_balance())
    total_buy = 0.0
    total_sell = 0.0

    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT order_type, COALESCE(SUM(filled_quantity * filled_price), 0) AS gross
            FROM paper_orders
            WHERE status = 'filled' AND COALESCE(filled_quantity, 0) > 0
            GROUP BY order_type
            """
        )
        for row in cursor.fetchall():
            if row['order_type'] == 'BUY':
                total_buy = _to_float(row['gross'])
            elif row['order_type'] == 'SELL':
                total_sell = _to_float(row['gross'])

    cash = cash - total_buy + total_sell
    market_value = sum(pos.market_value for pos in rebuilt_positions.values())
    unrealized_pnl = sum(pos.unrealized_pnl for pos in rebuilt_positions.values())
    realized_pnl = sum(pos.realized_pnl for pos in rebuilt_positions.values())
    total_position_cost = sum(pos.quantity * pos.average_cost for pos in rebuilt_positions.values())

    return {
        'cash': _round_money(cash),
        'market_value': _round_money(market_value),
        'total': _round_money(cash + market_value),
        'total_position_cost': _round_money(total_position_cost),
        'unrealized_pnl': _round_money(unrealized_pnl),
        'realized_pnl': _round_money(realized_pnl),
        'position_count': len(rebuilt_positions),
    }


def reconcile_paper_positions(apply: bool = False, quick_check: bool = False) -> Dict:
    """
    對帳持倉
    
    Args:
        apply: 是否應用重建後的持倉
        quick_check: 快速檢查模式，只比對數量，不全量重建。
                    適合高頻輪詢，避免每次都全量重建。
                    當 quick_check=True 時，如果沒有新 filled 訂單則跳過。
    
    Returns:
        dict: 對帳結果
    """
    # quick_check 模式：檢查是否有新 filled 訂單
    if quick_check:
        with get_db_cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) as cnt FROM paper_orders 
                WHERE status = 'filled' 
                AND filled_at > NOW() - INTERVAL 5 MINUTE
            """)
            row = cursor.fetchone()
            new_filled_count = row['cnt'] if row else 0
        
        if new_filled_count == 0:
            # 沒有新成交訂單，跳過全量重建
            return {
                'applied': apply,
                'skipped': True,
                'reason': 'no_new_filled_orders',
                'mismatch_count': 0,
                'mismatches': [],
            }
    
    current_positions = load_current_positions()
    rebuilt_positions = rebuild_positions_from_orders({
        symbol: row['current_price'] for symbol, row in current_positions.items()
    })

    symbols = sorted(set(current_positions.keys()) | set(rebuilt_positions.keys()))
    mismatches = []
    for symbol in symbols:
        current = current_positions.get(symbol)
        rebuilt = rebuilt_positions.get(symbol)
        field_diffs = _compare_fields(current, rebuilt)
        if field_diffs:
            mismatches.append({
                'symbol': symbol,
                'current': current or {
                    'symbol': symbol,
                    'quantity': 0,
                    'average_cost': 0,
                    'realized_pnl': 0,
                },
                'rebuilt': asdict(rebuilt) if rebuilt else {
                    'symbol': symbol,
                    'quantity': 0,
                    'average_cost': 0,
                    'current_price': 0,
                    'market_value': 0,
                    'unrealized_pnl': 0,
                    'unrealized_pnl_pct': 0,
                    'realized_pnl': 0,
                },
                'diff': field_diffs,
            })

    if apply:
        apply_rebuilt_positions(rebuilt_positions)
        current_positions = load_current_positions()

    return {
        'applied': apply,
        'skipped': False,
        'mismatch_count': len(mismatches),
        'mismatches': mismatches,
        'rebuilt_positions': {symbol: asdict(pos) for symbol, pos in rebuilt_positions.items()},
        'assets': calculate_rebuilt_assets(rebuilt_positions),
    }


def apply_rebuilt_positions(rebuilt_positions: Dict[str, RebuiltPosition]) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM paper_positions")
            if rebuilt_positions:
                cursor.executemany(
                    """
                    INSERT INTO paper_positions
                    (symbol, quantity, average_cost, current_price, market_value,
                     unrealized_pnl, unrealized_pnl_pct, realized_pnl)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [pos.to_db_tuple() for pos in rebuilt_positions.values()]
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def reconcile_single_filled_order(order_id: int, apply: bool = True) -> Dict:
    order = PaperOrder.find_by_id(order_id)
    if not order or order.status != 'filled' or int(order.filled_quantity or 0) <= 0:
        return {'success': False, 'reason': 'order_not_filled'}

    # 不用 quick_check，確保每次成交都強制重建持倉
    report = reconcile_paper_positions(apply=apply, quick_check=False)
    return {
        'success': True,
        'order_id': order_id,
        'symbol': order.symbol,
        'report': report,
    }


__all__ = [
    'RebuiltPosition',
    'fetch_filled_orders',
    'rebuild_positions_from_orders',
    'load_current_positions',
    'calculate_rebuilt_assets',
    'reconcile_paper_positions',
    'apply_rebuilt_positions',
    'reconcile_single_filled_order',
]
