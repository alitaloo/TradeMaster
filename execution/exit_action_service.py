from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from config.database import get_db_cursor
from execution.exit_action_repository import ExitActionProposalRepository
from execution.exit_candidate_repository import ExitCandidateRepository
from models.system_config import SystemConfig

OPEN_LIFECYCLE_STATUSES = ('signal_created', 'order_submitted', 'partially_filled', 'filled_open', 'exit_pending')


@dataclass
class ActionSummary:
    scanned_active_candidates: int = 0
    proposed_count: int = 0
    blocked_count: int = 0
    stale_count: int = 0
    persisted_count: int = 0
    gate_skipped_count: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            'scanned_active_candidates': self.scanned_active_candidates,
            'proposed_count': self.proposed_count,
            'blocked_count': self.blocked_count,
            'stale_count': self.stale_count,
            'persisted_count': self.persisted_count,
            'gate_skipped_count': self.gate_skipped_count,
        }


class ExitActionService:
    def __init__(
        self,
        *,
        now: Optional[datetime] = None,
        candidate_repository: Optional[ExitCandidateRepository] = None,
        proposal_repository: Optional[ExitActionProposalRepository] = None,
    ):
        self.now = now or datetime.now()
        self.candidate_repository = candidate_repository or ExitCandidateRepository()
        self.proposal_repository = proposal_repository or ExitActionProposalRepository()

    def generate_proposals(self, *, limit: int = 200, persist: bool = True) -> Dict[str, Any]:
        gate_enabled = SystemConfig.get_bool('risk.exit_action_enabled', False)
        gate_mode = (SystemConfig.get('risk.exit_action_mode', 'off') or 'off').strip().lower()
        freshness_window_seconds = max(0, SystemConfig.get_int('risk.exit_action_freshness_seconds', 120))
        active_candidates = self.candidate_repository.list_candidates(statuses=('active',), limit=limit)
        summary = ActionSummary(scanned_active_candidates=len(active_candidates))
        evaluations: List[Dict[str, Any]] = []

        if not gate_enabled or gate_mode == 'off':
            summary.gate_skipped_count = len(active_candidates)
            return {
                'generated_at': self.now.isoformat(sep=' '),
                'config': {
                    'exit_action_enabled': gate_enabled,
                    'exit_action_mode': gate_mode,
                    'freshness_window_seconds': freshness_window_seconds,
                    'persist_proposals': persist,
                },
                'summary': summary.to_dict(),
                'proposals': [],
                'gate': {
                    'enabled': gate_enabled,
                    'mode': gate_mode,
                    'ready': False,
                    'reason': 'exit action gate is disabled; no executable dry-run proposals generated',
                },
            }

        proposal_mode = 'dry_run' if gate_mode != 'live' else 'live'
        for candidate in active_candidates:
            evaluation = self.evaluate_candidate(candidate, freshness_window_seconds=freshness_window_seconds, proposal_mode=proposal_mode)
            if persist:
                evaluation['proposal_record'] = self.proposal_repository.upsert_proposal(evaluation['proposal'])
                summary.persisted_count += 1
            status = evaluation['proposal']['status']
            if status == 'proposed':
                summary.proposed_count += 1
            elif status == 'blocked':
                summary.blocked_count += 1
            elif status == 'stale':
                summary.stale_count += 1
            evaluations.append(evaluation)

        return {
            'generated_at': self.now.isoformat(sep=' '),
            'config': {
                'exit_action_enabled': gate_enabled,
                'exit_action_mode': gate_mode,
                'freshness_window_seconds': freshness_window_seconds,
                'persist_proposals': persist,
            },
            'summary': summary.to_dict(),
            'proposals': [row['proposal_record'] if persist else row['proposal'] for row in evaluations],
            'evaluations': evaluations,
            'gate': {
                'enabled': gate_enabled,
                'mode': gate_mode,
                'ready': proposal_mode == 'dry_run',
                'reason': 'dry-run proposals generated without calling broker' if proposal_mode == 'dry_run' else 'live mode reserved for future stage',
            },
        }

    def list_proposals(self, *, limit: int = 200, statuses: Optional[List[str]] = None) -> Dict[str, Any]:
        rows = self.proposal_repository.list_proposals(statuses=statuses, limit=limit)
        return {
            'listed_at': self.now.isoformat(sep=' '),
            'count': len(rows),
            'statuses': statuses or [],
            'proposals': rows,
        }

    def evaluate_candidate(self, candidate: Dict[str, Any], *, freshness_window_seconds: int, proposal_mode: str) -> Dict[str, Any]:
        lifecycle = self.fetch_lifecycle(candidate['lifecycle_id'])
        snapshot = self.fetch_latest_position_snapshot(candidate.get('symbol'))

        reasons: List[str] = []
        stale_reasons: List[str] = []
        candidate_active = candidate.get('status') == 'active'
        lifecycle_open = lifecycle.get('status') in OPEN_LIFECYCLE_STATUSES if lifecycle else False
        snapshot_exists = bool(snapshot)
        snapshot_age_seconds = self._compute_age_seconds(snapshot.get('snapshot_time') if snapshot else None)
        snapshot_fresh = snapshot_age_seconds is not None and snapshot_age_seconds <= freshness_window_seconds
        candidate_age_seconds = self._compute_age_seconds(candidate.get('last_detected_at'))
        candidate_fresh = candidate_age_seconds is not None and candidate_age_seconds <= freshness_window_seconds

        if not candidate_active:
            reasons.append('candidate is not active')
        if not lifecycle:
            reasons.append('lifecycle missing')
        elif not lifecycle_open:
            reasons.append(f"lifecycle not open/eligible: {lifecycle.get('status')}")
        if not snapshot_exists:
            stale_reasons.append('position snapshot missing')
        if snapshot_exists and not snapshot_fresh:
            stale_reasons.append(f'position snapshot stale: age={snapshot_age_seconds}s > {freshness_window_seconds}s')
        if not candidate_fresh:
            stale_reasons.append(f'candidate stale: age={candidate_age_seconds}s > {freshness_window_seconds}s')

        action_side = self._resolve_exit_side(lifecycle.get('direction') if lifecycle else candidate.get('direction'))
        status = 'proposed'
        block_reason = None
        action_reason = f"dry-run {candidate.get('candidate_type')} candidate eligible for exit action proposal"
        if stale_reasons:
            status = 'stale'
            block_reason = '; '.join(stale_reasons)
            action_reason = None
        elif reasons:
            status = 'blocked'
            block_reason = '; '.join(reasons)
            action_reason = None

        proposal = {
            'candidate_id': candidate['id'],
            'lifecycle_id': candidate['lifecycle_id'],
            'symbol': candidate.get('symbol'),
            'action_type': 'exit_market',
            'action_side': action_side,
            'proposal_mode': proposal_mode,
            'status': status,
            'gate_enabled': True,
            'gate_mode': proposal_mode,
            'freshness_window_seconds': freshness_window_seconds,
            'freshness_checked_at': self.now,
            'candidate_last_detected_at': candidate.get('last_detected_at'),
            'lifecycle_status': lifecycle.get('status') if lifecycle else None,
            'snapshot_time': snapshot.get('snapshot_time') if snapshot else None,
            'snapshot_age_seconds': snapshot_age_seconds,
            'action_reason': action_reason,
            'block_reason': block_reason,
            'lease_owner': None,
            'lease_token': None,
            'leased_at': None,
            'lease_expires_at': None,
            'submit_state': 'proposed' if status == 'proposed' else 'submit_blocked',
            'submit_state_reason': None if status == 'proposed' else block_reason,
            'submit_ready_at': None,
            'submit_last_attempt_id': None,
            'broker_request_key': None,
            'external_order_ref': None,
            'reconciliation_status': 'pending_submit',
            'reconciliation_hook': None,
            'reconciliation_payload': {},
            'audit_payload': {
                'candidate': {
                    'id': candidate.get('id'),
                    'lifecycle_id': candidate.get('lifecycle_id'),
                    'symbol': candidate.get('symbol'),
                    'candidate_type': candidate.get('candidate_type'),
                    'status': candidate.get('status'),
                    'detected_at': candidate.get('last_detected_at'),
                    'reason': candidate.get('reason'),
                    'threshold_value': candidate.get('threshold_value'),
                    'current_price': candidate.get('current_price'),
                },
                'lifecycle': {
                    'id': lifecycle.get('id') if lifecycle else None,
                    'status': lifecycle.get('status') if lifecycle else None,
                    'direction': lifecycle.get('direction') if lifecycle else None,
                    'position_qty': lifecycle.get('position_qty') if lifecycle else None,
                    'entry_time': lifecycle.get('entry_time') if lifecycle else None,
                },
                'snapshot': snapshot,
                'checks': {
                    'candidate_active': candidate_active,
                    'lifecycle_open': lifecycle_open,
                    'snapshot_exists': snapshot_exists,
                    'snapshot_fresh': snapshot_fresh,
                    'candidate_fresh': candidate_fresh,
                    'candidate_age_seconds': candidate_age_seconds,
                    'snapshot_age_seconds': snapshot_age_seconds,
                    'freshness_window_seconds': freshness_window_seconds,
                },
                'decision': {
                    'status': status,
                    'action_side': action_side,
                    'action_type': 'exit_market',
                    'action_reason': action_reason,
                    'block_reason': block_reason,
                },
            },
        }
        return {'candidate': candidate, 'lifecycle': lifecycle, 'snapshot': snapshot, 'proposal': proposal}

    def fetch_lifecycle(self, lifecycle_id: int) -> Dict[str, Any]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM trade_lifecycles WHERE id = %s LIMIT 1', (lifecycle_id,))
            return cursor.fetchone() or {}

    def fetch_latest_position_snapshot(self, symbol: Optional[str], account_type: str = 'futu_sim') -> Dict[str, Any]:
        if not symbol:
            return {}
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT snapshot_time, broker, account_type, symbol, qty, avg_cost, market_price, market_value, unrealized_pnl
                FROM broker_positions_snapshot
                WHERE account_type = %s AND symbol = %s
                ORDER BY snapshot_time DESC, id DESC
                LIMIT 1
                """,
                (account_type, symbol),
            )
            return cursor.fetchone() or {}

    def _compute_age_seconds(self, value: Any) -> Optional[int]:
        dt = self._to_datetime(value)
        if dt is None:
            return None
        return max(0, int((self.now - dt).total_seconds()))

    @staticmethod
    def _resolve_exit_side(direction: Optional[str]) -> str:
        return 'sell' if str(direction or 'long').lower() == 'long' else 'buy'

    @staticmethod
    def _to_datetime(value: Any) -> Optional[datetime]:
        if value is None or value == '':
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip().replace('Z', '+00:00')
        for fmt in (None, '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S'):
            try:
                if fmt is None:
                    return datetime.fromisoformat(text)
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        return None
