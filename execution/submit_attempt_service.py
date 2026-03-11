from __future__ import annotations

import hashlib
import os
import socket
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from execution.exit_action_repository import ExitActionProposalRepository
from execution.futu_sync_service import FutuSyncService
from execution.submit_attempt_repository import SubmitAttemptRepository
from models.system_config import SystemConfig

ALLOWED_PRE_SUBMIT_STATUSES = {'proposed'}
ALLOWED_ACTIVE_ATTEMPT_STATES = {'reserved', 'submitting', 'submitted', 'ack_pending', 'reconcile_pending', 'reconciled'}


class SubmitAttemptService:
    def __init__(
        self,
        *,
        now: Optional[datetime] = None,
        proposal_repository: Optional[ExitActionProposalRepository] = None,
        submit_repository: Optional[SubmitAttemptRepository] = None,
        sync_service: Optional[FutuSyncService] = None,
        hostname: Optional[str] = None,
        paper_reconcile_fn=None,
        broker_submit_fn=None,
    ):
        self.now = now or datetime.now()
        self.proposal_repository = proposal_repository or ExitActionProposalRepository()
        self.submit_repository = submit_repository or SubmitAttemptRepository()
        self.sync_service = sync_service or FutuSyncService()
        self.hostname = hostname or socket.gethostname()
        self.paper_reconcile_fn = paper_reconcile_fn
        self.broker_submit_fn = broker_submit_fn

    def reserve_for_submission(self, proposal_id: int, *, lease_seconds: int = 30) -> Dict[str, Any]:
        proposal = self.proposal_repository.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f'proposal not found: {proposal_id}')
        if proposal.get('status') not in ALLOWED_PRE_SUBMIT_STATUSES:
            raise ValueError(f"proposal not eligible for submission reservation: status={proposal.get('status')}")

        existing_attempt = self.submit_repository.find_by_proposal_id(proposal_id)
        if existing_attempt and existing_attempt.get('submit_state') in ALLOWED_ACTIVE_ATTEMPT_STATES:
            return {
                'reserved_at': self.now.isoformat(sep=' '),
                'proposal_id': proposal['id'],
                'attempt': existing_attempt,
                'reservation': {
                    'reservation_key': existing_attempt.get('reservation_key'),
                    'lease_owner': existing_attempt.get('lease_owner'),
                    'lease_expires_at': existing_attempt.get('lease_expires_at'),
                },
                'duplicate_protection': {
                    'reused_existing_attempt': True,
                    'reason': f"proposal already has active attempt state={existing_attempt.get('submit_state')}",
                },
            }

        reservation_key = f"proposal:{proposal['id']}:mode:{proposal.get('proposal_mode') or 'dry_run'}"
        idempotency_key = self._stable_key('idemp', proposal)
        external_correlation_id = self._stable_key('corr', proposal)
        payload = {
            'proposal_id': proposal['id'],
            'candidate_id': proposal['candidate_id'],
            'lifecycle_id': proposal['lifecycle_id'],
            'symbol': proposal['symbol'],
            'proposal_mode': proposal.get('proposal_mode') or 'dry_run',
            'reservation_key': reservation_key,
            'lease_owner': self.hostname,
            'lease_acquired_at': self.now,
            'lease_expires_at': self.now + timedelta(seconds=max(1, int(lease_seconds))),
            'idempotency_key': idempotency_key,
            'external_correlation_id': external_correlation_id,
            'audit_payload': {
                'proposal_snapshot': proposal,
                'reservation': {
                    'lease_owner': self.hostname,
                    'lease_seconds': max(1, int(lease_seconds)),
                    'reserved_at': self.now.isoformat(sep=' '),
                },
            },
        }
        attempt = self.submit_repository.acquire_reservation(payload)
        return {
            'reserved_at': self.now.isoformat(sep=' '),
            'proposal_id': proposal['id'],
            'attempt': attempt,
            'reservation': {
                'reservation_key': reservation_key,
                'lease_owner': self.hostname,
                'lease_expires_at': payload['lease_expires_at'].isoformat(sep=' '),
            },
            'duplicate_protection': {
                'reused_existing_attempt': False,
            },
        }

    def advance_to_reconcile_pending(self, proposal_id: int, *, dry_run: bool = True) -> Dict[str, Any]:
        reservation = self.reserve_for_submission(proposal_id)
        attempt = reservation['attempt']
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state=attempt['submit_state'],
            to_state='submitting',
            patch={'submit_requested_at': self.now},
        )
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state='submitting',
            to_state='submitted',
            patch={
                'submit_finished_at': self.now,
                'audit_payload': {
                    'dry_run': dry_run,
                    'message': 'pre-live safety pack: broker submit intentionally not called',
                    'idempotency_key': attempt['idempotency_key'],
                    'external_correlation_id': attempt['external_correlation_id'],
                },
            },
        )
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state='submitted',
            to_state='ack_pending',
            patch={'submit_finished_at': self.now},
        )
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state='ack_pending',
            to_state='reconcile_pending',
            patch={'reconciliation_due_at': self.now},
        )
        return {
            'dry_run': dry_run,
            'broker_called': False,
            'attempt': attempt,
        }

    def submit_live_exit_order(self, proposal_id: int, *, lease_seconds: int = 30) -> Dict[str, Any]:
        proposal = self.proposal_repository.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f'proposal not found: {proposal_id}')

        guard = self._sim_only_guard(proposal)
        if not guard['allowed']:
            blocked_proposal = self.proposal_repository.update_submit_state(
                proposal_id,
                status='blocked',
                submit_state='submit_blocked',
                submit_state_reason=guard['reason'],
                reconciliation_status='reconciliation_blocked',
                reconciliation_hook='sim_only_guard',
                reconciliation_payload=guard,
                block_reason=guard['reason'],
            )
            attempt = self.submit_repository.find_by_proposal_id(proposal_id)
            if attempt and attempt.get('submit_state') in ALLOWED_ACTIVE_ATTEMPT_STATES:
                attempt = self.submit_repository.transition_state(
                    attempt['id'],
                    from_state=attempt['submit_state'],
                    to_state='failed',
                    patch={
                        'reservation_status': 'released',
                        'last_error': guard['reason'],
                        'failure_reason': guard['reason'],
                        'attempt_status': 'submit_blocked',
                        'submission_mode': 'live',
                        'reconciliation_status': 'reconciliation_blocked',
                        'reconciliation_hook': 'sim_only_guard',
                        'response_payload': guard,
                        'audit_payload': {'sim_only_guard': guard},
                    },
                )
            return {
                'success': False,
                'broker_called': False,
                'sim_only_guard': True,
                'blocked': True,
                'reason': guard['reason'],
                'proposal': blocked_proposal,
                'attempt': attempt,
            }

        reservation = self.reserve_for_submission(proposal_id, lease_seconds=lease_seconds)
        attempt = reservation['attempt']
        if attempt.get('submit_state') in {'submitted', 'ack_pending', 'reconcile_pending', 'reconciled'} and attempt.get('broker_order_id'):
            return {
                'success': True,
                'broker_called': False,
                'sim_only_guard': True,
                'duplicate_protection': {'reused_existing_attempt': True, 'reason': 'existing broker order already correlated'},
                'attempt': attempt,
                'proposal': proposal,
            }

        request_payload = self._build_broker_submit_payload(proposal, attempt)
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state=attempt['submit_state'],
            to_state='submitting',
            patch={
                'submit_requested_at': self.now,
                'submission_mode': 'live',
                'attempt_status': 'ready_to_submit',
                'request_payload': request_payload,
            },
        )
        self.proposal_repository.update_submit_state(
            proposal_id,
            submit_state='ready_to_submit',
            submit_ready_at=self.now,
            submit_last_attempt_id=attempt['id'],
            broker_request_key=attempt['idempotency_key'],
            reconciliation_status='pending_submit',
            reconciliation_hook='futu_sim_submit',
            reconciliation_payload={
                'sim_only_guard': True,
                'request_payload': request_payload,
            },
            lease_owner=attempt.get('lease_owner'),
            lease_token=attempt.get('lease_token'),
            leased_at=attempt.get('lease_acquired_at'),
            lease_expires_at=attempt.get('lease_expires_at'),
        )

        try:
            broker_result = self._submit_to_futu_sim(request_payload)
        except Exception as exc:
            reason = f'futu sim submit exception: {exc}'
            attempt = self.submit_repository.transition_state(
                attempt['id'],
                from_state='submitting',
                to_state='failed',
                patch={
                    'submit_finished_at': self.now,
                    'reservation_status': 'released',
                    'last_error': reason,
                    'failure_reason': reason,
                    'attempt_status': 'submit_failed',
                    'submission_mode': 'live',
                    'reconciliation_status': 'reconciliation_blocked',
                    'reconciliation_hook': 'futu_sim_submit',
                    'response_payload': {'error': str(exc), 'sim_only_guard': True},
                },
            )
            blocked_proposal = self.proposal_repository.update_submit_state(
                proposal_id,
                submit_state='submit_failed',
                submit_state_reason=reason,
                submit_last_attempt_id=attempt['id'],
                reconciliation_status='reconciliation_blocked',
                reconciliation_hook='futu_sim_submit',
                reconciliation_payload={'error': str(exc), 'sim_only_guard': True},
                action_reason=None,
            )
            return {
                'success': False,
                'broker_called': True,
                'sim_only_guard': True,
                'reason': reason,
                'attempt': attempt,
                'proposal': blocked_proposal,
            }

        if not broker_result.get('success'):
            reason = broker_result.get('error') or 'futu sim submit failed'
            attempt = self.submit_repository.transition_state(
                attempt['id'],
                from_state='submitting',
                to_state='failed',
                patch={
                    'submit_finished_at': self.now,
                    'reservation_status': 'released',
                    'last_error': reason,
                    'failure_reason': reason,
                    'attempt_status': 'submit_failed',
                    'submission_mode': 'live',
                    'reconciliation_status': 'reconciliation_blocked',
                    'reconciliation_hook': 'futu_sim_submit',
                    'response_payload': broker_result,
                },
            )
            failed_proposal = self.proposal_repository.update_submit_state(
                proposal_id,
                submit_state='submit_failed',
                submit_state_reason=reason,
                submit_last_attempt_id=attempt['id'],
                reconciliation_status='reconciliation_blocked',
                reconciliation_hook='futu_sim_submit',
                reconciliation_payload=broker_result,
                action_reason=None,
            )
            return {
                'success': False,
                'broker_called': True,
                'sim_only_guard': True,
                'reason': reason,
                'attempt': attempt,
                'proposal': failed_proposal,
            }

        external_order_ref = str(broker_result.get('futu_order_id') or broker_result.get('order_id') or '')
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state='submitting',
            to_state='submitted',
            patch={
                'submit_finished_at': self.now,
                'broker_order_id': external_order_ref,
                'external_order_ref': external_order_ref,
                'attempt_status': 'ready_to_submit',
                'submission_mode': 'live',
                'reconciliation_status': 'awaiting_reconciliation',
                'reconciliation_hook': 'futu_sim_submit',
                'response_payload': broker_result,
                'audit_payload': {
                    'sim_only_guard': True,
                    'broker_result': broker_result,
                    'idempotency_key': attempt['idempotency_key'],
                    'external_correlation_id': attempt['external_correlation_id'],
                },
            },
        )
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state='submitted',
            to_state='ack_pending',
            patch={
                'submit_finished_at': self.now,
                'broker_order_id': external_order_ref,
                'external_order_ref': external_order_ref,
                'reconciliation_status': 'awaiting_reconciliation',
                'reconciliation_hook': 'futu_sim_submit',
                'response_payload': broker_result,
            },
        )
        attempt = self.submit_repository.transition_state(
            attempt['id'],
            from_state='ack_pending',
            to_state='reconcile_pending',
            patch={
                'broker_order_id': external_order_ref,
                'external_order_ref': external_order_ref,
                'reconciliation_due_at': self.now,
                'reconciliation_status': 'awaiting_reconciliation',
                'reconciliation_hook': 'futu_sim_submit',
                'response_payload': broker_result,
            },
        )
        proposal = self.proposal_repository.update_submit_state(
            proposal_id,
            status='proposed',
            submit_state='ready_to_submit',
            submit_state_reason='submitted to futu simulate',
            submit_ready_at=self.now,
            submit_last_attempt_id=attempt['id'],
            broker_request_key=attempt['idempotency_key'],
            external_order_ref=external_order_ref,
            reconciliation_status='awaiting_reconciliation',
            reconciliation_hook='futu_sim_submit',
            reconciliation_payload={
                'sim_only_guard': True,
                'broker_result': broker_result,
                'attempt_id': attempt['id'],
            },
            action_reason='futu simulate exit order submitted',
        )
        return {
            'success': True,
            'broker_called': True,
            'sim_only_guard': True,
            'attempt': attempt,
            'proposal': proposal,
            'broker_result': broker_result,
            'duplicate_protection': reservation.get('duplicate_protection') or {},
        }

    def run_post_submit_reconciliation(self, proposal_id: int) -> Dict[str, Any]:
        proposal = self.proposal_repository.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f'proposal not found: {proposal_id}')
        attempt = self.submit_repository.find_by_proposal_id(proposal_id)
        if not attempt:
            raise ValueError(f'submit attempt not found for proposal: {proposal_id}')
        if attempt.get('submit_state') != 'reconcile_pending':
            raise ValueError(f"submit attempt not reconcile_pending: {attempt.get('submit_state')}")

        external_order_ref = attempt.get('external_order_ref') or proposal.get('external_order_ref') or attempt.get('broker_order_id')
        if external_order_ref and hasattr(self.sync_service, 'sync_external_order_ref'):
            sync_result = self.sync_service.sync_external_order_ref(
                external_order_ref,
                lifecycle_id=proposal.get('lifecycle_id') or attempt.get('lifecycle_id'),
            )
        else:
            sync_result = self.sync_service.run_once()
        lifecycle_updates = sync_result.get('lifecycles_updated', 0)
        paper_rebuild = None
        try:
            if self.paper_reconcile_fn is not None:
                paper_rebuild = self.paper_reconcile_fn(apply=True)
            else:
                from paper_position_reconciliation import reconcile_paper_positions
                paper_rebuild = reconcile_paper_positions(apply=True)
        except Exception as exc:  # pragma: no cover
            paper_rebuild = {'success': False, 'warning': str(exc)}

        lifecycle = self._fetch_lifecycle(proposal.get('lifecycle_id') or attempt.get('lifecycle_id'))
        readiness = self._assess_reconciliation_readiness(
            attempt=attempt,
            proposal=proposal,
            lifecycle=lifecycle,
            sync_result=sync_result,
        )

        if readiness['reconciled']:
            attempt = self.submit_repository.transition_state(
                attempt['id'],
                from_state='reconcile_pending',
                to_state='reconciled',
                patch={
                    'reconciled_at': self.now,
                    'reservation_status': 'released',
                    'attempt_status': 'ready_to_submit' if attempt.get('broker_order_id') else attempt.get('attempt_status'),
                    'reconciliation_status': 'reconciled',
                    'reconciliation_hook': 'post_submit_reconciliation',
                    'response_payload': sync_result,
                    'audit_payload': {
                        'hook': 'post_submit_reconciliation',
                        'broker_called': bool(attempt.get('broker_order_id')),
                        'sync_result': sync_result,
                        'lifecycle_updates': lifecycle_updates,
                        'paper_rebuild': paper_rebuild,
                        'readiness': readiness,
                    },
                },
            )
            attempt = self.submit_repository.mark_released(attempt['id'], reservation_status='released', submit_state='reconciled')
            proposal = self.proposal_repository.update_submit_state(
                proposal_id,
                submit_state='ready_to_submit' if proposal.get('external_order_ref') else proposal.get('submit_state'),
                submit_state_reason='reconciled after futu sim submit',
                submit_last_attempt_id=attempt['id'],
                reconciliation_status='reconciled',
                reconciliation_hook='post_submit_reconciliation',
                reconciliation_payload={
                    'sync_result': sync_result,
                    'paper_rebuild': paper_rebuild,
                    'sim_only_guard': True,
                    'readiness': readiness,
                },
            )
        else:
            attempt = self.submit_repository.transition_state(
                attempt['id'],
                from_state='reconcile_pending',
                to_state='reconcile_pending',
                patch={
                    'reservation_status': 'active',
                    'reconciliation_due_at': self.now,
                    'reconciliation_status': 'awaiting_reconciliation',
                    'reconciliation_hook': 'post_submit_reconciliation_pending',
                    'response_payload': sync_result,
                    'audit_payload': {
                        'hook': 'post_submit_reconciliation_pending',
                        'broker_called': bool(attempt.get('broker_order_id')),
                        'sync_result': sync_result,
                        'lifecycle_updates': lifecycle_updates,
                        'paper_rebuild': paper_rebuild,
                        'readiness': readiness,
                    },
                },
            )
            proposal = self.proposal_repository.update_submit_state(
                proposal_id,
                submit_last_attempt_id=attempt['id'],
                reconciliation_status='awaiting_reconciliation',
                reconciliation_hook='post_submit_reconciliation_pending',
                reconciliation_payload={
                    'sync_result': sync_result,
                    'paper_rebuild': paper_rebuild,
                    'sim_only_guard': True,
                    'readiness': readiness,
                },
            )
        return {
            'proposal_id': proposal_id,
            'broker_called': bool(attempt.get('broker_order_id')),
            'lifecycle_updates': lifecycle_updates,
            'sync_result': sync_result,
            'paper_rebuild': paper_rebuild,
            'readiness': readiness,
            'proposal': proposal,
            'attempt': attempt,
        }


    def _assess_reconciliation_readiness(
        self,
        *,
        attempt: Dict[str, Any],
        proposal: Dict[str, Any],
        lifecycle: Dict[str, Any],
        sync_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        lifecycle_status = str(lifecycle.get('status') or '').lower()
        broker_order_status = str((sync_result.get('broker_order') or {}).get('status') or '').lower()
        fill_detected = bool(sync_result.get('fill_detected')) or sync_result.get('fills_upserted', 0) > 0
        broker_order_terminal = broker_order_status in {'filled', 'partial_filled'}
        lifecycle_closed = lifecycle_status == 'closed'
        reconciled = fill_detected or broker_order_terminal or lifecycle_closed
        reason = 'pending'
        if lifecycle_closed:
            reason = 'lifecycle_closed'
        elif fill_detected:
            reason = 'broker_fill_detected'
        elif broker_order_terminal:
            reason = f'broker_order_{broker_order_status}'
        return {
            'reconciled': reconciled,
            'reason': reason,
            'fill_detected': fill_detected,
            'broker_order_status': broker_order_status or None,
            'lifecycle_status': lifecycle_status or None,
            'external_order_ref': attempt.get('external_order_ref') or proposal.get('external_order_ref') or attempt.get('broker_order_id'),
        }

    def _build_broker_submit_payload(self, proposal: Dict[str, Any], attempt: Dict[str, Any]) -> Dict[str, Any]:
        lifecycle = self._fetch_lifecycle(proposal.get('lifecycle_id'))
        qty = int(float(lifecycle.get('position_qty') or 0))
        if qty <= 0:
            raise ValueError(f"invalid exit qty for lifecycle {proposal.get('lifecycle_id')}: {qty}")
        return {
            'symbol': proposal.get('symbol'),
            'order_type': str(proposal.get('action_side') or '').upper(),
            'quantity': qty,
            'price': self._resolve_submit_price(proposal),
            'source_signal_id': lifecycle.get('signal_id'),
            'proposal_id': proposal.get('id'),
            'candidate_id': proposal.get('candidate_id'),
            'lifecycle_id': proposal.get('lifecycle_id'),
            'attempt_id': attempt.get('id'),
            'idempotency_key': attempt.get('idempotency_key'),
            'external_correlation_id': attempt.get('external_correlation_id'),
            'sim_only_guard': True,
        }

    def _submit_to_futu_sim(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.broker_submit_fn is not None:
            result = self.broker_submit_fn(**payload)
        else:
            from paper_trading import submit_paper_order
            result = submit_paper_order(
                symbol=payload['symbol'],
                order_type=payload['order_type'],
                quantity=payload['quantity'],
                price=payload['price'],
                source_signal_id=payload.get('source_signal_id'),
            )
        if isinstance(result, dict):
            result.setdefault('sim_only_guard', True)
        return result

    def _sim_only_guard(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        trading_mode = SystemConfig.get_trading_mode()
        paper_enabled = SystemConfig.is_paper_trading()
        proposal_mode = str(proposal.get('proposal_mode') or '').lower()
        allowed = paper_enabled and trading_mode == 1 and proposal_mode == 'live'
        reason = None
        if not paper_enabled:
            reason = 'paper_trading_enabled is false; sim-only guard blocked submit'
        elif trading_mode != 1:
            reason = f'paper_trading_mode={trading_mode}; sim-only guard requires trading_mode=1'
        elif proposal_mode != 'live':
            reason = f'proposal_mode={proposal_mode}; sim-only submit requires live proposal stage gate'
        return {
            'allowed': allowed,
            'sim_only_guard': True,
            'paper_trading_enabled': paper_enabled,
            'trading_mode': trading_mode,
            'proposal_mode': proposal_mode,
            'reason': reason,
        }

    def _fetch_lifecycle(self, lifecycle_id: Any) -> Dict[str, Any]:
        if lifecycle_id in (None, ''):
            return {}
        try:
            from config.database import get_db_cursor
            with get_db_cursor() as cursor:
                cursor.execute('SELECT * FROM trade_lifecycles WHERE id = %s LIMIT 1', (lifecycle_id,))
                return cursor.fetchone() or {}
        except Exception:
            return {}

    @staticmethod
    def _resolve_submit_price(proposal: Dict[str, Any]) -> float:
        snapshot = proposal.get('audit_payload', {}).get('snapshot') if isinstance(proposal.get('audit_payload'), dict) else {}
        candidate = proposal.get('audit_payload', {}).get('candidate') if isinstance(proposal.get('audit_payload'), dict) else {}
        price = None
        for source in (snapshot, candidate, proposal):
            if not isinstance(source, dict):
                continue
            for key in ('market_price', 'current_price', 'threshold_value'):
                value = source.get(key)
                if value not in (None, ''):
                    price = float(value)
                    break
            if price is not None:
                break
        if price is None or price <= 0:
            raise ValueError('unable to resolve positive submit price for futu sim exit order')
        return price

    @staticmethod
    def _stable_key(prefix: str, proposal: Dict[str, Any]) -> str:
        base = '|'.join(
            [
                prefix,
                str(proposal.get('id') or ''),
                str(proposal.get('candidate_id') or ''),
                str(proposal.get('lifecycle_id') or ''),
                str(proposal.get('proposal_mode') or ''),
                str(proposal.get('action_type') or ''),
                str(proposal.get('action_side') or ''),
            ]
        )
        digest = hashlib.sha256(base.encode('utf-8')).hexdigest()[:24]
        return f'{prefix}:{digest}'
