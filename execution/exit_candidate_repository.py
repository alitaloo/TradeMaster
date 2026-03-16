from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from config.database import get_db_cursor


class ExitCandidateRepository:
    ACTIVE_STATUS = 'active'
    RESOLVED_STATUS = 'resolved'
    IGNORED_STATUS = 'ignored'

    def persist_candidate(self, candidate: Dict[str, Any], *, detected_at: datetime, cooldown_seconds: int) -> Dict[str, Any]:
        lifecycle_id = candidate['lifecycle_id']
        candidate_type = candidate['candidate_type']
        symbol = candidate.get('symbol')
        cooldown_seconds = max(0, int(cooldown_seconds or 0))
        latest_active = self.find_latest(lifecycle_id=lifecycle_id, candidate_type=candidate_type, statuses=(self.ACTIVE_STATUS,))

        if latest_active is not None:
            last_detected_at = self._to_datetime(latest_active.get('last_detected_at') or latest_active.get('first_detected_at'))
            if last_detected_at is not None and cooldown_seconds > 0 and detected_at - last_detected_at < timedelta(seconds=cooldown_seconds):
                updated = self._refresh_candidate(latest_active['id'], candidate, detected_at)
                updated['persist_action'] = 'cooldown_refreshed'
                updated['cooldown_seconds'] = cooldown_seconds
                return self._serialize_row(updated)

            updated = self._refresh_candidate(latest_active['id'], candidate, detected_at)
            updated['persist_action'] = 'reactivated'
            updated['cooldown_seconds'] = cooldown_seconds
            return self._serialize_row(updated)

        with get_db_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO lifecycle_exit_candidates (
                    lifecycle_id, symbol, candidate_type, status,
                    first_detected_at, last_detected_at,
                    threshold_value, current_price, threshold_source, reason,
                    detection_count, metadata
                ) VALUES (%s, %s, %s, 'active', %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    lifecycle_id,
                    symbol,
                    candidate_type,
                    detected_at,
                    detected_at,
                    candidate.get('threshold_value'),
                    candidate.get('current_price'),
                    candidate.get('threshold_source'),
                    candidate.get('reason'),
                    1,
                    json.dumps(self._build_metadata(candidate), ensure_ascii=False, default=str),
                ),
            )
            inserted_id = cursor.lastrowid

        row = self.get_by_id(inserted_id)
        row['persist_action'] = 'inserted'
        row['cooldown_seconds'] = cooldown_seconds
        return self._serialize_row(row)

    def resolve_absent_candidates(self, *, lifecycle_id: int, detected_types: Sequence[str], resolved_at: datetime) -> int:
        active_rows = self.list_candidates(lifecycle_id=lifecycle_id, statuses=(self.ACTIVE_STATUS,))
        detected = set(detected_types)
        resolved = 0
        for row in active_rows:
            if row['candidate_type'] in detected:
                continue
            with get_db_cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE lifecycle_exit_candidates
                    SET status = 'resolved', resolved_at = %s, updated_at = NOW()
                    WHERE id = %s AND status = 'active'
                    """,
                    (resolved_at, row['id']),
                )
            resolved += 1
        return resolved

    def list_candidates(
        self,
        *,
        lifecycle_id: Optional[int] = None,
        statuses: Optional[Sequence[str]] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        statuses = tuple(statuses or (self.ACTIVE_STATUS, self.RESOLVED_STATUS, self.IGNORED_STATUS))
        where = []
        params: List[Any] = []
        if lifecycle_id is not None:
            where.append('lifecycle_id = %s')
            params.append(lifecycle_id)
        if statuses:
            where.append(f"status IN ({', '.join(['%s'] * len(statuses))})")
            params.extend(list(statuses))
        sql = "SELECT * FROM lifecycle_exit_candidates"
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY status = \"active\" DESC, last_detected_at DESC, id DESC LIMIT %s'
        params.append(limit)
        with get_db_cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall() or []
        return [self._serialize_row(row) for row in rows]

    def find_latest(self, *, lifecycle_id: int, candidate_type: str, statuses: Sequence[str]) -> Optional[Dict[str, Any]]:
        sql = f"""
            SELECT *
            FROM lifecycle_exit_candidates
            WHERE lifecycle_id = %s
              AND candidate_type = %s
              AND status IN ({', '.join(['%s'] * len(statuses))})
            ORDER BY last_detected_at DESC, id DESC
            LIMIT 1
        """
        with get_db_cursor() as cursor:
            cursor.execute(sql, (lifecycle_id, candidate_type, *statuses))
            row = cursor.fetchone()
        return row

    def get_by_id(self, candidate_id: int) -> Dict[str, Any]:
        with get_db_cursor() as cursor:
            cursor.execute('SELECT * FROM lifecycle_exit_candidates WHERE id = %s LIMIT 1', (candidate_id,))
            row = cursor.fetchone()
        return row or {}

    def _refresh_candidate(self, candidate_id: int, candidate: Dict[str, Any], detected_at: datetime) -> Dict[str, Any]:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                UPDATE lifecycle_exit_candidates
                SET status = 'active',
                    last_detected_at = %s,
                    resolved_at = NULL,
                    threshold_value = %s,
                    current_price = %s,
                    threshold_source = %s,
                    reason = %s,
                    detection_count = detection_count + 1,
                    metadata = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    detected_at,
                    candidate.get('threshold_value'),
                    candidate.get('current_price'),
                    candidate.get('threshold_source'),
                    candidate.get('reason'),
                    json.dumps(self._build_metadata(candidate), ensure_ascii=False, default=str),
                    candidate_id,
                ),
            )
        return self.get_by_id(candidate_id)

    @staticmethod
    def _build_metadata(candidate: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(candidate)
        metadata.pop('persisted_candidate', None)
        return metadata

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
        metadata = payload.get('metadata')
        if isinstance(metadata, str):
            try:
                payload['metadata'] = json.loads(metadata)
            except Exception:
                pass
        return payload

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
