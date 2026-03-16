#!/usr/bin/env python3
import os
import sys
import unittest
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import paper_position_reconciliation as reconciliation


class PaperPositionReconciliationTest(unittest.TestCase):
    def test_rebuild_positions_from_orders_replays_buys_and_sells(self):
        orders = [
            {'id': 1, 'symbol': 'US.TSLA', 'order_type': 'BUY', 'filled_quantity': 10, 'filled_price': 100},
            {'id': 2, 'symbol': 'US.TSLA', 'order_type': 'BUY', 'filled_quantity': 20, 'filled_price': 110},
            {'id': 3, 'symbol': 'US.TSLA', 'order_type': 'SELL', 'filled_quantity': 12, 'filled_price': 120},
        ]

        with patch.object(reconciliation, 'fetch_filled_orders', return_value=orders):
            rebuilt = reconciliation.rebuild_positions_from_orders({'US.TSLA': 125})

        tsla = rebuilt['US.TSLA']
        self.assertEqual(tsla.quantity, 18)
        self.assertAlmostEqual(tsla.average_cost, 106.6667, places=4)
        self.assertAlmostEqual(tsla.realized_pnl, 160.0, places=2)
        self.assertAlmostEqual(tsla.market_value, 2250.0, places=2)
        self.assertAlmostEqual(tsla.unrealized_pnl, 330.0, places=2)

    def test_rebuild_positions_from_orders_rejects_oversell(self):
        orders = [
            {'id': 1, 'symbol': 'US.TSLA', 'order_type': 'SELL', 'filled_quantity': 1, 'filled_price': 100},
        ]

        with patch.object(reconciliation, 'fetch_filled_orders', return_value=orders):
            with self.assertRaises(ValueError):
                reconciliation.rebuild_positions_from_orders({})


if __name__ == '__main__':
    unittest.main()
