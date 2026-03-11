#!/usr/bin/env python3
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.submit_attempt_service import SubmitAttemptService


class FakeProposalRepository:
    def __init__(self, proposals=None):
        self.proposals = {row['id']: dict(row) for row in (proposals or [])}

    def get_by_id(self, proposal_id):
        row = self.proposals.get(proposal_id)
        return dict(row) if row else {}

    def update_submit_state(self, proposal_id, **fields):
        row = dict(self.proposals[proposal_id])
        row.update(fields)
        self.proposals[proposal_id] = row
        return dict(row)


class FakeSubmitAttemptRepository:
    def __init__(self):
        self.records = {}
        self.by_proposal = {}
        self.next_id = 1

    def find_by_proposal_id(self, proposal_id):
        attempt_id = self.by_proposal.get(proposal_id)
        return dict(self.records[attempt_id]) if attempt_id else None

    def get_by_id(self, attempt_id):
        return dict(self.records.get(attempt_id) or {})

    def acquire_reservation(self, payload):
        existing = self.find_by_proposal_id(payload['proposal_id'])
        if existing:
            existing.update({
                'reservation_status': 'active',
                'lease_owner': payload['lease_owner'],
                'lease_token': payload['idempotency_key'],
                'lease_acquired_at': payload['lease_acquired_at'].isoformat(sep=' '),
                'lease_expires_at': payload['lease_expires_at'].isoformat(sep=' '),
                'broker': 'futu',
                'broker_request_key': payload['idempotency_key'],
            })
            self.records[existing['id']] = existing
            return dict(existing)
        row = {
            'id': self.next_id,
            'proposal_id': payload['proposal_id'],
            'candidate_id': payload['candidate_id'],
            'lifecycle_id': payload['lifecycle_id'],
            'symbol': payload['symbol'],
            'proposal_mode': payload['proposal_mode'],
            'reservation_key': payload['reservation_key'],
            'reservation_status': 'active',
            'lease_owner': payload['lease_owner'],
            'lease_token': payload['idempotency_key'],
            'lease_acquired_at': payload['lease_acquired_at'].isoformat(sep=' '),
            'lease_expires_at': payload['lease_expires_at'].isoformat(sep=' '),
            'broker': 'futu',
            'broker_request_key': payload['idempotency_key'],
            'submit_state': 'reserved',
            'idempotency_key': payload['idempotency_key'],
            'external_correlation_id': payload['external_correlation_id'],
            'audit_payload': payload['audit_payload'],
        }
        self.records[self.next_id] = row
        self.by_proposal[payload['proposal_id']] = self.next_id
        self.next_id += 1
        return dict(row)

    def transition_state(self, attempt_id, *, from_state, to_state, patch=None):
        row = dict(self.records[attempt_id])
        if row['submit_state'] != from_state:
            raise AssertionError(f"bad transition {row['submit_state']} -> {to_state}, expected from {from_state}")
        row['submit_state'] = to_state
        for key, value in (patch or {}).items():
            if isinstance(value, datetime):
                value = value.isoformat(sep=' ')
            row[key] = value
        self.records[attempt_id] = row
        return dict(row)

    def mark_released(self, attempt_id, *, reservation_status='released', submit_state=None):
        row = dict(self.records[attempt_id])
        row['reservation_status'] = reservation_status
        if submit_state:
            row['submit_state'] = submit_state
        self.records[attempt_id] = row
        return dict(row)


class FakeSyncService:
    def __init__(self, *, sync_result=None):
        self.refresh_calls = 0
        self.run_calls = 0
        self.targeted_calls = []
        self.sync_result = sync_result or {
            'orders_upserted': 1,
            'fills_upserted': 0,
            'position_snapshots_inserted': 1,
            'equity_snapshots_inserted': 0,
            'lifecycles_updated': 1,
            'risk_scan': {},
            'warnings': [],
        }

    def refresh_trade_lifecycles(self):
        self.refresh_calls += 1
        return 3

    def run_once(self):
        self.run_calls += 1
        return dict(self.sync_result)

    def sync_external_order_ref(self, external_order_ref, *, lifecycle_id=None):
        self.targeted_calls.append((external_order_ref, lifecycle_id))
        payload = dict(self.sync_result)
        payload.setdefault('external_order_ref', external_order_ref)
        payload.setdefault('broker_order', None)
        payload.setdefault('paper_order', None)
        payload.setdefault('fill_detected', False)
        return payload


