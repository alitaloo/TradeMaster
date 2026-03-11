from __future__ import annotations

import json
import logging
import os
import socket
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.database import get_db_cursor  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class SyncRunResult:
    orders_upserted: int = 0
    fills_upserted: int = 0
    position_snapshots_inserted: int = 0
    equity_snapshots_inserted: int = 0
    lifecycles_updated: int = 0
    risk_scan: Dict[str, Any] | None = None
    warnings: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'orders_upserted': self.orders_upserted,
            'fills_upserted': self.fills_upserted,
            'position_snapshots_inserted': self.position_snapshots_inserted,
            'equity_snapshots_inserted': self.equity_snapshots_inserted,
            'lifecycles_updated': self.lifecycles_updated,
            'risk_scan': self.risk_scan or {},
            'warnings': self.warnings or [],
        }


class FutuBrokerQueryAdapter:
    """Best-effort Futu query adapter.

    Notes:
    - Prefer Futu OpenD query APIs when available.
    - When the local SDK or query methods are unavailable, return empty datasets
      plus warnings so the sync layer remains runnable/idempotent.
    """

    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or os.getenv('FUTU_HOST', '127.0.0.1')
        self.port = int(port or os.getenv('FUTU_PORT', '11111'))
        self._ft = None
        self._warnings: List[str] = []
        self._disabled = os.getenv('FUTU_SYNC_DISABLE_BROKER', '0') == '1'
        self._bootstrap_sdk()

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    def _bootstrap_sdk(self) -> None:
        if self._disabled:
            self._warnings.append('broker sync disabled by FUTU_SYNC_DISABLE_BROKER=1')
            self._ft = None
            return
        if not self._is_broker_reachable():
            self._warnings.append(f'futu opend unreachable at {self.host}:{self.port}')
            self._ft = None
            return
        try:
            from futu.quote.open_quote_context import OpenQuoteContext  # type: ignore
            from futu.trade.open_trade_context import OpenUSTradeContext  # type: ignore
            from futu.common.constant import TrdEnv  # type: ignore

            self._ft = type(
                'FT',
                (),
                {
                    'OpenQuoteContext': OpenQuoteContext,
                    'OpenUSTradeContext': OpenUSTradeContext,
                    'TrdEnv': TrdEnv,
                    'RET_OK': 0,
                },
            )()
            return
        except Exception as exc:  # pragma: no cover - env specific
            self._warnings.append(f'futu sdk unavailable: {exc}')
            self._ft = None

    def _is_broker_reachable(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=0.6):
                return True
        except OSError:
            return False

    def _normalize_frame(self, data: Any) -> List[Dict[str, Any]]:
        if data is None:
            return []
        if hasattr(data, 'to_dict'):
            try:
                records = data.to_dict('records')
                if isinstance(records, list):
                    return records
            except Exception:
                pass
            try:
                row = data.to_dict()
                if isinstance(row, dict):
                    return [row]
            except Exception:
                pass
        if isinstance(data, list):
            return [dict(x) if not isinstance(x, dict) else x for x in data]
        if isinstance(data, dict):
            return [data]
        return []

    def _query(self, method_name: str, **kwargs: Any) -> List[Dict[str, Any]]:
        if not self._ft:
            return []
        ctx = None
        try:
            ctx = self._ft.OpenUSTradeContext(host=self.host, port=self.port)
            method = getattr(ctx, method_name, None)
            if method is None:
                self._warnings.append(f'futu method not available: {method_name}')
                return []
            ret, data = method(**kwargs)
            if ret != self._ft.RET_OK:
                self._warnings.append(f'{method_name} failed: {data}')
                return []
            return self._normalize_frame(data)
        except Exception as exc:  # pragma: no cover - env specific
            self._warnings.append(f'{method_name} exception: {exc}')
            return []
        finally:
            if ctx is not None:
                try:
                    ctx.close()
                except Exception:
                    pass

    def fetch_orders(self, checkpoint_time: datetime | None = None) -> List[Dict[str, Any]]:
        rows = self._query('order_list_query', trd_env=self._ft.TrdEnv.SIMULATE if self._ft else None)
        if checkpoint_time is None:
            return rows
        return [
            r for r in rows
            if self._extract_datetime(r, 'updated_time', 'create_time') is None
            or self._extract_datetime(r, 'updated_time', 'create_time') >= checkpoint_time
        ]

    def fetch_fills(self, checkpoint_time: datetime | None = None) -> List[Dict[str, Any]]:
        method_names = ['deal_list_query', 'history_deal_list_query']
        for name in method_names:
            rows = self._query(name, trd_env=self._ft.TrdEnv.SIMULATE if self._ft else None)
            if rows:
                if checkpoint_time is None:
                    return rows
                return [
                    r for r in rows
                    if self._extract_datetime(r, 'create_time', 'updated_time') is None
                    or self._extract_datetime(r, 'create_time', 'updated_time') >= checkpoint_time
                ]
        self._warnings.append('native futu deal list unavailable; relying on paper_orders fill fallback when possible')
        return []

    def fetch_positions(self) -> List[Dict[str, Any]]:
        rows = self._query('position_list_query', trd_env=self._ft.TrdEnv.SIMULATE if self._ft else None)
        return rows or []

    def fetch_account_info(self) -> List[Dict[str, Any]]:
        method_names = ['accinfo_query', 'acc_list_query']
        for name in method_names:
            rows = self._query(name, trd_env=self._ft.TrdEnv.SIMULATE if self._ft else None)
            if rows:
                return rows
        return []

    @staticmethod
    def _extract_datetime(row: Dict[str, Any], *keys: str) -> datetime | None:
        for key in keys:
            value = row.get(key)
            parsed = FutuSyncService._to_datetime(value)
            if parsed:
                return parsed
        return None


