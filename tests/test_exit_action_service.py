#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.exit_action_service import ExitActionService


class FakeCandidateRepository:
    def __init__(self, records=None):
        self.records = records or []

    def list_candidates(self, *, statuses=('active',), limit=200):
        rows = [row for row in self.records if row.get('status') in statuses]
        return rows[:limit]


class FakeProposalRepository:
    def __init__(self):
        self.records = []
        self.next_id = 1

    def upsert_proposal(self, proposal):
        for record in self.records:
            if record['candidate_id'] == proposal['candidate_id'] and record['proposal_mode'] == proposal['proposal_mode']:
                record.update(self._serialize(proposal))
                record['id'] = record['id']
                return dict(record)
        row = {'id': self.next_id} | self._serialize(proposal)
        self.next_id += 1
        self.records.append(row)
        return dict(row)

    def list_proposals(self, *, statuses=None, limit=200):
        rows = self.records
        if statuses:
            rows = [row for row in rows if row.get('status') in statuses]
        return [dict(row) for row in rows[:limit]]

    @staticmethod
    def _serialize(proposal):
        row = dict(proposal)
        for key in ('freshness_checked_at',):
            if isinstance(row.get(key), datetime):
                row[key] = row[key].isoformat(sep=' ')
        return row


class ExitActionServiceTest(unittest.TestCase):
    def test_gate_off_skips_generation_and_persistence(self):
        candidates = [{'id': 1, 'lifecycle_id': 101, 'symbol': 'US.AAPL', 'candidate_type': 'stop_loss', 'status': 'active', 'last_detected_at': '2026-03-10 13:59:30'}]
        proposal_repo = FakeProposalRepository()
        config = {
            'risk.exit_action_enabled': 'false',
            'risk.exit_action_mode': 'off',
            'risk.exit_action_freshness_seconds': '120',
        }

        def fake_get(key, default=None):
            return config.get(key, default)

        service = ExitActionService(
            now=datetime(2026, 3, 10, 14, 0, 0),
            candidate_repository=FakeCandidateRepository(candidates),
            proposal_repository=proposal_repo,
        )
        with patch('execution.exit_action_service.SystemConfig.get', side_effect=fake_get):
            report = service.generate_proposals()

        self.assertEqual(report['summary']['gate_skipped_count'], 1)
        self.assertEqual(report['proposals'], [])
        self.assertEqual(proposal_repo.records, [])

    def test_dry_run_proposes_and_upserts_idempotently(self):
        candidates = [{'id': 7, 'lifecycle_id': 301, 'symbol': 'US.TSLA', 'candidate_type': 'stop_loss', 'status': 'active', 'reason': 'crossed', 'threshold_value': 95.0, 'current_price': 94.0, 'last_detected_at': '2026-03-10 13:59:30'}]
        proposal_repo = FakeProposalRepository()
        config = {
            'risk.exit_action_enabled': 'true',
            'risk.exit_action_mode': 'dry_run',
            'risk.exit_action_freshness_seconds': '120',
        }

        def fake_get(key, default=None):
            return config.get(key, default)

        lifecycle = {'id': 301, 'status': 'filled_open', 'direction': 'long', 'position_qty': 2, 'entry_time': '2026-03-10 09:00:00'}
        snapshot = {'snapshot_time': '2026-03-10 13:59:20', 'symbol': 'US.TSLA', 'qty': 2, 'market_price': 94.0}
        service = ExitActionService(
            now=datetime(2026, 3, 10, 14, 0, 0),
            candidate_repository=FakeCandidateRepository(candidates),
            proposal_repository=proposal_repo,
        )
        with patch('execution.exit_action_service.SystemConfig.get', side_effect=fake_get), \
             patch.object(ExitActionService, 'fetch_lifecycle', return_value=lifecycle), \
             patch.object(ExitActionService, 'fetch_latest_position_snapshot', return_value=snapshot):
            first = service.generate_proposals()
            second = service.generate_proposals()

        self.assertEqual(first['summary']['proposed_count'], 1)
        self.assertEqual(second['summary']['proposed_count'], 1)
        self.assertEqual(len(proposal_repo.records), 1)
        self.assertEqual(proposal_repo.records[0]['status'], 'proposed')
        self.assertEqual(proposal_repo.records[0]['action_side'], 'sell')

    def test_stale_snapshot_marks_proposal_stale(self):
        candidates = [{'id': 9, 'lifecycle_id': 501, 'symbol': 'US.NVDA', 'candidate_type': 'take_profit', 'status': 'active', 'reason': 'crossed', 'threshold_value': 110.0, 'current_price': 111.0, 'last_detected_at': '2026-03-10 13:58:30'}]
        proposal_repo = FakeProposalRepository()
        config = {
            'risk.exit_action_enabled': 'true',
            'risk.exit_action_mode': 'dry_run',
            'risk.exit_action_freshness_seconds': '60',
        }

        def fake_get(key, default=None):
            return config.get(key, default)

        lifecycle = {'id': 501, 'status': 'filled_open', 'direction': 'long', 'position_qty': 1, 'entry_time': '2026-03-10 12:00:00'}
        snapshot = {'snapshot_time': '2026-03-10 13:56:00', 'symbol': 'US.NVDA', 'qty': 1, 'market_price': 111.0}
        service = ExitActionService(
            now=datetime(2026, 3, 10, 14, 0, 0),
            candidate_repository=FakeCandidateRepository(candidates),
            proposal_repository=proposal_repo,
        )
        with patch('execution.exit_action_service.SystemConfig.get', side_effect=fake_get), \
             patch.object(ExitActionService, 'fetch_lifecycle', return_value=lifecycle), \
             patch.object(ExitActionService, 'fetch_latest_position_snapshot', return_value=snapshot):
            report = service.generate_proposals()

        self.assertEqual(report['summary']['stale_count'], 1)
        self.assertEqual(report['proposals'][0]['status'], 'stale')
        self.assertIn('stale', report['proposals'][0]['block_reason'])

    def test_closed_lifecycle_blocks_proposal(self):
        candidates = [{'id': 11, 'lifecycle_id': 777, 'symbol': 'US.META', 'candidate_type': 'holding_timeout', 'status': 'active', 'reason': 'timeout', 'threshold_value': 120, 'current_price': 200.0, 'last_detected_at': '2026-03-10 13:59:40'}]
        proposal_repo = FakeProposalRepository()
        config = {
            'risk.exit_action_enabled': 'true',
            'risk.exit_action_mode': 'dry_run',
            'risk.exit_action_freshness_seconds': '120',
        }

        def fake_get(key, default=None):
            return config.get(key, default)

        lifecycle = {'id': 777, 'status': 'closed', 'direction': 'long', 'position_qty': 0, 'entry_time': '2026-03-10 10:00:00'}
        snapshot = {'snapshot_time': '2026-03-10 13:59:30', 'symbol': 'US.META', 'qty': 0, 'market_price': 200.0}
        service = ExitActionService(
            now=datetime(2026, 3, 10, 14, 0, 0),
            candidate_repository=FakeCandidateRepository(candidates),
            proposal_repository=proposal_repo,
        )
        with patch('execution.exit_action_service.SystemConfig.get', side_effect=fake_get), \
             patch.object(ExitActionService, 'fetch_lifecycle', return_value=lifecycle), \
             patch.object(ExitActionService, 'fetch_latest_position_snapshot', return_value=snapshot):
            report = service.generate_proposals()

        self.assertEqual(report['summary']['blocked_count'], 1)
        self.assertEqual(report['proposals'][0]['status'], 'blocked')
        self.assertIn('not open/eligible', report['proposals'][0]['block_reason'])


if __name__ == '__main__':
    unittest.main()
