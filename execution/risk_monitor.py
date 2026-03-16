from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.database import get_db_cursor  # noqa: E402
from execution.exit_candidate_repository import ExitCandidateRepository  # noqa: E402
from models.system_config import SystemConfig  # noqa: E402

logger = logging.getLogger(__name__)

OPEN_LIFECYCLE_STATUSES = ('signal_created', 'order_submitted', 'partially_filled', 'filled_open', 'exit_pending')
ACTIVE_CANDIDATE_STATUSES = ('active',)


@dataclass
class RiskMonitorSummary:
    scanned: int = 0
    candidate_count: int = 0
    holding_timeout_count: int = 0
    stop_loss_count: int = 0
    take_profit_count: int = 0
    inserted_count: int = 0
    cooldown_refreshed_count: int = 0
    reactivated_count: int = 0
    resolved_count: int = 0
    active_candidate_count: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            'scanned': self.scanned,
            'candidate_count': self.candidate_count,
            'holding_timeout_count': self.holding_timeout_count,
            'stop_loss_count': self.stop_loss_count,
            'take_profit_count': self.take_profit_count,
            'inserted_count': self.inserted_count,
            'cooldown_refreshed_count': self.cooldown_refreshed_count,
            'reactivated_count': self.reactivated_count,
            'resolved_count': self.resolved_count,
            'active_candidate_count': self.active_candidate_count,
        }


