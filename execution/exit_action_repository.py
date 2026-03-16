from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from config.database import get_db_cursor


class ExitActionProposalRepository:
    LEASEABLE_STATES = ('proposed', 'submit_failed', 'submit_blocked')

    def upsert_proposal(self, proposal: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.find_by_candidate(candidate_id=proposal['candidate_id'], proposal_mode=proposal['proposal_mode'])
        payload_json = json.dumps(proposal.get('audit_payload') or {}, ensure_ascii=False, default=str)
        params = (
            proposal['candidate_id'],
            proposal['lifecycle_id'],
            proposal['symbol'],
            proposal['action_type'],
            proposal['action_side'],
            proposal['proposal_mode'],
            proposal['status'],
            1 if proposal.get('gate_enabled') else 0,
            proposal.get('gate_mode'),
            proposal.get('freshness_window_seconds'),
            proposal['freshness_checked_at'],
            proposal.get('candidate_last_detected_at'),
            proposal.get('lifecycle_status'),
            proposal.get('snapshot_time'),
            proposal.get('snapshot_age_seconds'),
            proposal.get('action_reason'),
            proposal.get('block_reason'),
            proposal.get('lease_owner'),
            proposal.get('lease_token'),
            proposal.get('leased_at'),
            proposal.get('lease_expires_at'),
            proposal.get('submit_state', 'proposed'),
            proposal.get('submit_state_reason'),
            proposal.get('submit_ready_at'),
            proposal.get('submit_last_attempt_id'),
            proposal.get('broker_request_key'),
            proposal.get('external_order_ref'),
            proposal.get('reconciliation_status', 'pending_submit'),
            proposal.get('reconciliation_hook'),
            json.dumps(proposal.get('reconciliation_payload') or {}, ensure_ascii=False, default=str),
            payload_json,
        )
        with get_db_cursor() as cursor:
            if existing:
                update_params = (
                    proposal['lifecycle_id'],
                    proposal['symbol'],
                    proposal['action_type'],
                    proposal['action_side'],
                    proposal['status'],
                    1 if proposal.get('gate_enabled') else 0,
                    proposal.get('gate_mode'),
                    proposal.get('freshness_window_seconds'),
                    proposal['freshness_checked_at'],
                    proposal.get('candidate_last_detected_at'),
                    proposal.get('lifecycle_status'),
                    proposal.get('snapshot_time'),
                    proposal.get('snapshot_age_seconds'),
                    proposal.get('action_reason'),
                    proposal.get('block_reason'),
                    proposal.get('lease_owner'),
                    proposal.get('lease_token'),
                    proposal.get('leased_at'),
                    proposal.get('lease_expires_at'),
                    proposal.get('submit_state', existing.get('submit_state', 'proposed')),
                    proposal.get('submit_state_reason'),
                    proposal.get('submit_ready_at'),
                    proposal.get('submit_last_attempt_id'),
                    proposal.get('broker_request_key'),
                    proposal.get('external_order_ref'),
                    proposal.get('reconciliation_status', existing.get('reconciliation_status', 'pending_submit')),
                    proposal.get('reconciliation_hook'),
                    json.dumps(proposal.get('reconciliation_payload') or {}, ensure_ascii=False, default=str),
                    payload_json,
                    existing['id'],
                )
                cursor.execute(
                    """
                    UPDATE lifecycle_exit_action_proposals
                    SET lifecycle_id = %s,
                        symbol = %s,
                        action_type = %s,
                        action_side = %s,
                        status = %s,
                        gate_enabled = %s,
                        gate_mode = %s,
                        freshness_window_seconds = %s,
                        freshness_checked_at = %s,
                        candidate_last_detected_at = %s,
                        lifecycle_status = %s,
                        snapshot_time = %s,
                        snapshot_age_seconds = %s,
                        action_reason = %s,
                        block_reason = %s,
                        lease_owner = %s,
                        lease_token = %s,
                        leased_at = %s,
                        lease_expires_at = %s,
                        submit_state = %s,
                        submit_state_reason = %s,
                        submit_ready_at = %s,
                        submit_last_attempt_id = %s,
                        broker_request_key = %s,
                        external_order_ref = %s,
                        reconciliation_status = %s,
                        reconciliation_hook = %s,
                        reconciliation_payload = %s,
                        audit_payload = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    update_params,
                )
                proposal_id = existing['id']
            else:
                cursor.execute(
                    """
                    INSERT INTO lifecycle_exit_action_proposals (
                        candidate_id, lifecycle_id, symbol, action_type, action_side,
                        proposal_mode, status, gate_enabled, gate_mode,
                        freshness_window_seconds, freshness_checked_at,
                        candidate_last_detected_at, lifecycle_status, snapshot_time,
                        snapshot_age_seconds, action_reason, block_reason,
                        lease_owner, lease_token, leased_at, lease_expires_at,
                        submit_state, submit_state_reason, submit_ready_at, submit_last_attempt_id,
                        broker_request_key, external_order_ref,
                        reconciliation_status, reconciliation_hook, reconciliation_payload,
                        audit_payload
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    params,
                )
                proposal_id = cursor.lastrowid
        return self.get_by_id(proposal_id)

    def find_by_candidate(self, *, candidate_id: int, proposal_mode: str = 'dry_run') -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM lifecycle_exit_action_proposals WHERE candidate_id = %s AND proposal_mode = %s LIMIT 1',
                (candidate_id, proposal_mode),
            )
            row = cursor.fetchone()
        return self._serialize_row(row) if row else None

    def acquire_lease(self, *, proposal_id: int, lease_owner: str, lease_token: str, leased_at: datetime, lease_expires_at: datetime) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE lifecycle_exit_action_proposals
                SET lease_owner = %s,
                    lease_token = %s,
                    leased_at = %s,
                    lease_expires_at = %s,
                    submit_state = 'leased',
                    submit_state_reason = 'lease acquired',
                    updated_at = NOW()
                WHERE id = %s
                  AND status = 'proposed'
                  AND (submit_state IN ('proposed','submit_failed','submit_blocked'))
                  AND (lease_expires_at IS NULL OR lease_expires_at <= %s OR lease_owner = %s)
                """,
                (lease_owner, lease_token, leased_at, lease_expires_at, proposal_id, leased_at, lease_owner),
            )
            updated = cursor.rowcount
        return self.get_by_id(proposal_id) if updated else None

    def update_submit_state(self, proposal_id: int, **fields: Any) -> Dict[str, Any]:
        allowed = {
            'status', 'submit_state', 'submit_state_reason', 'submit_ready_at', 'submit_last_attempt_id',
            'broker_request_key', 'external_order_ref', 'reconciliation_status', 'reconciliation_hook',
            'reconciliation_payload', 'lease_owner', 'lease_token', 'leased_at', 'lease_expires_at',
            'action_reason', 'block_reason'
        }
        assignments = []
        params: List[Any] = []
        for key, value in fields.items():
            if key not in allowed:
                continue
            assignments.append(f"{key} = %s")
            if key in ('reconciliation_payload',) and not isinstance(value, str):
                params.append(json.dumps(value or {}, ensure_ascii=False, default=str))
            else:
                params.append(value)
        if not assignments:
            return self.get_by_id(proposal_id)
        sql = 'UPDATE lifecycle_exit_action_proposals SET ' + ', '.join(assignments) + ', updated_at = NOW() WHERE id = %s'
        params.append(proposal_id)
        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
        return self.get_by_id(proposal_id)

    def list_proposals(self, *, statuses: Optional[Sequence[str]] = None, limit: int = 200) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if statuses:
            where.append(f"status IN ({', '.join(['%s'] * len(statuses))})")
            params.extend(statuses)
        sql = 'SELECT * FROM lifecycle_exit_action_proposals'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY updated_at DESC, id DESC LIMIT %s'
        params.append(limit)
        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall() or []
        return [self._serialize_row(row) for row in rows]

    def get_by_id(self, proposal_id: int) -> Dict[str, Any]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM lifecycle_exit_action_proposals WHERE id = %s LIMIT 1', (proposal_id,))
            row = cursor.fetchone()
        return self._serialize_row(row or {})

    @classmethod
    def _serialize_row(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for key, value in (row or {}).items():
            if isinstance(value, Decimal):
                payload[key] = float(value)
            elif isinstance(value, datetime):
                payload[key] = value.isoformat(sep=' ')
            else:
                payload[key] = value
        for key in ('audit_payload', 'reconciliation_payload'):
            raw = payload.get(key)
            if isinstance(raw, str):
                try:
                    payload[key] = json.loads(raw)
                except Exception:
                    pass
        return payload
