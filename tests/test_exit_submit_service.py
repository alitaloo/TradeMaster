#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.exit_reconciliation_hook import ExitReconciliationHook
from execution.exit_submit_service import ExitSubmitService


class FakeProposalRepository:
    def __init__(self, records=None):
        self.records = [dict(row) for row in (records or [])]

    def list_proposals(self, *, statuses=None, limit=200):
        rows = self.records
        if statuses:
            rows = [row for row in rows if row.get('status') in statuses]
        return [dict(row) for row in rows[:limit]]

    def get_by_id(self, proposal_id):
        for row in self.records:
            if row['id'] == proposal_id:
                return dict(row)
        return {}

    def acquire_lease(self, *, proposal_id, lease_owner, lease_token, leased_at, lease_expires_at):
        for row in self.records:
            if row['id'] != proposal_id:
                continue
            existing_expiry = row.get('lease_expires_at')
            if row.get('status') != 'proposed':
                return None
            if row.get('submit_state') not in (None, 'proposed', 'submit_failed', 'submit_blocked'):
                return None
            if existing_expiry and existing_expiry > leased_at and row.get('lease_owner') != lease_owner:
                return None
            row.update({
                'lease_owner': lease_owner,
                'lease_token': lease_token,
                'leased_at': leased_at.isoformat(sep=' '),
                'lease_expires_at': lease_expires_at.isoformat(sep=' '),
                'submit_state': 'leased',
                'submit_state_reason': 'lease acquired',
            })
            return dict(row)
        return None

    def update_submit_state(self, proposal_id, **fields):
        for row in self.records:
            if row['id'] == proposal_id:
                for key, value in fields.items():
                    if isinstance(value, datetime):
                        row[key] = value.isoformat(sep=' ')
                    else:
                        row[key] = value
                return dict(row)
        return {}


class FakeAttemptRepository:
    def __init__(self):
        self.records = []
        self.next_id = 1

    def create_attempt(self, attempt):
        row = {'id': self.next_id}
        self.next_id += 1
        for key, value in dict(attempt).items():
            if isinstance(value, datetime):
                row[key] = value.isoformat(sep=' ')
            else:
                row[key] = value
        self.records.append(row)
        return dict(row)

    def get_by_id(self, attempt_id):
        for row in self.records:
            if row['id'] == attempt_id:
                return dict(row)
        return {}

    def find_by_request_key(self, *, broker, broker_request_key):
        for row in self.records:
            if row.get('broker') == broker and row.get('broker_request_key') == broker_request_key:
                return dict(row)
        return None

    def get_latest_attempt(self, *, proposal_id):
        rows = [row for row in self.records if row.get('proposal_id') == proposal_id]
        if not rows:
            return None
        return dict(sorted(rows, key=lambda row: (row.get('attempt_no', 0), row.get('id', 0)))[-1])

    def list_attempts(self, *, statuses=None, proposal_id=None, limit=200):
        rows = self.records
        if proposal_id is not None:
            rows = [row for row in rows if row.get('proposal_id') == proposal_id]
        if statuses:
            rows = [row for row in rows if row.get('attempt_status') in statuses]
        return [dict(row) for row in rows[:limit]]


