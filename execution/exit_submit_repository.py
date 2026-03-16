from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from config.database import get_db_cursor


class ExitSubmitAttemptRepository:
    def create_attempt(self, attempt: Dict[str, Any]) -> Dict[str, Any]:
        params = (
            attempt['proposal_id'],
            attempt['candidate_id'],
            attempt['lifecycle_id'],
            attempt['symbol'],
            attempt['attempt_no'],
            attempt['lease_owner'],
            attempt['lease_token'],
            attempt.get('broker', 'futu'),
            attempt['broker_request_key'],
            attempt.get('external_order_ref'),
            attempt.get('submission_mode', 'dry_run'),
            attempt['attempt_status'],
            attempt.get('failure_reason'),
            attempt.get('reconciliation_status', 'pending_submit'),
            attempt.get('reconciliation_hook'),
            json.dumps(attempt.get('reconciliation_payload') or {}, ensure_ascii=False, default=str),
            json.dumps(attempt.get('request_payload') or {}, ensure_ascii=False, default=str),
            json.dumps(attempt.get('response_payload') or {}, ensure_ascii=False, default=str),
            attempt.get('simulated_at'),
        )
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lifecycle_exit_submit_attempts (
                    proposal_id, candidate_id, lifecycle_id, symbol, attempt_no,
                    lease_owner, lease_token, broker, broker_request_key, external_order_ref,
                    submission_mode, attempt_status, failure_reason,
                    reconciliation_status, reconciliation_hook, reconciliation_payload,
                    request_payload, response_payload, simulated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                params,
            )
            attempt_id = cursor.lastrowid
        return self.get_by_id(attempt_id)

    def get_by_id(self, attempt_id: int) -> Dict[str, Any]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM lifecycle_exit_submit_attempts WHERE id = %s LIMIT 1', (attempt_id,))
            row = cursor.fetchone() or {}
        return self._serialize_row(row)

    def find_by_request_key(self, *, broker: str, broker_request_key: str) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM lifecycle_exit_submit_attempts WHERE broker = %s AND broker_request_key = %s LIMIT 1',
                (broker, broker_request_key),
            )
            row = cursor.fetchone()
        return self._serialize_row(row) if row else None

    def get_latest_attempt(self, *, proposal_id: int) -> Optional[Dict[str, Any]]:
        with get_db_cursor() as cursor:
            cursor.execute(
                'SELECT * FROM lifecycle_exit_submit_attempts WHERE proposal_id = %s ORDER BY attempt_no DESC, id DESC LIMIT 1',
                (proposal_id,),
            )
            row = cursor.fetchone()
        return self._serialize_row(row) if row else None

    def list_attempts(self, *, statuses: Optional[Sequence[str]] = None, proposal_id: Optional[int] = None, limit: int = 200) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if proposal_id is not None:
            where.append('proposal_id = %s')
            params.append(proposal_id)
        if statuses:
            where.append(f"attempt_status IN ({', '.join(['%s'] * len(statuses))})")
            params.extend(statuses)
        sql = 'SELECT * FROM lifecycle_exit_submit_attempts'
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY updated_at DESC, id DESC LIMIT %s'
        params.append(limit)
        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall() or []
        return [self._serialize_row(row) for row in rows]

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
        for key in ('reconciliation_payload', 'request_payload', 'response_payload'):
            raw = payload.get(key)
            if isinstance(raw, str):
                try:
                    payload[key] = json.loads(raw)
                except Exception:
                    pass
        return payload
