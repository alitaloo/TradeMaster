#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.signal_consumer import SignalConsumer
from scripts import fox_analysis_v2 as fox


class RecordingRepository:
    def __init__(self, submitted_today=0, open_lifecycle=None, pending_order=None):
        self.submitted_today = submitted_today
        self.open_lifecycle = open_lifecycle
        self.pending_order = pending_order
        self.inserted_signals = []
        self.status_updates = []
        self.lifecycle_updates = []
        self.inserted_orders = []

    def get_signal_by_hash(self, *_args, **_kwargs):
        return None

    def insert_signal(self, signal):
        self.inserted_signals.append(signal)
        return 101

    def update_signal_status(self, *args, **kwargs):
        self.status_updates.append((args, kwargs))
        return None

    def upsert_lifecycle(self, **kwargs):
        self.lifecycle_updates.append(kwargs)
        return 201

    def find_open_lifecycle(self, *_args, **_kwargs):
        return self.open_lifecycle

    def find_pending_order(self, *_args, **_kwargs):
        return self.pending_order

    def count_submitted_signals_for_day(self, *_args, **_kwargs):
        return self.submitted_today

    def insert_broker_order(self, **kwargs):
        self.inserted_orders.append(kwargs)
        return 301


class FakeAdapter:
    def submit_order(self, **_kwargs):
        return {
            'success': True,
            'broker': 'futu',
            'broker_order_id': 'SIM-1',
            'status': 'submitted',
        }


class SignalConsumerStage15IntegrationTest(unittest.TestCase):
    def base_signal(self):
        return {
            'strategy_name': 'fox_analysis_v2',
            'symbol': 'AAPL',
            'action': 'buy',
            'entry_price': 100,
            'stop_loss': 95,
            'take_profit': 110,
            'confidence': 0.8,
            'strength': 'strong',
            'signal_time': datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc).isoformat(),
            '1h_trend': 'bearish',
            'confidence_tier': 'high',
            'reasons': ['TopK consensus', '1h aligned'],
        }

    def test_trend_veto_blocks_conflicting_trade(self):
        repo = RecordingRepository()
        consumer = SignalConsumer(
            repository=repo,
            adapter=FakeAdapter(),
            trend_veto_enabled=True,
            per_day_trade_cap=0,
        )
        result = consumer.process_signal(self.base_signal())
        self.assertEqual(result['decision'], 'ignored')
        self.assertIn('trend veto', result['message'])
        self.assertEqual(result['details']['trend_veto']['trend'], 'bearish')
        self.assertEqual(repo.inserted_signals[0]['reasons'], ['TopK consensus', '1h aligned'])

    def test_daily_trade_cap_blocks_after_limit(self):
        consumer = SignalConsumer(
            repository=RecordingRepository(submitted_today=2),
            adapter=FakeAdapter(),
            trend_veto_enabled=False,
            per_day_trade_cap=2,
        )
        signal = self.base_signal()
        signal['1h_trend'] = 'bullish'
        result = consumer.process_signal(signal)
        self.assertEqual(result['decision'], 'ignored')
        self.assertIn('daily trade cap reached', result['message'])
        self.assertEqual(result['details']['per_day_trade_cap']['submitted_today'], 2)

    def test_legacy_fox_metadata_contract_is_ingested_end_to_end(self):
        repo = RecordingRepository()
        consumer = SignalConsumer(
            repository=repo,
            adapter=FakeAdapter(),
            trend_veto_enabled=True,
            trend_veto_required_tf='1h',
            per_day_trade_cap=0,
            min_confidence=0.6,
            min_confidence_tier='high',
        )
        legacy_signal = {
            'strategy_type': 'fox_analysis_v2',
            'signal_type': 'BUY',
            'symbol': 'TSLA',
            'price': 250,
            'quantity': 3,
            'confidence': 0.82,
            'created_at': datetime(2026, 3, 10, 10, 0, tzinfo=timezone.utc).isoformat(),
            'metadata': {
                'reason': 'TopK 共識 (BUY)',
                'reasons': ['TopK consensus', 'macro tailwind'],
                'trend_tf': '1h',
                '1h_trend': 'BUY',
                '1d_trend': 'BUY',
                'confidence_tier': 'high',
                'strength': 'strong',
                'take_profit': 280,
                'stop_loss': 235,
            }
        }

        result = consumer.process_signal(legacy_signal)

        self.assertEqual(result['decision'], 'submitted')
        self.assertEqual(result['lifecycle_status'], 'order_submitted')
        inserted = repo.inserted_signals[0]
        self.assertEqual(inserted['action'], 'buy')
        self.assertEqual(inserted['symbol'], 'US.TSLA')
        self.assertEqual(inserted['confidence_tier'], 'high')
        self.assertEqual(inserted['strength'], 'strong')
        self.assertEqual(inserted['trend_tf'], '1h')
        self.assertEqual(inserted['trend_value'], 'bullish')
        self.assertEqual(inserted['stop_loss'], 235.0)
        self.assertEqual(inserted['take_profit'], 280.0)
        self.assertEqual(inserted['reasons'], ['TopK consensus', 'macro tailwind'])
        self.assertEqual(inserted['metadata']['contract_version'], 'stage1.5')
        self.assertEqual(repo.inserted_orders[0]['signal']['confidence_tier'], 'high')

    def test_mandatory_gates_still_win_after_new_contract_fields(self):
        repo = RecordingRepository(open_lifecycle={'id': 77, 'status': 'filled_open'})
        consumer = SignalConsumer(
            repository=repo,
            adapter=FakeAdapter(),
            trend_veto_enabled=True,
            per_day_trade_cap=0,
            min_confidence_tier='medium',
        )
        signal = self.base_signal()
        signal['1h_trend'] = 'bullish'
        signal['metadata'] = {
            'confidence_tier': 'high',
            'strength': 'strong',
            'reasons': ['aligned'],
        }

        result = consumer.process_signal(signal)

        self.assertEqual(result['decision'], 'ignored')
        self.assertIn('open lifecycle exists', result['message'])
        self.assertEqual(result['lifecycle_status'], 'signal_created')


class FoxStage1Test(unittest.TestCase):
    def test_apply_rsi_profile_tighter(self):
        with patch.object(fox, 'get_runtime_setting', return_value='tighter'):
            params = fox.apply_rsi_profile('RSI', {'period': 14, 'oversold': 30, 'overbought': 70})
        self.assertEqual(params['oversold'], 25)
        self.assertEqual(params['overbought'], 75)

    def test_calculate_confidence_returns_tier_and_strength(self):
        result = fox.calculate_confidence(
            {'return_pct': 12},
            {'total_weight': 0, 'breakdown': {'positive': 2, 'negative': 0}},
            {'vix': 14, 'market_drop': 1.5},
            tf_signals={'consensus': 'BUY', '1h': 'BUY', '1d': 'BUY'},
        )
        self.assertGreaterEqual(result['confidence'], 0.85)
        self.assertEqual(result['confidence_tier'], 'very_high')
        self.assertEqual(result['strength'], 'very_strong')


if __name__ == '__main__':
    unittest.main()
