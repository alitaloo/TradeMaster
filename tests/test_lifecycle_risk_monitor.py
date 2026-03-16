#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.risk_monitor import LifecycleRiskMonitor


class FakeCandidateRepository:
    def __init__(self):
        self.records = []
        self.next_id = 1

    def persist_candidate(self, candidate, *, detected_at, cooldown_seconds):
        for record in self.records:
            if record['lifecycle_id'] == candidate['lifecycle_id'] and record['candidate_type'] == candidate['candidate_type'] and record['status'] == 'active':
                action = 'cooldown_refreshed' if (detected_at - record['_last_detected_dt']).total_seconds() < cooldown_seconds else 'reactivated'
                record['_last_detected_dt'] = detected_at
                record['last_detected_at'] = detected_at.isoformat(sep=' ')
                record['current_price'] = candidate.get('current_price')
                record['threshold_value'] = candidate.get('threshold_value')
                record['threshold_source'] = candidate.get('threshold_source')
                record['reason'] = candidate.get('reason')
                record['detection_count'] += 1
                return {k: v for k, v in record.items() if not k.startswith('_')} | {'persist_action': action, 'cooldown_seconds': cooldown_seconds}

        record = {
            'id': self.next_id,
            'lifecycle_id': candidate['lifecycle_id'],
            'symbol': candidate['symbol'],
            'candidate_type': candidate['candidate_type'],
            'status': 'active',
            'first_detected_at': detected_at.isoformat(sep=' '),
            'last_detected_at': detected_at.isoformat(sep=' '),
            'current_price': candidate.get('current_price'),
            'threshold_value': candidate.get('threshold_value'),
            'threshold_source': candidate.get('threshold_source'),
            'reason': candidate.get('reason'),
            'detection_count': 1,
            '_last_detected_dt': detected_at,
        }
        self.records.append(record)
        self.next_id += 1
        return {k: v for k, v in record.items() if not k.startswith('_')} | {'persist_action': 'inserted', 'cooldown_seconds': cooldown_seconds}

    def resolve_absent_candidates(self, *, lifecycle_id, detected_types, resolved_at):
        resolved = 0
        detected_types = set(detected_types)
        for record in self.records:
            if record['lifecycle_id'] == lifecycle_id and record['status'] == 'active' and record['candidate_type'] not in detected_types:
                record['status'] = 'resolved'
                record['resolved_at'] = resolved_at.isoformat(sep=' ')
                resolved += 1
        return resolved

    def list_candidates(self, *, lifecycle_id=None, statuses=('active',), limit=200):
        rows = []
        for record in self.records:
            if lifecycle_id is not None and record['lifecycle_id'] != lifecycle_id:
                continue
            if statuses and record['status'] not in statuses:
                continue
            rows.append({k: v for k, v in record.items() if not k.startswith('_')})
        return rows[:limit]