class SubmitAttemptServiceTest(unittest.TestCase):
    def test_reservation_is_idempotent_and_stable(self):
        proposals = [{
            'id': 10,
            'candidate_id': 20,
            'lifecycle_id': 30,
            'symbol': 'US.AAPL',
            'proposal_mode': 'dry_run',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
        }]
        submit_repo = FakeSubmitAttemptRepository()
        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 0, 0),
            proposal_repository=FakeProposalRepository(proposals),
            submit_repository=submit_repo,
            sync_service=FakeSyncService(),
            hostname='tm-node',
            paper_reconcile_fn=lambda apply=True: {'success': True, 'rebuilt_positions': 0},
        )

        first = service.reserve_for_submission(10)
        second = service.reserve_for_submission(10)

        self.assertEqual(first['attempt']['id'], second['attempt']['id'])
        self.assertEqual(first['attempt']['idempotency_key'], second['attempt']['idempotency_key'])
        self.assertEqual(first['attempt']['external_correlation_id'], second['attempt']['external_correlation_id'])
        self.assertEqual(second['attempt']['reservation_status'], 'active')
        self.assertTrue(second['duplicate_protection']['reused_existing_attempt'])

    def test_submit_state_machine_advances_without_broker_call(self):
        proposals = [{
            'id': 11,
            'candidate_id': 21,
            'lifecycle_id': 31,
            'symbol': 'US.TSLA',
            'proposal_mode': 'dry_run',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
        }]
        submit_repo = FakeSubmitAttemptRepository()
        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 5, 0),
            proposal_repository=FakeProposalRepository(proposals),
            submit_repository=submit_repo,
            sync_service=FakeSyncService(),
            hostname='tm-node',
            paper_reconcile_fn=lambda apply=True: {'success': True, 'rebuilt_positions': 0},
        )

        result = service.advance_to_reconcile_pending(11)

        self.assertFalse(result['broker_called'])
        self.assertEqual(result['attempt']['submit_state'], 'reconcile_pending')
        self.assertIn('idempotency_key', result['attempt'])
        self.assertIn('external_correlation_id', result['attempt'])

    def test_live_submit_guard_blocks_non_sim_path(self):
        proposals = [{
            'id': 15,
            'candidate_id': 25,
            'lifecycle_id': 35,
            'symbol': 'US.NVDA',
            'proposal_mode': 'live',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
        }]
        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 7, 0),
            proposal_repository=FakeProposalRepository(proposals),
            submit_repository=FakeSubmitAttemptRepository(),
            sync_service=FakeSyncService(),
            hostname='tm-node',
        )

        with patch('execution.submit_attempt_service.SystemConfig.is_paper_trading', return_value=True), \
             patch('execution.submit_attempt_service.SystemConfig.get_trading_mode', return_value=0):
            result = service.submit_live_exit_order(15)

        self.assertFalse(result['success'])
        self.assertTrue(result['sim_only_guard'])
        self.assertIn('requires trading_mode=1', result['reason'])

    def test_live_submit_success_moves_to_reconcile_pending_with_correlation(self):
        proposals = [{
            'id': 16,
            'candidate_id': 26,
            'lifecycle_id': 36,
            'symbol': 'US.TSLA',
            'proposal_mode': 'live',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
            'audit_payload': {
                'snapshot': {'market_price': 299.5},
                'candidate': {'current_price': 299.5},
            },
        }]
        submit_repo = FakeSubmitAttemptRepository()
        proposal_repo = FakeProposalRepository(proposals)
        sync_service = FakeSyncService()
        broker_calls = []

        def fake_broker_submit_fn(**payload):
            broker_calls.append(payload)
            return {
                'success': True,
                'order_id': 7001,
                'futu_order_id': 'SIM-EXIT-7001',
                'status': 'pending',
                'sim_only_guard': True,
            }

        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 8, 0),
            proposal_repository=proposal_repo,
            submit_repository=submit_repo,
            sync_service=sync_service,
            hostname='tm-node',
            broker_submit_fn=fake_broker_submit_fn,
        )

        with patch('execution.submit_attempt_service.SystemConfig.is_paper_trading', return_value=True), \
             patch('execution.submit_attempt_service.SystemConfig.get_trading_mode', return_value=1), \
             patch.object(SubmitAttemptService, '_fetch_lifecycle', return_value={'id': 36, 'signal_id': 501, 'position_qty': 2}):
            result = service.submit_live_exit_order(16)

        self.assertTrue(result['success'])
        self.assertTrue(result['broker_called'])
        self.assertEqual(result['attempt']['submit_state'], 'reconcile_pending')
        self.assertEqual(result['attempt']['broker_order_id'], 'SIM-EXIT-7001')
        self.assertEqual(result['proposal']['external_order_ref'], 'SIM-EXIT-7001')
        self.assertEqual(result['proposal']['reconciliation_status'], 'awaiting_reconciliation')
        self.assertEqual(len(broker_calls), 1)
        self.assertEqual(broker_calls[0]['quantity'], 2)
        self.assertTrue(broker_calls[0]['sim_only_guard'])

    def test_live_submit_duplicate_protection_reuses_existing_attempt(self):
        proposals = [{
            'id': 17,
            'candidate_id': 27,
            'lifecycle_id': 37,
            'symbol': 'US.AAPL',
            'proposal_mode': 'live',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
            'audit_payload': {
                'snapshot': {'market_price': 188.0},
                'candidate': {'current_price': 188.0},
            },
        }]
        submit_repo = FakeSubmitAttemptRepository()
        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 9, 0),
            proposal_repository=FakeProposalRepository(proposals),
            submit_repository=submit_repo,
            sync_service=FakeSyncService(),
            hostname='tm-node',
            broker_submit_fn=lambda **payload: {
                'success': True,
                'order_id': 8001,
                'futu_order_id': 'SIM-EXIT-8001',
                'status': 'pending',
                'sim_only_guard': True,
            },
        )

        with patch('execution.submit_attempt_service.SystemConfig.is_paper_trading', return_value=True), \
             patch('execution.submit_attempt_service.SystemConfig.get_trading_mode', return_value=1), \
             patch.object(SubmitAttemptService, '_fetch_lifecycle', return_value={'id': 37, 'signal_id': 502, 'position_qty': 1}):
            first = service.submit_live_exit_order(17)
            second = service.submit_live_exit_order(17)

        self.assertTrue(first['success'])
        self.assertTrue(second['success'])
        self.assertEqual(first['attempt']['id'], second['attempt']['id'])
        self.assertTrue(second['duplicate_protection']['reused_existing_attempt'])

    def test_post_submit_reconciliation_stays_pending_without_fill_signal(self):
        proposals = [{
            'id': 12,
            'candidate_id': 22,
            'lifecycle_id': 32,
            'symbol': 'US.NVDA',
            'proposal_mode': 'live',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
            'external_order_ref': 'SIM-EXIT-9001',
        }]
        submit_repo = FakeSubmitAttemptRepository()
        sync_service = FakeSyncService(sync_result={
            'orders_upserted': 1,
            'fills_upserted': 0,
            'position_snapshots_inserted': 0,
            'equity_snapshots_inserted': 0,
            'lifecycles_updated': 1,
            'risk_scan': {},
            'warnings': [],
            'broker_order': {'broker_order_id': 'SIM-EXIT-9001', 'status': 'submitted'},
            'fill_detected': False,
        })
        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 10, 0),
            proposal_repository=FakeProposalRepository(proposals),
            submit_repository=submit_repo,
            sync_service=sync_service,
            hostname='tm-node',
            paper_reconcile_fn=lambda apply=True: {'success': True, 'rebuilt_positions': 0},
        )
        service.advance_to_reconcile_pending(12)
        submit_repo.records[1]['broker_order_id'] = 'SIM-EXIT-9001'
        submit_repo.records[1]['external_order_ref'] = 'SIM-EXIT-9001'
        result = service.run_post_submit_reconciliation(12)

        self.assertFalse(result['readiness']['reconciled'])
        self.assertEqual(result['attempt']['submit_state'], 'reconcile_pending')
        self.assertEqual(result['attempt']['reservation_status'], 'active')
        self.assertEqual(result['proposal']['reconciliation_status'], 'awaiting_reconciliation')
        self.assertEqual(sync_service.targeted_calls, [('SIM-EXIT-9001', 32)])

    def test_post_submit_reconciliation_reconciles_after_fill_and_lifecycle_close(self):
        proposals = [{
            'id': 13,
            'candidate_id': 23,
            'lifecycle_id': 33,
            'symbol': 'US.NVDA',
            'proposal_mode': 'live',
            'status': 'proposed',
            'action_type': 'exit_market',
            'action_side': 'sell',
            'external_order_ref': 'SIM-EXIT-9002',
        }]
        submit_repo = FakeSubmitAttemptRepository()
        sync_service = FakeSyncService(sync_result={
            'orders_upserted': 1,
            'fills_upserted': 1,
            'position_snapshots_inserted': 0,
            'equity_snapshots_inserted': 0,
            'lifecycles_updated': 1,
            'risk_scan': {},
            'warnings': [],
            'broker_order': {'broker_order_id': 'SIM-EXIT-9002', 'status': 'filled'},
            'fill_detected': True,
        })
        service = SubmitAttemptService(
            now=datetime(2026, 3, 10, 16, 11, 0),
            proposal_repository=FakeProposalRepository(proposals),
            submit_repository=submit_repo,
            sync_service=sync_service,
            hostname='tm-node',
            paper_reconcile_fn=lambda apply=True: {'success': True, 'rebuilt_positions': 0},
        )
        service.advance_to_reconcile_pending(13)
        submit_repo.records[1]['broker_order_id'] = 'SIM-EXIT-9002'
        submit_repo.records[1]['external_order_ref'] = 'SIM-EXIT-9002'

        with patch.object(SubmitAttemptService, '_fetch_lifecycle', return_value={'id': 33, 'status': 'closed'}):
            result = service.run_post_submit_reconciliation(13)

        self.assertTrue(result['readiness']['reconciled'])
        self.assertEqual(result['attempt']['submit_state'], 'reconciled')
        self.assertEqual(result['attempt']['reservation_status'], 'released')
        self.assertEqual(result['proposal']['reconciliation_status'], 'reconciled')
        self.assertEqual(sync_service.targeted_calls, [('SIM-EXIT-9002', 33)])


if __name__ == '__main__':
    unittest.main()
