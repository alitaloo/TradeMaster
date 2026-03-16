from __future__ import annotations

import json
from typing import Any, Dict, Optional

from config.database import get_db_cursor


class ExecutionRepository:
    OPEN_LIFECYCLE_STATUSES = ('signal_created', 'order_submitted', 'partially_filled', 'filled_open', 'exit_pending')
    PENDING_ORDER_STATUSES = ('pending', 'submitted')

    def insert_signal(self, signal: Dict[str, Any]) -> int:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO strategy_signals (
                    strategy_name, symbol, action, entry_price, stop_loss, take_profit,
                    confidence, strength, reason, signal_time, signal_hash,
                    execution_enabled, status, status_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    signal['strategy_name'], signal['symbol'], signal['action'], signal['entry_price'],
                    signal.get('stop_loss'), signal.get('take_profit'), signal.get('confidence'),
                    signal.get('strength'), signal.get('reason'), signal['signal_time'], signal['signal_hash'],
                    1 if signal.get('execution_enabled', True) else 0,
                    signal.get('status', 'new'), signal.get('status_reason')
                )
            )
            return cursor.lastrowid

    def get_signal_by_hash(self, signal_hash: str) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM strategy_signals WHERE signal_hash = %s LIMIT 1", (signal_hash,))
            return cursor.fetchone()

    def update_signal_status(self, signal_id: int, status: str, status_reason: Optional[str] = None) -> None:
        with get_db_cursor() as cursor:
            cursor.execute(
                "UPDATE strategy_signals SET status = %s, status_reason = %s, updated_at = NOW() WHERE id = %s",
                (status, status_reason, signal_id),
            )

    def find_open_lifecycle(self, symbol: str, direction: str) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            placeholders = ','.join(['%s'] * len(self.OPEN_LIFECYCLE_STATUSES))
            cursor.execute(
                f"SELECT * FROM trade_lifecycles WHERE symbol = %s AND direction = %s AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",
                (symbol, direction, *self.OPEN_LIFECYCLE_STATUSES),
            )
            return cursor.fetchone()

    def find_pending_order(self, symbol: str, side: str) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            placeholders = ','.join(['%s'] * len(self.PENDING_ORDER_STATUSES))
            cursor.execute(
                f"SELECT * FROM broker_orders WHERE symbol = %s AND side = %s AND status IN ({placeholders}) ORDER BY id DESC LIMIT 1",
                (symbol, side, *self.PENDING_ORDER_STATUSES),
            )
            return cursor.fetchone()

    def count_submitted_signals_for_day(self, strategy_name: str, signal_time) -> int:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM strategy_signals
                WHERE strategy_name = %s
                  AND status = 'submitted'
                  AND DATE(signal_time) = DATE(%s)
                """,
                (strategy_name, signal_time),
            )
            row = cursor.fetchone()
            return int((row or {}).get('cnt', 0))

    def insert_broker_order(self, *, signal_id: int, signal: Dict[str, Any], adapter_result: Dict[str, Any]) -> int:
        raw_payload = json.dumps(adapter_result.get('raw') or {}, ensure_ascii=False, default=str)
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO broker_orders (
                    signal_id, broker, account_type, broker_order_id, symbol, side,
                    order_type, qty, price, status, submitted_at, updated_at,
                    reject_reason, raw_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), %s, %s)
                """,
                (
                    signal_id,
                    adapter_result.get('broker', 'futu'),
                    adapter_result.get('account_type', 'futu_sim'),
                    adapter_result['broker_order_id'],
                    signal['symbol'],
                    signal['action'],
                    adapter_result.get('order_type', signal['action'].upper()),
                    adapter_result.get('qty', signal.get('quantity', 1.0)),
                    adapter_result.get('price', signal['entry_price']),
                    adapter_result.get('status', 'pending'),
                    adapter_result.get('error_message'),
                    raw_payload,
                ),
            )
            return cursor.lastrowid

    def upsert_lifecycle(self, *, signal_id: int, signal: Dict[str, Any], status: str, entry_order_id: Optional[int] = None,
                         rejection_reason: Optional[str] = None) -> int:
        existing = self.find_open_lifecycle(signal['symbol'], signal['direction'])
        if existing:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE trade_lifecycles
                    SET status = %s, entry_order_id = COALESCE(%s, entry_order_id), stop_loss = %s,
                        take_profit = %s, position_qty = %s, rejection_reason = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (status, entry_order_id, signal.get('stop_loss'), signal.get('take_profit'), signal.get('quantity', 1.0), rejection_reason, existing['id'])
                )
            return existing['id']

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO trade_lifecycles (
                    signal_id, strategy_name, symbol, direction, entry_order_id,
                    entry_price, entry_time, position_qty, status, stop_loss, take_profit, rejection_reason
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    signal_id, signal['strategy_name'], signal['symbol'], signal['direction'], entry_order_id,
                    signal['entry_price'], signal['signal_time'], signal.get('quantity', 1.0), status,
                    signal.get('stop_loss'), signal.get('take_profit'), rejection_reason
                )
            )
            return cursor.lastrowid