class ExitSubmitServiceTest(unittest.TestCase):
    def _make_proposal(self, **overrides):
        base = {
            'id': 1,
            'candidate_id': 7,
            'lifecycle_id': 301,
            'symbol': 'US.TSLA',
            'status': 'proposed',
            'proposal_mode': 'dry_run',
            'action_type': 'exit_market',
            'action_side': 'sell',
            'submit_state': 'proposed',
            'lease_owner': None,
            'lease_expires_at': None,
            'broker_request_key': None,
            'external_order_ref': None,
        }
        base.update(overrides)
        return base

    def test_submit_dry_run_acquires_lease_and_creates_simulated_attempt(self):
        proposals = FakeProposalRepository([self._make_proposal()])
        attempts = FakeAttemptRepository()
        service = ExitSubmitService(
            now=datetime(2026, 3, 10, 16, 0, 0),
            proposal_repository=proposals,
            attempt_repository=attempts,
            reconciliation_hook=ExitReconciliationHook(),
        )

        report = service.process_dry_run_submissions(lease_owner='worker-a', lease_seconds=90)

        self.assertEqual(report['summary']['leased_count'], 1)
        self.assertEqual(report['summary']['simulated_count'], 1)
        proposal = proposals.get_by_id(1)
        self.assertEqual(proposal['submit_state'], 'submit_simulated')
        self.assertEqual(proposal['lease_owner'], 'worker-a')
        self.assertTrue(proposal['broker_request_key'].startswith('exit:dry_run:1:7'))
        self.assertEqual(proposal['reconciliation_status'], 'awaiting_reconciliation')
        self.assertEqual(len(attempts.records), 1)
        self.assertEqual(attempts.records[0]['attempt_status'], 'submit_simulated')

    def test_existing_live_lease_blocks_second_worker(self):
        expiry = datetime(2026, 3, 10, 16, 5, 0)
        proposals = FakeProposalRepository([
            self._make_proposal(
                lease_owner='worker-a',
                lease_expires_at=expiry,
            )
        ])
        attempts = FakeAttemptRepository()
        service = ExitSubmitService(
            now=datetime(2026, 3, 10, 16, 0, 0),
            proposal_repository=proposals,
            attempt_repository=attempts,
        )

        result = service.process_single_proposal(proposals.get_by_id(1), lease_owner='worker-b')

        self.assertTrue(result['skipped'])
        self.assertEqual(result['reason'], 'lease unavailable or proposal no longer eligible')
        self.assertEqual(len(attempts.records), 0)

    def test_idempotent_request_key_reuses_existing_attempt(self):
        proposals = FakeProposalRepository([self._make_proposal(broker_request_key='exit:dry_run:1:7')])
        attempts = FakeAttemptRepository()
        attempts.create_attempt({
            'proposal_id': 1,
            'candidate_id': 7,
            'lifecycle_id': 301,
            'symbol': 'US.TSLA',
            'attempt_no': 1,
            'lease_owner': 'worker-a',
            'lease_token': 'lease-old',
            'broker': 'futu',
            'broker_request_key': 'exit:dry_run:1:7',
            'external_order_ref': 'SIMULATED-1-1',
            'submission_mode': 'dry_run',
            'attempt_status': 'submit_simulated',
            'reconciliation_status': 'awaiting_reconciliation',
            'reconciliation_hook': 'paper_position_reconciliation',
            'reconciliation_payload': {'ok': True},
            'request_payload': {},
            'response_payload': {},
            'simulated_at': datetime(2026, 3, 10, 15, 59, 0),
        })
        service = ExitSubmitService(
            now=datetime(2026, 3, 10, 16, 0, 0),
            proposal_repository=proposals,
            attempt_repository=attempts,
        )

        result = service.process_single_proposal(proposals.get_by_id(1), lease_owner='worker-b')

        self.assertTrue(result['idempotent_reuse'])
        self.assertEqual(len(attempts.records), 1)
        proposal = proposals.get_by_id(1)
        self.assertEqual(proposal['submit_last_attempt_id'], 1)
        self.assertEqual(proposal['submit_state'], 'submit_simulated')

    def test_inspect_state_surfaces_pre_live_pipeline_fields(self):
        proposals = FakeProposalRepository([
            self._make_proposal(
                submit_state='submit_blocked',
                submit_state_reason='freshness check failed',
                broker_request_key='exit:dry_run:1:7',
                external_order_ref=None,
                reconciliation_status='pending_submit',
                submit_last_attempt_id=None,
            )
        ])
        service = ExitSubmitService(
            now=datetime(2026, 3, 10, 16, 0, 0),
            proposal_repository=proposals,
            attempt_repository=FakeAttemptRepository(),
        )

        report = service.inspect_state(limit=10)

        self.assertEqual(report['count'], 1)
        self.assertEqual(report['items'][0]['submit_state'], 'submit_blocked')
        self.assertEqual(report['items'][0]['broker_request_key'], 'exit:dry_run:1:7')


if __name__ == '__main__':
    unittest.main()