class LifecycleRiskMonitor:
    def __init__(self, now: Optional[datetime] = None, repository: Optional[ExitCandidateRepository] = None):
        self.now = now or datetime.now()
        self.repository = repository or ExitCandidateRepository()

    def scan(self, *, account_type: str = 'futu_sim', limit: int = 200, persist: bool = True) -> Dict[str, Any]:
        rows = self.fetch_open_lifecycles(account_type=account_type, limit=limit)
        summary = RiskMonitorSummary(scanned=len(rows))
        monitored: List[Dict[str, Any]] = []
        candidates: List[Dict[str, Any]] = []

        holding_enabled = SystemConfig.get_bool('risk.holding_timeout_enabled', False)
        max_holding_minutes = self._get_max_holding_minutes()
        sltp_enabled = SystemConfig.get_bool('risk.active_sltp_detect_enabled', False)
        default_stop_loss_pct = self._get_optional_float('risk.default_stop_loss_pct')
        default_take_profit_pct = self._get_optional_float('risk.default_take_profit_pct')
        candidate_cooldown_seconds = self._get_candidate_cooldown_seconds()

        config = {
            'account_type': account_type,
            'holding_timeout_enabled': holding_enabled,
            'max_holding_minutes': max_holding_minutes,
            'active_sltp_detect_enabled': sltp_enabled,
            'default_stop_loss_pct': default_stop_loss_pct,
            'default_take_profit_pct': default_take_profit_pct,
            'candidate_cooldown_seconds': candidate_cooldown_seconds,
            'persist_candidates': persist,
            'stage3_action_enabled': False,
            'stage3_action_source': 'future: active lifecycle_exit_candidates -> action layer',
        }

        for row in rows:
            monitor_row = self.evaluate_row(
                row,
                holding_enabled=holding_enabled,
                max_holding_minutes=max_holding_minutes,
                sltp_enabled=sltp_enabled,
                default_stop_loss_pct=default_stop_loss_pct,
                default_take_profit_pct=default_take_profit_pct,
            )
            monitored.append(monitor_row)
            for candidate in monitor_row['candidates']:
                candidates.append(candidate)
                summary.candidate_count += 1
                if candidate['candidate_type'] == 'holding_timeout':
                    summary.holding_timeout_count += 1
                elif candidate['candidate_type'] == 'stop_loss':
                    summary.stop_loss_count += 1
                elif candidate['candidate_type'] == 'take_profit':
                    summary.take_profit_count += 1
                logger.info('risk detect candidate: %s', json.dumps(candidate, ensure_ascii=False, default=str))

        if persist:
            persistence = self.persist_scan_candidates(monitored, cooldown_seconds=candidate_cooldown_seconds)
            summary.inserted_count = persistence['summary']['inserted_count']
            summary.cooldown_refreshed_count = persistence['summary']['cooldown_refreshed_count']
            summary.reactivated_count = persistence['summary']['reactivated_count']
            summary.resolved_count = persistence['summary']['resolved_count']
            candidates = persistence['candidates']
        else:
            persistence = {
                'summary': {
                    'inserted_count': 0,
                    'cooldown_refreshed_count': 0,
                    'reactivated_count': 0,
                    'resolved_count': 0,
                },
                'candidates': candidates,
            }

        active_candidates = self.repository.list_candidates(statuses=ACTIVE_CANDIDATE_STATUSES, limit=max(limit * 3, 200)) if persist else []
        summary.active_candidate_count = len(active_candidates)

        return {
            'monitored_at': self.now.isoformat(sep=' '),
            'config': config,
            'summary': summary.to_dict(),
            'candidates': candidates,
            'active_candidates': active_candidates,
            'monitored': monitored,
            'stage3_handoff': {
                'ready': True,
                'mode': 'detect_only',
                'action_enabled': False,
                'source_table': 'lifecycle_exit_candidates',
                'selection_rule': 'status=active ordered by last_detected_at ASC',
                'safety_boundary': 'Stage 2.5 only persists and resolves candidates; it never submits exit orders.',
            },
            'persistence': persistence['summary'],
        }

    def persist_scan_candidates(self, monitored: List[Dict[str, Any]], *, cooldown_seconds: int) -> Dict[str, Any]:
        persisted: List[Dict[str, Any]] = []
        summary = {
            'inserted_count': 0,
            'cooldown_refreshed_count': 0,
            'reactivated_count': 0,
            'resolved_count': 0,
        }

        for row in monitored:
            detected_types: List[str] = []
            for candidate in row['candidates']:
                persisted_candidate = self.repository.persist_candidate(candidate, detected_at=self.now, cooldown_seconds=cooldown_seconds)
                candidate_payload = dict(candidate)
                candidate_payload['persisted_candidate'] = persisted_candidate
                candidate_payload['candidate_status'] = persisted_candidate.get('status')
                candidate_payload['candidate_record_id'] = persisted_candidate.get('id')
                candidate_payload['persist_action'] = persisted_candidate.get('persist_action')
                candidate_payload['first_detected_at'] = persisted_candidate.get('first_detected_at')
                candidate_payload['last_detected_at'] = persisted_candidate.get('last_detected_at')
                candidate_payload['detection_count'] = persisted_candidate.get('detection_count')
                detected_types.append(candidate['candidate_type'])
                persisted.append(candidate_payload)
                action = persisted_candidate.get('persist_action')
                action_key = f'{action}_count' if action else None
                if action_key in summary:
                    summary[action_key] += 1
            summary['resolved_count'] += self.repository.resolve_absent_candidates(
                lifecycle_id=row['lifecycle_id'],
                detected_types=detected_types,
                resolved_at=self.now,
            )

        return {
            'summary': summary,
            'candidates': persisted,
        }

    def list_candidates(self, *, status: str = 'active', limit: int = 200) -> Dict[str, Any]:
        rows = self.repository.list_candidates(statuses=(status,), limit=limit)
        return {
            'listed_at': self.now.isoformat(sep=' '),
            'status': status,
            'count': len(rows),
            'candidates': rows,
        }

    def fetch_open_lifecycles(self, *, account_type: str, limit: int) -> List[Dict[str, Any]]:
        placeholders = ', '.join(['%s'] * len(OPEN_LIFECYCLE_STATUSES))
        sql = f"""
            SELECT
                tl.*, 
                ss.stop_loss AS signal_stop_loss,
                ss.take_profit AS signal_take_profit,
                ps.snapshot_time,
                ps.qty AS snapshot_qty,
                ps.avg_cost AS snapshot_avg_cost,
                ps.market_price,
                ps.market_value,
                ps.unrealized_pnl
            FROM trade_lifecycles tl
            LEFT JOIN strategy_signals ss ON ss.id = tl.signal_id
            LEFT JOIN broker_positions_snapshot ps
                ON ps.account_type = %s
               AND ps.symbol = tl.symbol
               AND ps.snapshot_time = (
                   SELECT MAX(p2.snapshot_time)
                   FROM broker_positions_snapshot p2
                   WHERE p2.account_type = %s AND p2.symbol = tl.symbol
               )
            WHERE tl.status IN ({placeholders})
            ORDER BY tl.updated_at DESC
            LIMIT %s
        """
        with get_db_cursor() as cursor:
            cursor.execute(sql, (account_type, account_type, *OPEN_LIFECYCLE_STATUSES, limit))
            return cursor.fetchall() or []

    def evaluate_row(
        self,
        row: Dict[str, Any],
        *,
        holding_enabled: bool,
        max_holding_minutes: Optional[int],
        sltp_enabled: bool,
        default_stop_loss_pct: Optional[float],
        default_take_profit_pct: Optional[float],
    ) -> Dict[str, Any]:
        entry_time = self._to_datetime(row.get('entry_time') or row.get('created_at'))
        current_price = self._to_float(row.get('market_price'))
        entry_price = self._to_float(row.get('entry_price') or row.get('snapshot_avg_cost'))
        direction = str(row.get('direction') or 'long').lower()
        snapshot_qty = self._to_float(row.get('snapshot_qty')) or 0.0
        holding_minutes = self._compute_elapsed_minutes(entry_time, self.now)
        stop_loss, stop_loss_source = self._resolve_threshold(
            primary=row.get('stop_loss'),
            secondary=row.get('signal_stop_loss'),
            fallback_pct=default_stop_loss_pct,
            entry_price=entry_price,
            direction=direction,
            threshold_type='stop_loss',
        )
        take_profit, take_profit_source = self._resolve_threshold(
            primary=row.get('take_profit'),
            secondary=row.get('signal_take_profit'),
            fallback_pct=default_take_profit_pct,
            entry_price=entry_price,
            direction=direction,
            threshold_type='take_profit',
        )

        candidates: List[Dict[str, Any]] = []

        if holding_enabled and max_holding_minutes and holding_minutes is not None and holding_minutes >= max_holding_minutes:
            candidates.append({
                'lifecycle_id': row['id'],
                'signal_id': row.get('signal_id'),
                'symbol': row.get('symbol'),
                'strategy_name': row.get('strategy_name'),
                'status': row.get('status'),
                'direction': direction,
                'candidate_type': 'holding_timeout',
                'reason': f'holding_minutes {holding_minutes} >= max_holding_minutes {max_holding_minutes}',
                'entry_time': self._to_str(entry_time),
                'holding_minutes': holding_minutes,
                'threshold_value': max_holding_minutes,
                'current_price': current_price,
                'snapshot_qty': snapshot_qty,
                'threshold_source': 'config',
                'detected_at': self.now.isoformat(sep=' '),
            })

        sl_hit = False
        tp_hit = False
        if sltp_enabled and current_price is not None:
            if stop_loss is not None:
                sl_hit = current_price <= stop_loss if direction == 'long' else current_price >= stop_loss
                if sl_hit:
                    candidates.append({
                        'lifecycle_id': row['id'],
                        'signal_id': row.get('signal_id'),
                        'symbol': row.get('symbol'),
                        'strategy_name': row.get('strategy_name'),
                        'status': row.get('status'),
                        'direction': direction,
                        'candidate_type': 'stop_loss',
                        'reason': f'current_price {current_price} crossed stop_loss {stop_loss}',
                        'entry_price': entry_price,
                        'current_price': current_price,
                        'threshold_value': stop_loss,
                        'threshold_source': stop_loss_source,
                        'snapshot_qty': snapshot_qty,
                        'detected_at': self.now.isoformat(sep=' '),
                    })
            if take_profit is not None:
                tp_hit = current_price >= take_profit if direction == 'long' else current_price <= take_profit
                if tp_hit:
                    candidates.append({
                        'lifecycle_id': row['id'],
                        'signal_id': row.get('signal_id'),
                        'symbol': row.get('symbol'),
                        'strategy_name': row.get('strategy_name'),
                        'status': row.get('status'),
                        'direction': direction,
                        'candidate_type': 'take_profit',
                        'reason': f'current_price {current_price} crossed take_profit {take_profit}',
                        'entry_price': entry_price,
                        'current_price': current_price,
                        'threshold_value': take_profit,
                        'threshold_source': take_profit_source,
                        'snapshot_qty': snapshot_qty,
                        'detected_at': self.now.isoformat(sep=' '),
                    })

        return {
            'lifecycle_id': row['id'],
            'signal_id': row.get('signal_id'),
            'symbol': row.get('symbol'),
            'strategy_name': row.get('strategy_name'),
            'direction': direction,
            'status': row.get('status'),
            'entry_time': self._to_str(entry_time),
            'entry_price': entry_price,
            'current_price': current_price,
            'snapshot_time': self._to_str(row.get('snapshot_time')),
            'snapshot_qty': snapshot_qty,
            'holding_minutes': holding_minutes,
            'holding_timeout_hit': bool(holding_enabled and max_holding_minutes and holding_minutes is not None and holding_minutes >= max_holding_minutes),
            'max_holding_minutes': max_holding_minutes,
            'resolved_stop_loss': stop_loss,
            'resolved_stop_loss_source': stop_loss_source,
            'stop_loss_hit': sl_hit,
            'resolved_take_profit': take_profit,
            'resolved_take_profit_source': take_profit_source,
            'take_profit_hit': tp_hit,
            'candidates': candidates,
        }

    def _get_max_holding_minutes(self) -> Optional[int]:
        minutes = self._get_optional_int('risk.max_holding_minutes')
        if minutes is not None:
            return minutes
        hours = self._get_optional_float('risk.max_holding_hours')
        if hours is None:
            return None
        return int(hours * 60)

    @staticmethod
    def _get_optional_int(key: str) -> Optional[int]:
        value = SystemConfig.get(key)
        if value in (None, ''):
            return None
        return int(value)

    @staticmethod
    def _get_optional_float(key: str) -> Optional[float]:
        value = SystemConfig.get(key)
        if value in (None, ''):
            return None
        return float(value)

    def _get_candidate_cooldown_seconds(self) -> int:
        value = SystemConfig.get('risk.exit_candidate_cooldown_seconds')
        if value in (None, ''):
            return 300
        return max(0, int(value))

    @staticmethod
    def _resolve_threshold(
        *,
        primary: Any,
        secondary: Any,
        fallback_pct: Optional[float],
        entry_price: Optional[float],
        direction: str,
        threshold_type: str,
    ) -> tuple[Optional[float], Optional[str]]:
        primary_value = LifecycleRiskMonitor._to_float(primary)
        if primary_value is not None and primary_value > 0:
            return primary_value, 'lifecycle'
        secondary_value = LifecycleRiskMonitor._to_float(secondary)
        if secondary_value is not None and secondary_value > 0:
            return secondary_value, 'signal'
        if fallback_pct is None or fallback_pct <= 0 or entry_price is None or entry_price <= 0:
            return None, None
        if threshold_type == 'stop_loss':
            value = entry_price * (1 - fallback_pct) if direction == 'long' else entry_price * (1 + fallback_pct)
        else:
            value = entry_price * (1 + fallback_pct) if direction == 'long' else entry_price * (1 - fallback_pct)
        return value, 'config_pct'

    @staticmethod
    def _compute_elapsed_minutes(start: Optional[datetime], end: Optional[datetime]) -> Optional[int]:
        if not start or not end:
            return None
        return max(0, int((end - start).total_seconds() // 60))

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

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None or value == '':
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _to_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat(sep=' ')
        return str(value)
