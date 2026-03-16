#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime
from decimal import Decimal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.futu_sync_service import FutuSyncService


class FutuSyncServiceStage4Test(unittest.TestCase):
    def test_refresh_marks_exit_pending_when_exit_order_submitted_without_fill(self):
        service = FutuSyncService(adapter=None)
        orders = [
            {
                'id': 1,
                'broker_order_id': 'ENTRY-1',
                'symbol': 'US.TSLA',
                'side': 'buy',
                'status': 'filled',
                'qty': Decimal('2'),
                'price': Decimal('300'),
                'submitted_at': datetime(2026, 3, 10, 9, 0, 0),
                'updated_at': datetime(2026, 3, 10, 9, 0, 30),
                'raw_payload': {},
            },
            {
                'id': 2,
                'broker_order_id': 'EXIT-1',
                'symbol': 'US.TSLA',
                'side': 'sell',
                'status': 'submitted',
                'qty': Decimal('2'),
                'price': Decimal('299.5'),
                'submitted_at': datetime(2026, 3, 10, 16, 8, 0),
                'updated_at': datetime(2026, 3, 10, 16, 8, 5),
                'raw_payload': {},
            },
        ]
        lifecycles = [{
            'id': 10,
            'symbol': 'US.TSLA',
            'direction': 'long',
            'entry_order_id': 1,
            'exit_order_id': None,
            'status': 'filled_open',
            'position_qty': Decimal('2'),
            'take_profit': None,
            'stop_loss': None,
        }]
        applied = []
        service.fetch_all_broker_orders = lambda: orders
        service.fetch_fills_grouped_by_order = lambda: {'ENTRY-1': [{'fill_qty': Decimal('2'), 'fill_price': Decimal('300'), 'fill_time': datetime(2026, 3, 10, 9, 0, 30)}]}
        service.fetch_open_lifecycles = lambda: lifecycles
        service.update_lifecycle = lambda lifecycle_id, updates: applied.append((lifecycle_id, updates))

        updated = service.refresh_trade_lifecycles()

        self.assertEqual(updated, 1)
        self.assertEqual(applied[0][0], 10)
        self.assertEqual(applied[0][1]['status'], 'exit_pending')
        self.assertEqual(applied[0][1]['exit_order_id'], 2)


    def test_sync_external_order_ref_promotes_fill_and_closes_lifecycle(self):
        service = FutuSyncService(adapter=None)
        orders = [
            {
                'id': 1,
                'broker_order_id': 'ENTRY-1',
                'symbol': 'US.TSLA',
                'side': 'buy',
                'status': 'filled',
                'qty': Decimal('2'),
                'price': Decimal('300'),
                'submitted_at': datetime(2026, 3, 10, 9, 0, 0),
                'updated_at': datetime(2026, 3, 10, 9, 0, 30),
                'raw_payload': {},
            },
            {
                'id': 2,
                'broker_order_id': 'EXIT-2',
                'symbol': 'US.TSLA',
                'side': 'sell',
                'status': 'filled',
                'qty': Decimal('2'),
                'price': Decimal('310'),
                'submitted_at': datetime(2026, 3, 10, 16, 8, 0),
                'updated_at': datetime(2026, 3, 10, 16, 8, 5),
                'raw_payload': {},
            },
        ]
        lifecycle = {
            'id': 10,
            'symbol': 'US.TSLA',
            'direction': 'long',
            'entry_order_id': 1,
            'exit_order_id': None,
            'status': 'filled_open',
            'position_qty': Decimal('2'),
            'take_profit': None,
            'stop_loss': None,
        }
        paper_order = {
            'id': 99,
            'futu_order_id': 'EXIT-2',
            'symbol': 'US.TSLA',
            'order_type': 'SELL',
            'quantity': Decimal('2'),
            'price': Decimal('310'),
            'status': 'filled',
            'filled_quantity': Decimal('2'),
            'filled_price': Decimal('310'),
            'filled_at': datetime(2026, 3, 10, 16, 9, 0),
            'updated_at': datetime(2026, 3, 10, 16, 9, 0),
            'created_at': datetime(2026, 3, 10, 16, 8, 0),
            'source_signal_id': 501,
        }
        applied = []
        fill_rows = {
            'ENTRY-1': [{'fill_qty': Decimal('2'), 'fill_price': Decimal('300'), 'fill_time': datetime(2026, 3, 10, 9, 0, 30)}],
            'EXIT-2': [{'fill_qty': Decimal('2'), 'fill_price': Decimal('310'), 'fill_time': datetime(2026, 3, 10, 16, 9, 0)}],
        }
        service.fetch_paper_order_by_external_order_ref = lambda ref: dict(paper_order) if ref == 'EXIT-2' else None
        service.fetch_broker_order_by_external_order_ref = lambda ref: next((dict(o) for o in orders if o['broker_order_id'] == ref), None)
        service.fetch_trade_lifecycle_by_id = lambda lifecycle_id: dict(lifecycle) if lifecycle_id == 10 else None
        service.fetch_all_broker_orders = lambda: [dict(o) for o in orders]
        service.fetch_fills_grouped_by_order = lambda: fill_rows
        service.upsert_broker_order_from_paper_order = lambda row: 1
        service.upsert_broker_fill_from_paper_order = lambda row: 1
        service.update_lifecycle = lambda lifecycle_id, updates: applied.append((lifecycle_id, updates))

        result = service.sync_external_order_ref('EXIT-2', lifecycle_id=10)

        self.assertEqual(result['orders_upserted'], 1)
        self.assertEqual(result['fills_upserted'], 1)
        self.assertTrue(result['fill_detected'])
        self.assertEqual(result['lifecycles_updated'], 1)
        self.assertEqual(applied[0][0], 10)
        self.assertEqual(applied[0][1]['status'], 'closed')
        self.assertEqual(applied[0][1]['exit_order_id'], 2)


if __name__ == '__main__':
    unittest.main()