class LifecycleRiskMonitorTest(unittest.TestCase):
    def test_detects_holding_timeout_and_stop_loss_with_lifecycle_priority(self):
        row = {
            'id': 101,
            'signal_id': 11,
            'symbol': 'US.AAPL',
            'strategy_name': 'trend_alpha',
            'status': 'filled_open',
            'direction': 'long',
            'entry_time': datetime(2026, 3, 10, 9, 0, 0),
            'entry_price': 100.0,
            'stop_loss': 95.0,
            'take_profit': 130.0,
            'signal_stop_loss': 94.0,
            'signal_take_profit': 140.0,
            'market_price': 94.5,
            'snapshot_qty': 10,
            'snapshot_time': datetime(2026, 3, 10, 13, 0, 0),
        }
        monitor = LifecycleRiskMonitor(now=datetime(2026, 3, 10, 13, 30, 0), repository=FakeCandidateRepository())

        result = monitor.evaluate_row(
            row,
            holding_enabled=True,
            max_holding_minutes=120,
            sltp_enabled=True,
            default_stop_loss_pct=0.1,
            default_take_profit_pct=0.2,
        )

        self.assertTrue(result['holding_timeout_hit'])
        self.assertTrue(result['stop_loss_hit'])
        self.assertFalse(result['take_profit_hit'])
        self.assertEqual(result['resolved_stop_loss'], 95.0)
        self.assertEqual(result['resolved_stop_loss_source'], 'lifecycle')
        self.assertEqual([c['candidate_type'] for c in result['candidates']], ['holding_timeout', 'stop_loss'])

    def test_scan_uses_signal_then_config_fallback_for_thresholds(self):
        rows = [
            {
                'id': 202,
                'signal_id': 22,
                'symbol': 'US.MSFT',
                'strategy_name': 'swing_beta',
                'status': 'filled_open',
                'direction': 'long',
                'entry_time': datetime(2026, 3, 10, 10, 0, 0),
                'entry_price': 100.0,
                'stop_loss': None,
                'take_profit': None,
                'signal_stop_loss': None,
                'signal_take_profit': 105.0,
                'market_price': 106.0,
                'snapshot_qty': 5,
                'snapshot_time': datetime(2026, 3, 10, 13, 0, 0),
            },
            {
                'id': 203,
                'signal_id': 23,
                'symbol': 'US.NVDA',
                'strategy_name': 'swing_beta',
                'status': 'filled_open',
                'direction': 'long',
                'entry_time': datetime(2026, 3, 10, 12, 0, 0),
                'entry_price': 100.0,
                'stop_loss': None,
                'take_profit': None,
                'signal_stop_loss': None,
                'signal_take_profit': None,
                'market_price': 89.0,
                'snapshot_qty': 3,
                'snapshot_time': datetime(2026, 3, 10, 13, 0, 0),
            },
        ]

        config_values = {
            'risk.holding_timeout_enabled': 'false',
            'risk.max_holding_minutes': None,
            'risk.max_holding_hours': None,
            'risk.active_sltp_detect_enabled': 'true',
            'risk.default_stop_loss_pct': '0.1',
            'risk.default_take_profit_pct': '0.2',
            'risk.exit_candidate_cooldown_seconds': '300',
        }

        def fake_get(key, default=None):
            return config_values.get(key, default)

        monitor = LifecycleRiskMonitor(now=datetime(2026, 3, 10, 13, 30, 0), repository=FakeCandidateRepository())
        with patch.object(LifecycleRiskMonitor, 'fetch_open_lifecycles', return_value=rows), \
             patch('execution.risk_monitor.SystemConfig.get', side_effect=fake_get):
            report = monitor.scan()

        self.assertEqual(report['summary']['candidate_count'], 2)
        self.assertEqual(report['summary']['take_profit_count'], 1)
        self.assertEqual(report['summary']['stop_loss_count'], 1)
        monitored_by_id = {row['lifecycle_id']: row for row in report['monitored']}
        self.assertEqual(monitored_by_id[202]['resolved_take_profit_source'], 'signal')
        self.assertEqual(monitored_by_id[203]['resolved_stop_loss_source'], 'config_pct')
        self.assertEqual(report['summary']['inserted_count'], 2)
        self.assertEqual(report['summary']['active_candidate_count'], 2)

    def test_cooldown_refresh_and_resolution_keep_state_ready_for_stage3(self):
        rows_first = [
            {
                'id': 301,
                'signal_id': 31,
                'symbol': 'US.TSLA',
                'strategy_name': 'risk_alpha',
                'status': 'filled_open',
                'direction': 'long',
                'entry_time': datetime(2026, 3, 10, 9, 0, 0),
                'entry_price': 100.0,
                'stop_loss': 95.0,
                'take_profit': None,
                'signal_stop_loss': None,
                'signal_take_profit': None,
                'market_price': 94.0,
                'snapshot_qty': 2,
                'snapshot_time': datetime(2026, 3, 10, 13, 0, 0),
            }
        ]
        rows_second = [
            {
                'id': 301,
                'signal_id': 31,
                'symbol': 'US.TSLA',
                'strategy_name': 'risk_alpha',
                'status': 'filled_open',
                'direction': 'long',
                'entry_time': datetime(2026, 3, 10, 9, 0, 0),
                'entry_price': 100.0,
                'stop_loss': 95.0,
                'take_profit': None,
                'signal_stop_loss': None,
                'signal_take_profit': None,
                'market_price': 97.0,
                'snapshot_qty': 2,
                'snapshot_time': datetime(2026, 3, 10, 13, 2, 0),
            }
        ]
        config_values = {
            'risk.holding_timeout_enabled': 'false',
            'risk.max_holding_minutes': None,
            'risk.max_holding_hours': None,
            'risk.active_sltp_detect_enabled': 'true',
            'risk.default_stop_loss_pct': None,
            'risk.default_take_profit_pct': None,
            'risk.exit_candidate_cooldown_seconds': '300',
        }

        def fake_get(key, default=None):
            return config_values.get(key, default)

        repository = FakeCandidateRepository()
        with patch('execution.risk_monitor.SystemConfig.get', side_effect=fake_get):
            monitor1 = LifecycleRiskMonitor(now=datetime(2026, 3, 10, 13, 0, 0), repository=repository)
            with patch.object(LifecycleRiskMonitor, 'fetch_open_lifecycles', return_value=rows_first):
                first = monitor1.scan()

            monitor2 = LifecycleRiskMonitor(now=datetime(2026, 3, 10, 13, 2, 0), repository=repository)
            with patch.object(LifecycleRiskMonitor, 'fetch_open_lifecycles', return_value=rows_first):
                second = monitor2.scan()

            monitor3 = LifecycleRiskMonitor(now=datetime(2026, 3, 10, 13, 10, 0), repository=repository)
            with patch.object(LifecycleRiskMonitor, 'fetch_open_lifecycles', return_value=rows_second):
                third = monitor3.scan()

        self.assertEqual(first['summary']['inserted_count'], 1)
        self.assertEqual(second['summary']['cooldown_refreshed_count'], 1)
        self.assertEqual(second['candidates'][0]['persist_action'], 'cooldown_refreshed')
        self.assertEqual(third['summary']['resolved_count'], 1)
        self.assertEqual(third['summary']['active_candidate_count'], 0)
        self.assertEqual(repository.records[0]['status'], 'resolved')


if __name__ == '__main__':
    unittest.main()
