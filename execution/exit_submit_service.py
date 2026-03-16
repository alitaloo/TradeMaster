from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from execution.exit_action_repository import ExitActionProposalRepository
from execution.exit_reconciliation_hook import ExitReconciliationHook
from execution.exit_submit_repository import ExitSubmitAttemptRepository


@dataclass
class SubmitSummary:
    scanned_proposals: int = 0
    leased_count: int = 0
    ready_count: int = 0
    blocked_count: int = 0
    simulated_count: int = 0
    failed_count: int = 0
    idempotent_reuse_count: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            'scanned_proposals': self.scanned_proposals,
            'leased_count': self.leased_count,
            'ready_count': self.ready_count,
            'blocked_count': self.blocked_count,
            'simulated_count': self.simulated_count,
            'failed_count': self.failed_count,
            'idempotent_reuse_count': self.idempotent_reuse_count,
        }


class ExitSubmitService:
    def __init__(
        self,
        *,
        now: Optional[datetime] = None,
        proposal_repository: Optional[ExitActionProposalRepository] = None,
        attempt_repository: Optional[ExitSubmitAttemptRepository] = None,
        reconciliation_hook: Optional[ExitReconciliationHook] = None,
    ):
        self.now = now or datetime.now()
        self.proposal_repository = proposal_repository or ExitActionProposalRepository()
        self.attempt_repository = attempt_repository or ExitSubmitAttemptRepository()
        self.reconciliation_hook = reconciliation_hook or ExitReconciliationHook()

    def process_dry_run_submissions(self, *, lease_owner: str, limit: int = 200, lease_seconds: int = 120) -> Dict[str, Any]:
        proposals = self.proposal_repository.list_proposals(statuses=['proposed'], limit=limit)
        summary = SubmitSummary(scanned_proposals=len(proposals))
        results: List[Dict[str, Any]] = []
        for proposal in proposals:
            outcome = self.process_single_proposal(proposal, lease_owner=lease_owner, lease_seconds=lease_seconds)
            state = outcome['proposal']['submit_state']
            if outcome.get('leased'):
                summary.leased_count += 1
            if outcome.get('idempotent_reuse'):
                summary.idempotent_reuse_count += 1
            if state == 'ready_to_submit':
                summary.ready_count += 1
            elif state == 'submit_blocked':
                summary.blocked_count += 1
            elif state == 'submit_simulated':
                summary.simulated_count += 1
            elif state == 'submit_failed':
                summary.failed_count += 1
            results.append(outcome)
        return {
            'processed_at': self.now.isoformat(sep=' '),
            'lease_owner': lease_owner,
            'lease_seconds': lease_seconds,
            'summary': summary.to_dict(),
            'results': results,
        }

    def process_single_proposal(self, proposal: Dict[str, Any], *, lease_owner: str, lease_seconds: int = 120) -> Dict[str, Any]:
        leased_at = self.now
        lease_expires_at = leased_at + timedelta(seconds=max(1, lease_seconds))
        lease_token = f"lease-{proposal['id']}-{uuid4().hex[:12]}"
        leased = self.proposal_repository.acquire_lease(
            proposal_id=proposal['id'],
            lease_owner=lease_owner,
            lease_token=lease_token,
            leased_at=leased_at,
            lease_expires_at=lease_expires_at,
        )
        if not leased:
            current = self.proposal_repository.get_by_id(proposal['id'])
            return {
                'proposal': current,
                'leased': False,
                'skipped': True,
                'reason': 'lease unavailable or proposal no longer eligible',
            }

        request_key = leased.get('broker_request_key') or self._build_broker_request_key(leased)
        existing_attempt = self.attempt_repository.find_by_request_key(broker='futu', broker_request_key=request_key)
        if existing_attempt:
            updated = self.proposal_repository.update_submit_state(
                leased['id'],
                submit_state=existing_attempt.get('attempt_status'),
                submit_state_reason='reused existing submit attempt by broker_request_key',
                submit_last_attempt_id=existing_attempt.get('id'),
                broker_request_key=request_key,
                external_order_ref=existing_attempt.get('external_order_ref'),
                reconciliation_status=existing_attempt.get('reconciliation_status'),
                reconciliation_hook=existing_attempt.get('reconciliation_hook'),
                reconciliation_payload=existing_attempt.get('reconciliation_payload') or {},
            )
            return {
                'proposal': updated,
                'leased': True,
                'idempotent_reuse': True,
                'attempt': existing_attempt,
            }

        ready = self.proposal_repository.update_submit_state(
            leased['id'],
            submit_state='ready_to_submit',
            submit_state_reason='dry-run pre-live guard passed; broker call intentionally disabled',
            submit_ready_at=self.now,
            broker_request_key=request_key,
            reconciliation_status='pending_submit',
            reconciliation_hook='paper_position_reconciliation',
            reconciliation_payload={},
        )

        latest_attempt = self.attempt_repository.get_latest_attempt(proposal_id=ready['id'])
        attempt_no = int(latest_attempt.get('attempt_no', 0)) + 1 if latest_attempt else 1
        external_order_ref = f"SIMULATED-{ready['id']}-{attempt_no}"
        attempt = self.attempt_repository.create_attempt({
            'proposal_id': ready['id'],
            'candidate_id': ready['candidate_id'],
            'lifecycle_id': ready['lifecycle_id'],
            'symbol': ready['symbol'],
            'attempt_no': attempt_no,
            'lease_owner': lease_owner,
            'lease_token': ready['lease_token'],
            'broker': 'futu',
            'broker_request_key': request_key,
            'external_order_ref': external_order_ref,
            'submission_mode': ready.get('proposal_mode', 'dry_run'),
            'attempt_status': 'submit_simulated',
            'reconciliation_status': 'awaiting_reconciliation',
            'reconciliation_hook': 'paper_position_reconciliation',
            'reconciliation_payload': {},
            'request_payload': {
                'proposal_id': ready['id'],
                'candidate_id': ready['candidate_id'],
                'action_type': ready.get('action_type'),
                'action_side': ready.get('action_side'),
                'mode': ready.get('proposal_mode'),
                'guardrail': 'pre_live_safety_pack',
            },
            'response_payload': {
                'simulation': True,
                'submitted': False,
                'boundary': 'pre_live',
                'message': 'No broker API invoked. Dry-run submission only.',
            },
            'simulated_at': self.now,
        })
        reconciliation_payload = self.reconciliation_hook.build_pending_payload(ready, attempt)
        updated = self.proposal_repository.update_submit_state(
            ready['id'],
            submit_state='submit_simulated',
            submit_state_reason='dry-run simulated submission recorded; live broker path still disabled',
            submit_last_attempt_id=attempt['id'],
            broker_request_key=request_key,
            external_order_ref=external_order_ref,
            reconciliation_status='awaiting_reconciliation',
            reconciliation_hook='paper_position_reconciliation',
            reconciliation_payload=reconciliation_payload,
        )
        attempt = self.attempt_repository.get_by_id(attempt['id'])
        return {
            'proposal': updated,
            'leased': True,
            'idempotent_reuse': False,
            'attempt': attempt,
        }

    def inspect_state(self, *, limit: int = 200, statuses: Optional[List[str]] = None) -> Dict[str, Any]:
        proposals = self.proposal_repository.list_proposals(statuses=statuses, limit=limit)
        items = []
        for proposal in proposals:
            items.append({
                'proposal_id': proposal.get('id'),
                'candidate_id': proposal.get('candidate_id'),
                'symbol': proposal.get('symbol'),
                'status': proposal.get('status'),
                'submit_state': proposal.get('submit_state'),
                'submit_state_reason': proposal.get('submit_state_reason'),
                'lease_owner': proposal.get('lease_owner'),
                'lease_expires_at': proposal.get('lease_expires_at'),
                'broker_request_key': proposal.get('broker_request_key'),
                'external_order_ref': proposal.get('external_order_ref'),
                'reconciliation_status': proposal.get('reconciliation_status'),
                'submit_last_attempt_id': proposal.get('submit_last_attempt_id'),
            })
        return {
            'inspected_at': self.now.isoformat(sep=' '),
            'count': len(items),
            'items': items,
        }

    @staticmethod
    def _build_broker_request_key(proposal: Dict[str, Any]) -> str:
        mode = proposal.get('proposal_mode', 'dry_run')
        return f"exit:{mode}:{proposal.get('id')}:{proposal.get('candidate_id')}"
