from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from config.database import get_db_cursor


class SubmitAttemptRepository:
    def find_by_proposal_id(self, proposal_id: int) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM lifecycle_exit_submit_attempts WHERE proposal_id = %s LIMIT 1', (proposal_id,))
            row = cursor.fetchone()
        return self._serialize_row(row) if row else None

    def get_by_id(self, attempt_id: int) -> Dict[str, Any]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM lifecycle_exit_submit_attempts WHERE id = %s LIMIT 1', (attempt_id,))
            row = cursor.fetchone()
        return self._serialize_row(row or {})

    def acquire_reservation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        existing = self.find_by_proposal_id(payload['proposal_id'])
        audit_payload = json.dumps(payload.get('audit_payload') or {}, ensure_ascii=False, default=str)
        if existing:
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE lifecycle_exit_submit_attempts
                    SET reservation_status = 'active',
                        lease_owner = %s,
                        lease_token = COALESCE(lease_token, %s),
                        lease_acquired_at = %s,
                        lease_expires_at = %s,
                        broker = COALESCE(broker, 'futu'),
                        broker_request_key = COALESCE(broker_request_key, %s),
                        submit_state = CASE
                            WHEN submit_state IN ('cancelled','expired','failed') THEN 'reserved'
                            ELSE submit_state
                        END,
                        audit_payload = %s,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        payload['lease_owner'],
                        payload['idempotency_key'],
                        payload['lease_acquired_at'],
                        payload['lease_expires_at'],
                        payload['idempotency_key'],
                        audit_payload,
                        existing['id'],
                    ),
                )
            return self.get_by_id(existing['id'])

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lifecycle_exit_submit_attempts (
                    proposal_id, candidate_id, lifecycle_id, symbol, proposal_mode,
                    reservation_key, reservation_status, lease_owner, lease_token, lease_acquired_at, lease_expires_at,
                    broker, broker_request_key, submit_state, idempotency_key, external_correlation_id, audit_payload
                ) VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s, %s, %s, 'futu', %s, 'reserved', %s, %s, %s)
                """,
                (
                    payload['proposal_id'],
                    payload['candidate_id'],
                    payload['lifecycle_id'],
                    payload['symbol'],
                    payload['proposal_mode'],
                    payload['reservation_key'],
                    payload['lease_owner'],
                    payload['idempotency_key'],
                    payload['lease_acquired_at'],
                    payload['lease_expires_at'],
                    payload['idempotency_key'],
                    payload['idempotency_key'],
                    payload['external_correlation_id'],
                    audit_payload,
                ),
            )
            attempt_id = cursor.lastrowid
        return self.get_by_id(attempt_id)

    def transition_state(self, attempt_id: int, *, from_state: str, to_state: str, patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        patch = patch or {}
        assignments = ['submit_state = %s', 'updated_at = NOW()']
        params: list[Any] = [to_state]
        allowed = {
            'reservation_status', 'lease_owner', 'lease_token', 'lease_expires_at', 'last_error', 'failure_reason',
            'submit_requested_at', 'submit_finished_at', 'reconciliation_due_at', 'reconciled_at',
            'broker_order_id', 'broker_request_key', 'external_order_ref', 'submission_mode', 'attempt_status',
            'reconciliation_status', 'reconciliation_hook', 'reconciliation_payload',
            'request_payload', 'response_payload', 'audit_payload'
        }
        json_fields = {'audit_payload', 'reconciliation_payload', 'request_payload', 'response_payload'}
        for key, value in patch.items():
            if key not in allowed:
                continue
            assignments.append(f'{key} = %s')
            if key in json_fields and not isinstance(value, str):
                value = json.dumps(value or {}, ensure_ascii=False, default=str)
            params.append(value)
        params.extend([attempt_id, from_state])
        with get_db_cursor() as cursor:
            cursor.execute(
                f"UPDATE lifecycle_exit_submit_attempts SET {', '.join(assignments)} WHERE id = %s AND submit_state = %s",
                tuple(params),
            )
        return self.get_by_id(attempt_id)

    def mark_released(self, attempt_id: int, *, reservation_status: str = 'released', submit_state: Optional[str] = None) -> Dict[str, Any]:
        assignments = ['reservation_status = %s', 'updated_at = NOW()']
        params: list[Any] = [reservation_status]
        if submit_state:
            assignments.append('submit_state = %s')
            params.append(submit_state)
        params.append(attempt_id)
        with get_db_cursor() as cursor:
            cursor.execute(
                f"UPDATE lifecycle_exit_submit_attempts SET {', '.join(assignments)} WHERE id = %s",
                tuple(params),
            )
        return self.get_by_id(attempt_id)

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
        for key in ('audit_payload', 'reconciliation_payload', 'request_payload', 'response_payload'):
            raw = payload.get(key)
            if isinstance(raw, str):
                try:
                    payload[key] = json.loads(raw)
                except Exception:
                    pass
        return payload
