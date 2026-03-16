#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import paper_trading


class FakeOrder:
    def __init__(self, order_id=1, symbol='US.AAPL', order_type='BUY', quantity=100, price=150.0,
                 status='pending', futu_order_id='FT-1', filled_quantity=0, filled_price=None, filled_at=None):
        self.id = order_id
        self.symbol = symbol
        self.order_type = order_type
        self.quantity = quantity
        self.price = price
        self.status = status
        self.futu_order_id = futu_order_id
        self.filled_quantity = filled_quantity
        self.filled_price = filled_price
        self.filled_at = filled_at

    def to_dict(self):
        return {
            'id': self.id,
            'symbol': self.symbol,
            'order_type': self.order_type,
            'quantity': self.quantity,
            'price': self.price,
            'status': self.status,
            'futu_order_id': self.futu_order_id,
            'filled_quantity': self.filled_quantity,
            'filled_price': self.filled_price,
            'filled_at': self.filled_at,
        }


class PartialOrderPollingTest(unittest.TestCase):
    def test_pending_partial_filled_updates_progressively(self):
        order = FakeOrder(status='pending')
        poll_rows = iter([
            {
                'futu_order_id': 'FT-1',
                'order_status': 'SUBMITTED',
                'filled_quantity': 0,
                'filled_price': None,
                'filled_at': None,
            },
            {
                'futu_order_id': 'FT-1',
                'order_status': 'FILLED_PART',
                'filled_quantity': 30,
                'filled_price': 150.10,
                'filled_at': '2026-03-09 10:00:00',
            },
            {
                'futu_order_id': 'FT-1',
                'order_status': 'FILLED_PART',
                'filled_quantity': 70,
                'filled_price': 150.25,
                'filled_at': '2026-03-09 10:01:00',
            },
            {
                'futu_order_id': 'FT-1',
                'order_status': 'FILLED_ALL',
                'filled_quantity': 100,
                'filled_price': 150.40,
                'filled_at': '2026-03-09 10:02:00',
            },
        ])
        updates = []
        buy_fills = []

        def fake_query_order_status(_futu_order_id):
            return next(poll_rows)

        def fake_update_order_status(order_id, status, filled_quantity=0, filled_price=None, filled_at=None):
            updates.append({
                'order_id': order_id,
                'status': status,
                'filled_quantity': filled_quantity,
                'filled_price': filled_price,
                'filled_at': filled_at,
            })
            order.status = status
            order.filled_quantity = filled_quantity
            order.filled_price = filled_price
            order.filled_at = filled_at
            return True

        with patch.object(paper_trading.PaperOrder, 'find_pending', side_effect=[[order], [order], [order], [order]]), \
             patch.object(paper_trading, 'query_order_status', side_effect=fake_query_order_status), \
             patch.object(paper_trading, 'update_order_status', side_effect=fake_update_order_status), \
             patch.object(paper_trading, 'handle_buy_fill', side_effect=lambda order_id: buy_fills.append(order_id) or True), \
             patch.object(paper_trading, 'handle_sell_fill', return_value=True), \
             patch.object(paper_trading, 'reconcile_paper_positions', return_value={'applied': True}):
            snapshots = [paper_trading.poll_paper_orders()[0] for _ in range(4)]

        self.assertEqual([row['status'] for row in snapshots], ['pending', 'partial', 'partial', 'filled'])
        self.assertEqual([row['filled_quantity'] for row in snapshots], [0, 30, 70, 100])
        self.assertEqual([row['filled_price'] for row in snapshots], [None, 150.10, 150.25, 150.40])
        self.assertEqual([row['filled_at'] for row in snapshots], [None, '2026-03-09 10:00:00', '2026-03-09 10:01:00', '2026-03-09 10:02:00'])
        self.assertEqual([u['status'] for u in updates], ['pending', 'partial', 'partial', 'filled'])
        self.assertEqual(buy_fills, [1])

    def test_pending_partial_cancelled_keeps_last_fill_progress(self):
        order = FakeOrder(status='pending')
        poll_rows = iter([
            {
                'futu_order_id': 'FT-1',
                'order_status': 'FILLED_PART',
                'filled_quantity': 40,
                'filled_price': 149.80,
                'filled_at': '2026-03-09 11:00:00',
            },
            {
                'futu_order_id': 'FT-1',
                'order_status': 'CANCELLED_PART',
                'filled_quantity': 40,
                'filled_price': 149.80,
                'filled_at': '2026-03-09 11:00:00',
            },
        ])
        updates = []

        def fake_query_order_status(_futu_order_id):
            return next(poll_rows)

        def fake_update_order_status(order_id, status, filled_quantity=0, filled_price=None, filled_at=None):
            updates.append((status, filled_quantity, filled_price, filled_at))
            order.status = status
            order.filled_quantity = filled_quantity
            order.filled_price = filled_price
            order.filled_at = filled_at
            return True

        with patch.object(paper_trading.PaperOrder, 'find_pending', side_effect=[[order], [order]]), \
             patch.object(paper_trading, 'query_order_status', side_effect=fake_query_order_status), \
             patch.object(paper_trading, 'update_order_status', side_effect=fake_update_order_status), \
             patch.object(paper_trading, 'handle_buy_fill', return_value=True), \
             patch.object(paper_trading, 'handle_sell_fill', return_value=True), \
             patch.object(paper_trading, 'reconcile_paper_positions', return_value={'applied': True}):
            partial_snapshot = paper_trading.poll_paper_orders()[0]
            cancelled_snapshot = paper_trading.poll_paper_orders()[0]

        self.assertEqual(partial_snapshot['status'], 'partial')
        self.assertEqual(cancelled_snapshot['status'], 'cancelled')
        self.assertEqual(cancelled_snapshot['filled_quantity'], 40)
        self.assertEqual(cancelled_snapshot['filled_price'], 149.80)
        self.assertEqual(cancelled_snapshot['filled_at'], '2026-03-09 11:00:00')
        self.assertEqual(updates, [
            ('partial', 40, 149.8, '2026-03-09 11:00:00'),
            ('cancelled', 40, 149.8, '2026-03-09 11:00:00'),
        ])

    def test_pending_partial_failed_keeps_last_fill_progress(self):
        order = FakeOrder(status='pending')
        poll_rows = iter([
            {
                'futu_order_id': 'FT-1',
                'order_status': 'FILLED_PART',
                'filled_quantity': 20,
                'filled_price': 151.20,
                'filled_at': '2026-03-09 12:00:00',
            },
            {
                'futu_order_id': 'FT-1',
                'order_status': 'FAILED',
                'filled_quantity': 20,
                'filled_price': 151.20,
                'filled_at': '2026-03-09 12:00:00',
            },
        ])
        updates = []

        def fake_query_order_status(_futu_order_id):
            return next(poll_rows)

        def fake_update_order_status(order_id, status, filled_quantity=0, filled_price=None, filled_at=None):
            updates.append((status, filled_quantity, filled_price, filled_at))
            order.status = status
            order.filled_quantity = filled_quantity
            order.filled_price = filled_price
            order.filled_at = filled_at
            return True

        with patch.object(paper_trading.PaperOrder, 'find_pending', side_effect=[[order], [order]]), \
             patch.object(paper_trading, 'query_order_status', side_effect=fake_query_order_status), \
             patch.object(paper_trading, 'update_order_status', side_effect=fake_update_order_status), \
             patch.object(paper_trading, 'handle_buy_fill', return_value=True), \
             patch.object(paper_trading, 'handle_sell_fill', return_value=True), \
             patch.object(paper_trading, 'reconcile_paper_positions', return_value={'applied': True}):
            partial_snapshot = paper_trading.poll_paper_orders()[0]
            failed_snapshot = paper_trading.poll_paper_orders()[0]

        self.assertEqual(partial_snapshot['status'], 'partial')
        self.assertEqual(failed_snapshot['status'], 'failed')
        self.assertEqual(failed_snapshot['filled_quantity'], 20)
        self.assertEqual(failed_snapshot['filled_price'], 151.20)
        self.assertEqual(failed_snapshot['filled_at'], '2026-03-09 12:00:00')
        self.assertEqual(updates, [
            ('partial', 20, 151.2, '2026-03-09 12:00:00'),
            ('failed', 20, 151.2, '2026-03-09 12:00:00'),
        ])

    def test_query_order_surfaces_latest_partial_fill_fields(self):
        order = FakeOrder(
            order_id=9,
            status='partial',
            filled_quantity=30,
            filled_price=150.10,
            filled_at='2026-03-09 10:00:00',
        )

        with patch.object(paper_trading.PaperOrder, 'find_by_id', return_value=order), \
             patch.object(paper_trading, 'query_order_status', return_value={
                 'futu_order_id': 'FT-1',
                 'order_status': 'FILLED_PART',
                 'filled_quantity': 70,
                 'filled_price': 150.25,
                 'filled_at': '2026-03-09 10:01:00',
             }):
            payload = paper_trading.query_order(9)

        self.assertEqual(payload['status'], 'partial')
        self.assertEqual(payload['broker_status'], 'FILLED_PART')
        self.assertEqual(payload['filled_quantity'], 70)
        self.assertEqual(payload['filled_price'], 150.25)
        self.assertEqual(payload['filled_at'], '2026-03-09 10:01:00')


if __name__ == '__main__':
    unittest.main()