class FutuSyncService:
    ORDER_SYNC_NAME = 'futu_orders'
    FILL_SYNC_NAME = 'futu_fills'
    POSITION_SYNC_NAME = 'futu_positions'
    EQUITY_SYNC_NAME = 'futu_equity'
    PAPER_ORDER_SYNC_NAME = 'paper_orders'

    ORDER_STATUS_MAP = {
        'pending': 'submitted',
        'submitted': 'submitted',
        'submitting': 'submitted',
        'unsubmitted': 'submitted',
        'wait': 'submitted',
        'partial': 'partial_filled',
        'filled part': 'partial_filled',
        'partial_filled': 'partial_filled',
        'filled_part': 'partial_filled',
        'filled': 'filled',
        'filled_all': 'filled',
        'filled all': 'filled',
        'cancelled_all': 'cancelled',
        'cancelled part': 'cancelled',
        'cancelled': 'cancelled',
        'expired': 'cancelled',
        'failed': 'failed',
        'rejected': 'failed',
        'deleted': 'cancelled',
        'disable': 'failed',
    }

    def __init__(self, adapter: FutuBrokerQueryAdapter | None = None):
        self.adapter = adapter or FutuBrokerQueryAdapter()

    def run_once(self) -> Dict[str, Any]:
        result = SyncRunResult(warnings=[])
        result.orders_upserted = self.sync_orders()
        result.fills_upserted = self.sync_fills()
        result.position_snapshots_inserted = self.sync_positions_snapshot()
        result.equity_snapshots_inserted = self.sync_equity_snapshot()
        result.lifecycles_updated = self.refresh_trade_lifecycles()
        result.risk_scan = self.run_risk_monitor()
        result.warnings.extend(self.adapter.warnings)
        return result.to_dict()

    def sync_external_order_ref(self, external_order_ref: Any, *, lifecycle_id: int | None = None) -> Dict[str, Any]:
        external_order_ref = self._string_or_none(external_order_ref)
        if not external_order_ref:
            return self.run_once()

        result = SyncRunResult(warnings=[])
        paper_order = self.fetch_paper_order_by_external_order_ref(external_order_ref)
        broker_order = self.fetch_broker_order_by_external_order_ref(external_order_ref)

        if paper_order:
            result.orders_upserted += self.upsert_broker_order_from_paper_order(paper_order)
            if self._to_decimal(paper_order.get('filled_quantity')) > 0:
                result.fills_upserted += self.upsert_broker_fill_from_paper_order(paper_order)
            broker_order = self.fetch_broker_order_by_external_order_ref(external_order_ref) or broker_order

        lifecycle_updates = 0
        if lifecycle_id is not None:
            lifecycle_updates = self.refresh_trade_lifecycle_by_id(lifecycle_id)
        else:
            lifecycle_updates = self.refresh_trade_lifecycles_for_order_ref(external_order_ref)
        result.lifecycles_updated = lifecycle_updates
        result.warnings.extend(self.adapter.warnings)

        payload = result.to_dict()
        payload.update(
            {
                'external_order_ref': external_order_ref,
                'broker_order': broker_order,
                'paper_order': paper_order,
                'fill_detected': bool(paper_order and self._to_decimal(paper_order.get('filled_quantity')) > 0),
            }
        )
        return payload

    def sync_orders(self) -> int:
        checkpoint_time = self.get_checkpoint_time(self.ORDER_SYNC_NAME)
        rows = self.adapter.fetch_orders(checkpoint_time)
        count = 0
        newest_time = checkpoint_time
        for row in rows:
            count += self.upsert_broker_order_from_row(row)
            row_time = self._to_datetime(row.get('updated_time') or row.get('create_time'))
            if row_time and (newest_time is None or row_time > newest_time):
                newest_time = row_time

        paper_checkpoint = self.get_checkpoint_time(self.PAPER_ORDER_SYNC_NAME)
        paper_orders = self.fetch_paper_orders(paper_checkpoint)
        newest_paper_time = paper_checkpoint
        for paper_order in paper_orders:
            count += self.upsert_broker_order_from_paper_order(paper_order)
            row_time = self._to_datetime(paper_order.get('updated_at') or paper_order.get('filled_at') or paper_order.get('created_at'))
            if row_time and (newest_paper_time is None or row_time > newest_paper_time):
                newest_paper_time = row_time

        self.upsert_checkpoint(self.ORDER_SYNC_NAME, checkpoint_time=newest_time, checkpoint_value=str(count))
        self.upsert_checkpoint(self.PAPER_ORDER_SYNC_NAME, checkpoint_time=newest_paper_time, checkpoint_value=str(len(paper_orders)))
        return count

    def sync_fills(self) -> int:
        checkpoint_time = self.get_checkpoint_time(self.FILL_SYNC_NAME)
        rows = self.adapter.fetch_fills(checkpoint_time)
        count = 0
        newest_time = checkpoint_time
        for row in rows:
            count += self.upsert_broker_fill_from_row(row)
            row_time = self._to_datetime(row.get('create_time') or row.get('updated_time'))
            if row_time and (newest_time is None or row_time > newest_time):
                newest_time = row_time

        fallback_orders = self.fetch_filled_paper_orders(checkpoint_time)
        fallback_newest_time = newest_time
        for paper_order in fallback_orders:
            count += self.upsert_broker_fill_from_paper_order(paper_order)
            row_time = self._to_datetime(paper_order.get('filled_at') or paper_order.get('updated_at') or paper_order.get('created_at'))
            if row_time and (fallback_newest_time is None or row_time > fallback_newest_time):
                fallback_newest_time = row_time

        self.upsert_checkpoint(self.FILL_SYNC_NAME, checkpoint_time=fallback_newest_time, checkpoint_value=str(count))
        return count

    def sync_positions_snapshot(self) -> int:
        snapshot_time = datetime.now()
        rows = self.adapter.fetch_positions()
        count = 0
        for row in rows:
            self.insert_position_snapshot(row, snapshot_time)
            count += 1
        self.upsert_checkpoint(self.POSITION_SYNC_NAME, checkpoint_time=snapshot_time, checkpoint_value=str(count))
        return count

    def sync_equity_snapshot(self) -> int:
        snapshot_time = datetime.now()
        rows = self.adapter.fetch_account_info()
        if not rows:
            self.upsert_checkpoint(self.EQUITY_SYNC_NAME, checkpoint_time=snapshot_time, checkpoint_value='0')
            return 0

        inserted = 0
        for row in rows:
            self.insert_equity_snapshot(row, snapshot_time)
            inserted += 1
        self.upsert_checkpoint(self.EQUITY_SYNC_NAME, checkpoint_time=snapshot_time, checkpoint_value=str(inserted))
        return inserted

    def refresh_trade_lifecycles(self) -> int:
        open_lifecycles = self.fetch_open_lifecycles()
        return self._refresh_selected_trade_lifecycles(open_lifecycles)

    def _refresh_selected_trade_lifecycles(
        self,
        lifecycles: List[Dict[str, Any]],
        *,
        orders: List[Dict[str, Any]] | None = None,
        fills_by_order: Dict[str, List[Dict[str, Any]]] | None = None,
    ) -> int:
        orders = orders if orders is not None else self.fetch_all_broker_orders()
        fills_by_order = fills_by_order if fills_by_order is not None else self.fetch_fills_grouped_by_order()
        updated = 0

        for lifecycle in lifecycles:
            entry_order = self.find_order_by_id(orders, lifecycle.get('entry_order_id'))
            if not entry_order:
                continue

            entry_qty, entry_price, entry_time = self._resolve_order_execution(entry_order, fills_by_order)
            normalized_entry_status = self._normalize_order_status(entry_order.get('status'))
            entry_side = entry_order.get('side')
            exit_side = 'sell' if entry_side == 'buy' else 'buy'
            exit_order, exit_qty, exit_price, exit_time = self._match_exit_side(lifecycle, orders, fills_by_order, exit_side, entry_time)

            updates: Dict[str, Any] = {}
            if entry_qty > 0:
                updates['entry_price'] = float(entry_price) if entry_price is not None else None
                updates['entry_time'] = entry_time
                updates['position_qty'] = float(entry_qty)
                normalized_exit_status = self._normalize_order_status(exit_order.get('status')) if exit_order else None
                if exit_order and exit_qty <= 0 and normalized_exit_status in ('submitted', 'partial_filled', 'filled'):
                    updates['status'] = 'exit_pending'
                    updates['exit_order_id'] = exit_order['id']
                elif exit_qty <= 0:
                    updates['status'] = 'filled_open' if normalized_entry_status == 'filled' else 'partially_filled'
                elif exit_qty < entry_qty:
                    updates['status'] = 'exit_pending'
                    if exit_order:
                        updates['exit_order_id'] = exit_order['id']
                else:
                    updates['status'] = 'closed'
                    updates['exit_order_id'] = exit_order['id'] if exit_order else None
                    updates['exit_price'] = float(exit_price) if exit_price is not None else None
                    updates['exit_time'] = exit_time
                    pnl = self._compute_pnl(lifecycle['direction'], entry_price, exit_price, entry_qty)
                    updates['pnl'] = pnl
                    updates['pnl_pct'] = self._compute_pnl_pct(lifecycle['direction'], entry_price, pnl, entry_qty)
                    updates['holding_minutes'] = self._compute_holding_minutes(entry_time, exit_time)
                    updates['rr'] = self._compute_rr(lifecycle, entry_price, exit_price)
                    updates['exit_reason'] = self._infer_exit_reason(lifecycle, exit_price)
            elif normalized_entry_status == 'submitted':
                updates['status'] = 'order_submitted'
            elif normalized_entry_status in ('cancelled', 'failed'):
                updates['status'] = 'cancelled' if normalized_entry_status == 'cancelled' else 'rejected'
                updates['exit_reason'] = 'cancelled' if normalized_entry_status == 'cancelled' else 'rejected'

            if updates:
                self.update_lifecycle(lifecycle['id'], updates)
                updated += 1

        return updated

    def run_risk_monitor(self) -> Dict[str, Any]:
        try:
            from execution.exit_action_service import ExitActionService
            from execution.risk_monitor import LifecycleRiskMonitor

            risk_report = LifecycleRiskMonitor().scan()
            try:
                risk_report['action_layer'] = ExitActionService().generate_proposals()
            except Exception as action_exc:
                risk_report['action_layer'] = {
                    'generated_at': datetime.now().isoformat(sep=' '),
                    'summary': {
                        'scanned_active_candidates': 0,
                        'proposed_count': 0,
                        'blocked_count': 0,
                        'stale_count': 0,
                        'persisted_count': 0,
                        'gate_skipped_count': 0,
                    },
                    'proposals': [],
                    'gate': {
                        'enabled': False,
                        'mode': 'off',
                        'ready': False,
                        'reason': f'action layer failed: {action_exc}',
                    },
                }
            return risk_report
        except Exception as exc:
            warning = f'risk monitor failed: {exc}'
            logger.warning(warning)
            if self.adapter.warnings is not None:
                self.adapter.warnings.append(warning)
            return {
                'monitored_at': datetime.now().isoformat(sep=' '),
                'summary': {
                    'scanned': 0,
                    'candidate_count': 0,
                    'holding_timeout_count': 0,
                    'stop_loss_count': 0,
                    'take_profit_count': 0,
                },
                'candidates': [],
                'monitored': [],
                'action_layer': {
                    'generated_at': datetime.now().isoformat(sep=' '),
                    'summary': {
                        'scanned_active_candidates': 0,
                        'proposed_count': 0,
                        'blocked_count': 0,
                        'stale_count': 0,
                        'persisted_count': 0,
                        'gate_skipped_count': 0,
                    },
                    'proposals': [],
                    'gate': {
                        'enabled': False,
                        'mode': 'off',
                        'ready': False,
                        'reason': 'risk monitor unavailable',
                    },
                },
            }

    def fetch_paper_orders(self, checkpoint_time: datetime | None = None) -> List[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            if checkpoint_time is None:
                cursor.execute("SELECT * FROM paper_orders ORDER BY updated_at ASC, id ASC")
            else:
                cursor.execute(
                    """
                    SELECT * FROM paper_orders
                    WHERE COALESCE(updated_at, filled_at, created_at) >= %s
                    ORDER BY updated_at ASC, id ASC
                    """,
                    (checkpoint_time,),
                )
            return cursor.fetchall() or []

    def fetch_paper_order_by_external_order_ref(self, external_order_ref: Any) -> Dict[str, Any] | None:
        external_order_ref = self._string_or_none(external_order_ref)
        if not external_order_ref:
            return None
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM paper_orders
                WHERE CAST(COALESCE(futu_order_id, id) AS CHAR) = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (external_order_ref,),
            )
            return cursor.fetchone() or None

    def fetch_broker_order_by_external_order_ref(self, external_order_ref: Any) -> Dict[str, Any] | None:
        external_order_ref = self._string_or_none(external_order_ref)
        if not external_order_ref:
            return None
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM broker_orders
                WHERE broker_order_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (external_order_ref,),
            )
            return cursor.fetchone() or None

    def fetch_trade_lifecycle_by_id(self, lifecycle_id: Any) -> Dict[str, Any] | None:
        if lifecycle_id in (None, ''):
            return None
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM trade_lifecycles WHERE id = %s LIMIT 1', (lifecycle_id,))
            return cursor.fetchone() or None

    def refresh_trade_lifecycle_by_id(self, lifecycle_id: int) -> int:
        lifecycle = self.fetch_trade_lifecycle_by_id(lifecycle_id)
        if not lifecycle:
            return 0
        return self._refresh_selected_trade_lifecycles([lifecycle])

    def refresh_trade_lifecycles_for_order_ref(self, external_order_ref: Any) -> int:
        external_order_ref = self._string_or_none(external_order_ref)
        if not external_order_ref:
            return 0
        orders = self.fetch_all_broker_orders()
        target_order = next((row for row in orders if str(row.get('broker_order_id') or '') == external_order_ref), None)
        if not target_order:
            return 0
        open_lifecycles = self.fetch_open_lifecycles()
        matched = [
            lifecycle for lifecycle in open_lifecycles
            if lifecycle.get('exit_order_id') == target_order.get('id') or lifecycle.get('symbol') == target_order.get('symbol')
        ]
        if not matched:
            return 0
        return self._refresh_selected_trade_lifecycles(matched, orders=orders)

    def fetch_filled_paper_orders(self, checkpoint_time: datetime | None = None) -> List[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            if checkpoint_time is None:
                cursor.execute(
                    """
                    SELECT * FROM paper_orders
                    WHERE COALESCE(filled_quantity, 0) > 0
                    ORDER BY COALESCE(filled_at, updated_at, created_at) ASC, id ASC
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM paper_orders
                    WHERE COALESCE(filled_quantity, 0) > 0
                      AND COALESCE(filled_at, updated_at, created_at) >= %s
                    ORDER BY COALESCE(filled_at, updated_at, created_at) ASC, id ASC
                    """,
                    (checkpoint_time,),
                )
            return cursor.fetchall() or []

    def upsert_broker_order_from_row(self, row: Dict[str, Any]) -> int:
        broker_order_id = self._string_or_none(row.get('order_id') or row.get('id') or row.get('orderID'))
        if not broker_order_id:
            return 0

        symbol = self._string_or_none(row.get('code') or row.get('symbol')) or 'UNKNOWN'
        side = self._normalize_side(row.get('trd_side') or row.get('side'))
        order_type = self._string_or_none(row.get('order_type') or row.get('orderType')) or 'NORMAL'
        qty = self._to_decimal(row.get('qty') or row.get('order_qty') or row.get('quantity'))
        price = self._to_decimal(row.get('price') or row.get('price_limit') or row.get('submitted_price'))
        status = self._normalize_order_status(row.get('order_status') or row.get('status'))
        submitted_at = self._to_datetime(row.get('create_time') or row.get('submitted_at')) or datetime.now()
        updated_at = self._to_datetime(row.get('updated_time') or row.get('last_err_msg_time')) or submitted_at
        reject_reason = self._string_or_none(row.get('last_err_msg') or row.get('reject_reason'))

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO broker_orders (
                    signal_id, broker, account_type, broker_order_id, symbol, side,
                    order_type, qty, price, status, submitted_at, updated_at, reject_reason, raw_payload
                ) VALUES (
                    NULL, 'futu', 'futu_sim', %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    symbol = VALUES(symbol),
                    side = VALUES(side),
                    order_type = VALUES(order_type),
                    qty = VALUES(qty),
                    price = VALUES(price),
                    status = VALUES(status),
                    updated_at = VALUES(updated_at),
                    reject_reason = COALESCE(VALUES(reject_reason), reject_reason),
                    raw_payload = JSON_MERGE_PATCH(COALESCE(raw_payload, JSON_OBJECT()), VALUES(raw_payload))
                """,
                (
                    broker_order_id,
                    symbol,
                    side,
                    order_type,
                    qty,
                    price,
                    status,
                    submitted_at,
                    updated_at,
                    reject_reason,
                    json.dumps({'futu_order': row}, ensure_ascii=False, default=str),
                ),
            )
            return 1

    def upsert_broker_order_from_paper_order(self, row: Dict[str, Any]) -> int:
        broker_order_id = self._string_or_none(row.get('futu_order_id') or row.get('id'))
        if not broker_order_id:
            return 0

        symbol = self._string_or_none(row.get('symbol')) or 'UNKNOWN'
        side = self._normalize_side(row.get('order_type'))
        order_type = 'NORMAL'
        qty = self._to_decimal(row.get('quantity'))
        price = self._to_decimal(row.get('price'))
        status = self._normalize_order_status(row.get('status'))
        submitted_at = self._to_datetime(row.get('created_at')) or datetime.now()
        updated_at = self._to_datetime(row.get('updated_at') or row.get('filled_at') or row.get('created_at')) or submitted_at
        filled_quantity = self._to_decimal(row.get('filled_quantity'))
        filled_price = self._to_decimal(row.get('filled_price'))
        filled_at = self._to_datetime(row.get('filled_at'))
        reject_reason = None
        if status == 'cancelled' and row.get('status') == 'expired':
            reject_reason = 'paper_order expired by order polling'

        raw_payload = {
            'paper_order': {
                'paper_order_id': row.get('id'),
                'source_signal_id': row.get('source_signal_id'),
                'symbol': symbol,
                'order_type': row.get('order_type'),
                'quantity': float(qty),
                'price': float(price) if price is not None else None,
                'status': row.get('status'),
                'normalized_status': status,
                'filled_quantity': float(filled_quantity),
                'filled_price': float(filled_price) if filled_quantity > 0 else None,
                'filled_at': filled_at.isoformat() if filled_at else None,
                'created_at': submitted_at.isoformat() if submitted_at else None,
                'updated_at': updated_at.isoformat() if updated_at else None,
            }
        }

        strategy_signal_id = self._resolve_strategy_signal_id(row.get('source_signal_id'))

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO broker_orders (
                    signal_id, broker, account_type, broker_order_id, symbol, side,
                    order_type, qty, price, status, submitted_at, updated_at, reject_reason, raw_payload
                ) VALUES (
                    %s, 'futu', 'futu_sim', %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    signal_id = COALESCE(broker_orders.signal_id, VALUES(signal_id)),
                    symbol = VALUES(symbol),
                    side = VALUES(side),
                    order_type = VALUES(order_type),
                    qty = VALUES(qty),
                    price = VALUES(price),
                    status = VALUES(status),
                    submitted_at = LEAST(submitted_at, VALUES(submitted_at)),
                    updated_at = GREATEST(updated_at, VALUES(updated_at)),
                    reject_reason = COALESCE(VALUES(reject_reason), reject_reason),
                    raw_payload = JSON_MERGE_PATCH(COALESCE(raw_payload, JSON_OBJECT()), VALUES(raw_payload))
                """,
                (
                    strategy_signal_id,
                    broker_order_id,
                    symbol,
                    side,
                    order_type,
                    qty,
                    price,
                    status,
                    submitted_at,
                    updated_at,
                    reject_reason,
                    json.dumps(raw_payload, ensure_ascii=False, default=str),
                ),
            )
            return 1

    def upsert_broker_fill_from_row(self, row: Dict[str, Any]) -> int:
        broker_order_id = self._string_or_none(row.get('order_id') or row.get('broker_order_id'))
        if not broker_order_id:
            return 0
        broker_fill_id = self._string_or_none(row.get('deal_id') or row.get('fill_id') or row.get('id'))
        if not broker_fill_id:
            broker_fill_id = f"{broker_order_id}:{self._string_or_none(row.get('create_time') or datetime.now().isoformat())}"

        symbol = self._string_or_none(row.get('code') or row.get('symbol')) or 'UNKNOWN'
        side = self._normalize_side(row.get('trd_side') or row.get('side'))
        fill_price = self._to_decimal(row.get('price') or row.get('dealt_avg_price') or row.get('fill_price'))
        fill_qty = self._to_decimal(row.get('qty') or row.get('deal_qty') or row.get('fill_qty'))
        fill_time = self._to_datetime(row.get('create_time') or row.get('updated_time')) or datetime.now()

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO broker_fills (
                    broker, broker_order_id, broker_fill_id, symbol, side, fill_price, fill_qty, fill_time, raw_payload
                ) VALUES (
                    'futu', %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    symbol = VALUES(symbol),
                    side = VALUES(side),
                    fill_price = VALUES(fill_price),
                    fill_qty = VALUES(fill_qty),
                    fill_time = VALUES(fill_time),
                    raw_payload = VALUES(raw_payload)
                """,
                (
                    broker_order_id,
                    broker_fill_id,
                    symbol,
                    side,
                    fill_price,
                    fill_qty,
                    fill_time,
                    json.dumps({'futu_fill': row}, ensure_ascii=False, default=str),
                ),
            )
            return 1

    def upsert_broker_fill_from_paper_order(self, row: Dict[str, Any]) -> int:
        broker_order_id = self._string_or_none(row.get('futu_order_id') or row.get('id'))
        fill_qty = self._to_decimal(row.get('filled_quantity'))
        if not broker_order_id or fill_qty <= 0:
            return 0

        fill_time = self._to_datetime(row.get('filled_at') or row.get('updated_at') or row.get('created_at')) or datetime.now()
        fill_price = self._to_decimal(row.get('filled_price') or row.get('price'))
        symbol = self._string_or_none(row.get('symbol')) or 'UNKNOWN'
        side = self._normalize_side(row.get('order_type'))
        broker_fill_id = f'paper-order-fill:{broker_order_id}:{fill_time.isoformat()}'

        raw_payload = {
            'fill_source': 'paper_orders_fallback',
            'paper_order_id': row.get('id'),
            'source_signal_id': row.get('source_signal_id'),
            'status': row.get('status'),
            'filled_quantity': float(fill_qty),
            'filled_price': float(fill_price),
            'filled_at': fill_time.isoformat(),
        }

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO broker_fills (
                    broker, broker_order_id, broker_fill_id, symbol, side, fill_price, fill_qty, fill_time, raw_payload
                ) VALUES (
                    'futu', %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON DUPLICATE KEY UPDATE
                    symbol = VALUES(symbol),
                    side = VALUES(side),
                    fill_price = VALUES(fill_price),
                    fill_qty = VALUES(fill_qty),
                    fill_time = VALUES(fill_time),
                    raw_payload = VALUES(raw_payload)
                """,
                (
                    broker_order_id,
                    broker_fill_id,
                    symbol,
                    side,
                    fill_price,
                    fill_qty,
                    fill_time,
                    json.dumps(raw_payload, ensure_ascii=False, default=str),
                ),
            )
            return 1

    def insert_position_snapshot(self, row: Dict[str, Any], snapshot_time: datetime) -> None:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO broker_positions_snapshot (
                    snapshot_time, broker, account_type, symbol, qty, avg_cost,
                    market_price, market_value, unrealized_pnl, realized_pnl, raw_payload
                ) VALUES (
                    %s, 'futu', 'futu_sim', %s, %s, %s,
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    snapshot_time,
                    self._string_or_none(row.get('code') or row.get('symbol')) or 'UNKNOWN',
                    self._to_decimal(row.get('qty') or row.get('can_sell_qty') or 0),
                    self._to_decimal(row.get('cost_price') or row.get('average_cost') or row.get('avg_cost')),
                    self._to_decimal(row.get('nominal_price') or row.get('market_price') or row.get('price')),
                    self._to_decimal(row.get('market_val') or row.get('market_value')),
                    self._to_decimal(row.get('pl_val') or row.get('unrealized_pnl')),
                    self._to_decimal(row.get('realized_pl_val') or row.get('realized_pnl')),
                    json.dumps(row, ensure_ascii=False, default=str),
                ),
            )

    def insert_equity_snapshot(self, row: Dict[str, Any], snapshot_time: datetime) -> None:
        equity = self._to_decimal(row.get('total_assets') or row.get('power') or row.get('equity') or 0)
        cash = self._to_decimal(row.get('cash') or row.get('cash_balance') or row.get('avl_withdrawal_cash'))
        market_value = self._to_decimal(row.get('market_val') or row.get('market_value'))
        realized_pnl = self._to_decimal(row.get('realized_pl') or row.get('realized_pnl'))
        unrealized_pnl = self._to_decimal(row.get('pl_val') or row.get('unrealized_pnl'))
        high_water_mark = self._fetch_high_water_mark()
        drawdown_pct = None
        if high_water_mark and high_water_mark > 0 and equity is not None:
            high_water_mark_dec = Decimal(str(high_water_mark))
            drawdown_pct = float((high_water_mark_dec - equity) / high_water_mark_dec)

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO account_equity_snapshots (
                    snapshot_time, broker, account_type, cash, equity, market_value,
                    realized_pnl, unrealized_pnl, drawdown_pct, raw_payload
                ) VALUES (
                    %s, 'futu', 'futu_sim', %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    snapshot_time,
                    cash,
                    equity or Decimal('0'),
                    market_value,
                    realized_pnl,
                    unrealized_pnl,
                    drawdown_pct,
                    json.dumps(row, ensure_ascii=False, default=str),
                ),
            )

    def get_checkpoint_time(self, sync_name: str) -> datetime | None:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT checkpoint_time FROM sync_checkpoints WHERE sync_name = %s', (sync_name,))
            row = cursor.fetchone()
            return row['checkpoint_time'] if row else None

    def upsert_checkpoint(self, sync_name: str, *, checkpoint_time: datetime | None, checkpoint_value: str | None = None) -> None:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sync_checkpoints (sync_name, checkpoint_value, checkpoint_time)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    checkpoint_value = VALUES(checkpoint_value),
                    checkpoint_time = VALUES(checkpoint_time)
                """,
                (sync_name, checkpoint_value, checkpoint_time),
            )

    def fetch_open_lifecycles(self) -> List[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM trade_lifecycles
                WHERE status IN ('signal_created', 'order_submitted', 'partially_filled', 'filled_open', 'exit_pending')
                ORDER BY id ASC
                """
            )
            return cursor.fetchall() or []

    def _resolve_strategy_signal_id(self, signal_id: Any) -> int | None:
        if signal_id in (None, '', 0, '0'):
            return None
        try:
            candidate = int(signal_id)
        except Exception:
            return None
        with get_db_cursor() as cursor:
            cursor.execute('SELECT id FROM strategy_signals WHERE id = %s LIMIT 1', (candidate,))
            row = cursor.fetchone()
            return int(row['id']) if row else None

    def fetch_all_broker_orders(self) -> List[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM broker_orders ORDER BY submitted_at ASC, id ASC')
            return cursor.fetchall() or []

    def fetch_fills_grouped_by_order(self) -> Dict[str, List[Dict[str, Any]]]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM broker_fills ORDER BY fill_time ASC, id ASC')
            rows = cursor.fetchall() or []
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row['broker_order_id'])].append(row)
        return grouped

    def update_lifecycle(self, lifecycle_id: int, updates: Dict[str, Any]) -> None:
        if not updates:
            return
        allowed = {
            'entry_price', 'exit_price', 'entry_time', 'exit_time', 'position_qty', 'status',
            'exit_reason', 'pnl', 'pnl_pct', 'holding_minutes', 'rr', 'entry_order_id', 'exit_order_id'
        }
        parts = []
        values = []
        for key, value in updates.items():
            if key not in allowed:
                continue
            parts.append(f'{key} = %s')
            values.append(value)
        if not parts:
            return
        values.append(lifecycle_id)
        sql = f"UPDATE trade_lifecycles SET {', '.join(parts)}, updated_at = NOW() WHERE id = %s"
        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(values))

    def find_order_by_id(self, orders: Iterable[Dict[str, Any]], order_id: Any) -> Optional[Dict[str, Any]]:
        if order_id is None:
            return None
        for row in orders:
            if row.get('id') == order_id:
                return row
        return None

    def _match_exit_side(
        self,
        lifecycle: Dict[str, Any],
        orders: List[Dict[str, Any]],
        fills_by_order: Dict[str, List[Dict[str, Any]]],
        exit_side: str,
        entry_time: datetime | None,
    ) -> tuple[Optional[Dict[str, Any]], Decimal, Decimal | None, datetime | None]:
        exit_orders: List[Dict[str, Any]] = []
        for order in orders:
            if order.get('symbol') != lifecycle.get('symbol'):
                continue
            if order.get('side') != exit_side:
                continue
            if entry_time and order.get('submitted_at') and order['submitted_at'] < entry_time:
                continue
            if lifecycle.get('exit_order_id') and order.get('id') == lifecycle.get('exit_order_id'):
                exit_orders.append(order)
                continue
            if lifecycle.get('entry_order_id') == order.get('id'):
                continue
            exit_orders.append(order)

        if not exit_orders:
            return None, Decimal('0'), None, None

        exit_orders.sort(key=lambda x: (x.get('submitted_at') or datetime.min, x.get('id') or 0))
        selected_order: Optional[Dict[str, Any]] = None
        required_qty = self._to_decimal(lifecycle.get('position_qty') or 0)
        aggregated_qty = Decimal('0')
        weighted_value = Decimal('0')
        latest_time = None
        for order in exit_orders:
            order_qty, order_price, order_time = self._resolve_order_execution(order, fills_by_order)
            if order_qty <= 0:
                if selected_order is None:
                    selected_order = order
                continue
            selected_order = order
            aggregated_qty += order_qty
            if order_price is not None:
                weighted_value += order_qty * order_price
            if order_time and (latest_time is None or order_time > latest_time):
                latest_time = order_time
            if required_qty and aggregated_qty >= required_qty:
                break

        avg_price = (weighted_value / aggregated_qty) if aggregated_qty > 0 else None
        return selected_order, aggregated_qty, avg_price, latest_time

    def _resolve_order_execution(
        self,
        order: Dict[str, Any],
        fills_by_order: Dict[str, List[Dict[str, Any]]],
    ) -> tuple[Decimal, Decimal | None, datetime | None]:
        fills = fills_by_order.get(str(order['broker_order_id']), [])
        qty, price, fill_time = self._aggregate_fills(fills)
        if qty > 0:
            return qty, price, fill_time
        return self._aggregate_order_level_fill(order)

    def _aggregate_order_level_fill(self, order: Dict[str, Any]) -> tuple[Decimal, Decimal | None, datetime | None]:
        raw_payload = order.get('raw_payload')
        payload: Dict[str, Any] = {}
        if isinstance(raw_payload, dict):
            payload = raw_payload
        elif isinstance(raw_payload, str) and raw_payload:
            try:
                payload = json.loads(raw_payload)
            except Exception:
                payload = {}

        paper_order = payload.get('paper_order') if isinstance(payload, dict) else None
        if isinstance(paper_order, dict):
            qty = self._to_decimal(paper_order.get('filled_quantity'))
            if qty > 0:
                price = self._to_decimal(paper_order.get('filled_price') or order.get('price'))
                fill_time = self._to_datetime(paper_order.get('filled_at') or paper_order.get('updated_at') or order.get('updated_at'))
                return qty, price, fill_time

        normalized_status = self._normalize_order_status(order.get('status'))
        if normalized_status in ('filled', 'partial_filled'):
            qty = self._to_decimal(order.get('qty'))
            price = self._to_decimal(order.get('price'))
            fill_time = self._to_datetime(order.get('updated_at') or order.get('submitted_at'))
            return qty, price, fill_time
        return Decimal('0'), None, None

    def _fetch_high_water_mark(self) -> float | None:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT MAX(equity) AS max_equity FROM account_equity_snapshots WHERE account_type = %s', ('futu_sim',))
            row = cursor.fetchone()
            if not row or row['max_equity'] is None:
                return None
            return float(row['max_equity'])

    def _aggregate_fills(self, fills: List[Dict[str, Any]]) -> tuple[Decimal, Decimal | None, datetime | None]:
        if not fills:
            return Decimal('0'), None, None
        total_qty = Decimal('0')
        total_value = Decimal('0')
        latest_time = None
        for row in fills:
            qty = self._to_decimal(row.get('fill_qty'))
            price = self._to_decimal(row.get('fill_price'))
            total_qty += qty
            total_value += qty * price
            fill_time = self._to_datetime(row.get('fill_time'))
            if fill_time and (latest_time is None or fill_time > latest_time):
                latest_time = fill_time
        avg_price = (total_value / total_qty) if total_qty > 0 else None
        return total_qty, avg_price, latest_time

    def _infer_exit_reason(self, lifecycle: Dict[str, Any], exit_price: Decimal | None) -> str:
        if exit_price is None:
            return 'manual'
        take_profit = self._to_decimal(lifecycle.get('take_profit')) if lifecycle.get('take_profit') is not None else None
        stop_loss = self._to_decimal(lifecycle.get('stop_loss')) if lifecycle.get('stop_loss') is not None else None
        if lifecycle.get('direction') == 'long':
            if take_profit is not None and exit_price >= take_profit:
                return 'take_profit'
            if stop_loss is not None and exit_price <= stop_loss:
                return 'stop_loss'
        else:
            if take_profit is not None and exit_price <= take_profit:
                return 'take_profit'
            if stop_loss is not None and exit_price >= stop_loss:
                return 'stop_loss'
        return 'manual'

    def _normalize_order_status(self, value: Any) -> str:
        if value is None:
            return 'submitted'
        raw = str(value).strip().lower().replace('_', ' ')
        return self.ORDER_STATUS_MAP.get(raw, raw.replace(' ', '_'))

    @staticmethod
    def _normalize_side(value: Any) -> str:
        raw = str(value or '').strip().lower()
        if 'buy' in raw:
            return 'buy'
        if 'sell' in raw:
            return 'sell'
        return 'buy'

    @staticmethod
    def _compute_pnl(direction: str, entry_price: Decimal | None, exit_price: Decimal | None, qty: Decimal) -> float | None:
        if entry_price is None or exit_price is None:
            return None
        diff = (exit_price - entry_price) if direction == 'long' else (entry_price - exit_price)
        return float(diff * qty)

    @staticmethod
    def _compute_pnl_pct(direction: str, entry_price: Decimal | None, pnl: float | None, qty: Decimal) -> float | None:
        if entry_price is None or pnl is None or qty <= 0:
            return None
        basis = float(entry_price * qty)
        if basis == 0:
            return None
        return pnl / basis

    @staticmethod
    def _compute_holding_minutes(entry_time: datetime | None, exit_time: datetime | None) -> int | None:
        if not entry_time or not exit_time:
            return None
        return max(0, int((exit_time - entry_time).total_seconds() // 60))

    def _compute_rr(self, lifecycle: Dict[str, Any], entry_price: Decimal | None, exit_price: Decimal | None) -> float | None:
        if entry_price is None or exit_price is None:
            return None
        stop_loss = self._to_decimal(lifecycle.get('stop_loss')) if lifecycle.get('stop_loss') is not None else None
        if stop_loss is None:
            return None
        if lifecycle.get('direction') == 'long':
            reward = exit_price - entry_price
            risk = entry_price - stop_loss
        else:
            reward = entry_price - exit_price
            risk = stop_loss - entry_price
        if risk <= 0:
            return None
        return float(reward / risk)

    @staticmethod
    def _to_datetime(value: Any) -> datetime | None:
        if value is None or value == '':
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip().replace('Z', '+00:00')
        for fmt in (None, '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S'):
            try:
                if fmt is None:
                    return datetime.fromisoformat(text)
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        return None

    @staticmethod
    def _to_decimal(value: Any) -> Decimal:
        if value is None or value == '':
            return Decimal('0')
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal('0')

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
