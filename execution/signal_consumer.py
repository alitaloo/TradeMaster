from __future__ import annotations

"""Stage 1.5 signal ingestion for Fox -> execution.

Canonical contract accepted by SignalConsumer.normalize_signal/process_signal:
- action: buy|sell (or legacy signal_type: BUY|SELL|LONG|SHORT)
- symbol: broker symbol or raw ticker (normalized to US.*)
- confidence: numeric 0..1
- confidence_tier: low|medium|high|very_high
- strength: weak|moderate|strong|very_strong
- stop_loss / take_profit: numeric price levels
- reason or reasons: human-readable rationale
- trend fields: trend_tf + matching `<tf>_trend`, or 1h_trend / trend_alignment

To avoid Fox metadata drift, the same fields may also arrive under `metadata`.
normalize_signal() flattens both shapes into one execution-side contract.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from execution.futu_execution_adapter import FutuExecutionAdapter
from execution.repositories import ExecutionRepository
from execution.router_models import RouterDecision
from models.system_config import SystemConfig


class SignalConsumer:
    CONTRACT_VERSION = 'stage1.5'
    SIGNAL_CONTRACT_FIELDS = (
        'strategy_name', 'symbol', 'action', 'entry_price', 'signal_time',
        'confidence', 'confidence_tier', 'strength',
        'stop_loss', 'take_profit', 'reason', 'reasons',
        'trend_tf', 'trend_value', 'metadata',
    )
    ALLOWED_ACTIONS = {'buy', 'sell'}
    ALLOWED_STRENGTH = {'weak', 'moderate', 'strong', 'very_strong'}
    CONFIDENCE_TIER_MINIMUMS = {
        'low': 0.45,
        'medium': 0.60,
        'high': 0.75,
        'very_high': 0.85,
    }
    CONFIDENCE_TIER_ORDER = {
        'low': 0,
        'medium': 1,
        'high': 2,
        'very_high': 3,
    }
    ACTION_ALIASES = {
        'buy': 'buy',
        'long': 'buy',
        'bullish': 'buy',
        'sell': 'sell',
        'short': 'sell',
        'bearish': 'sell',
    }

    def __init__(self, repository: Optional[ExecutionRepository] = None,
                 adapter: Optional[FutuExecutionAdapter] = None,
                 *, signal_ttl_minutes: int = 30,
                 min_confidence: float = 0.6,
                 require_stop_loss: bool = False,
                 default_quantity: float = 1.0,
                 trend_veto_enabled: bool = False,
                 trend_veto_required_tf: str = '1h',
                 per_day_trade_cap: int = 0,
                 min_confidence_tier: Optional[str] = None):
        self.repository = repository or ExecutionRepository()
        self.adapter = adapter or FutuExecutionAdapter()

        self.signal_ttl_minutes = self._get_int_config('execution.signal_ttl_minutes', signal_ttl_minutes)
        self.min_confidence = self._get_float_config('execution.min_confidence', min_confidence)
        self.require_stop_loss = self._get_bool_config('execution.require_stop_loss', require_stop_loss)
        self.default_quantity = self._get_float_config('execution.default_quantity', default_quantity)
        self.trend_veto_enabled = self._get_bool_config('trend_veto.enabled', trend_veto_enabled)
        self.trend_veto_required_tf = str(SystemConfig.get('trend_veto.required_tf', trend_veto_required_tf)).strip() or '1h'
        self.per_day_trade_cap = self._get_int_config('risk.per_day_trade_cap', per_day_trade_cap)
        self.min_confidence_tier = self._normalize_confidence_tier(SystemConfig.get('execution.min_confidence_tier', min_confidence_tier))

    def normalize_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(signal)
        metadata = dict(signal.get('metadata') or {})

        action = self._normalize_action(signal.get('action') or signal.get('signal_type') or metadata.get('action') or metadata.get('signal_type'))
        strategy_name = self._first_present(signal, metadata, 'strategy_name', 'strategy_type') or 'fox_analysis_v2'
        symbol = self._first_present(signal, metadata, 'symbol') or ''
        trend_tf = str(self._first_present(signal, metadata, 'trend_tf', 'trend_timeframe') or self.trend_veto_required_tf).strip() or self.trend_veto_required_tf
        trend_value = self._resolve_trend_value(signal, metadata, trend_tf)
        confidence_tier = self._normalize_confidence_tier(self._first_present(signal, metadata, 'confidence_tier'))
        strength = self._normalize_strength(self._first_present(signal, metadata, 'strength'))
        reason = self._first_present(signal, metadata, 'reason')
        reasons = self._normalize_reasons(signal.get('reasons', metadata.get('reasons')))
        if not reason and reasons:
            reason = '; '.join(reasons)

        raw_symbol = str(symbol).strip().upper()
        normalized['strategy_name'] = str(strategy_name).strip()
        normalized['symbol'] = raw_symbol if '.' in raw_symbol else (f'US.{raw_symbol}' if raw_symbol else '')
        normalized['action'] = action or ''
        normalized['entry_price'] = self._to_float(self._first_present(signal, metadata, 'entry_price', 'price'), default=0)
        normalized['stop_loss'] = self._to_float(self._first_present(signal, metadata, 'stop_loss'))
        normalized['take_profit'] = self._to_float(self._first_present(signal, metadata, 'take_profit'))
        normalized['confidence'] = self._to_float(self._first_present(signal, metadata, 'confidence'))
        normalized['confidence_tier'] = confidence_tier
        normalized['strength'] = strength
        normalized['reason'] = reason
        normalized['reasons'] = reasons
        normalized['quantity'] = self._to_float(self._first_present(signal, metadata, 'quantity'), default=self.default_quantity)
        normalized['execution_enabled'] = bool(signal.get('execution_enabled', True))
        normalized['signal_time'] = self._parse_signal_time(self._first_present(signal, metadata, 'signal_time', 'created_at'))
        normalized['direction'] = 'long' if normalized['action'] == 'buy' else 'short'
        normalized['trend_tf'] = trend_tf
        normalized['trend_value'] = trend_value
        normalized['metadata'] = {
            **metadata,
            'contract_version': self.CONTRACT_VERSION,
            'action': normalized['action'] or metadata.get('action'),
            'confidence_tier': confidence_tier,
            'strength': strength,
            'trend_tf': trend_tf,
            f'{trend_tf}_trend': trend_value,
            'reasons': reasons,
        }
        normalized['warnings'] = []
        return normalized

    def validate_signal(self, signal: Dict[str, Any]) -> Tuple[bool, str]:
        required_fields = ['strategy_name', 'symbol', 'action', 'entry_price', 'signal_time']
        missing = [field for field in required_fields if not signal.get(field)]
        if missing:
            return False, f"missing required fields: {', '.join(missing)}"
        if signal['action'] not in self.ALLOWED_ACTIONS:
            return False, 'action must be buy or sell'
        if signal['entry_price'] <= 0:
            return False, 'entry_price must be > 0'
        if not signal['symbol'] or '.' not in signal['symbol']:
            return False, 'symbol must be normalized broker format'
        if signal['quantity'] <= 0:
            return False, 'quantity must be > 0'
        if signal.get('strength') and signal['strength'] not in self.ALLOWED_STRENGTH:
            return False, 'strength not in allowed set'
        if signal.get('confidence_tier') and signal['confidence_tier'] not in self.CONFIDENCE_TIER_ORDER:
            return False, 'confidence_tier not in allowed set'
        return True, 'ok'

    def generate_signal_hash(self, signal: Dict[str, Any]) -> str:
        bucket_dt = self._bucket_time(signal['signal_time'])
        payload = f"{signal['strategy_name']}|{signal['symbol']}|{signal['action']}|{bucket_dt.isoformat()}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def persist_signal(self, signal: Dict[str, Any]) -> int:
        return self.repository.insert_signal(signal)

    def dedupe_check(self, signal: Dict[str, Any]) -> Tuple[bool, str]:
        if self.repository.get_signal_by_hash(signal['signal_hash']):
            return False, 'duplicate signal hash'
        return True, 'ok'

    def eligibility_check(self, signal: Dict[str, Any]) -> Tuple[bool, str, list[str]]:
        warnings = []
        if datetime.now(signal['signal_time'].tzinfo) - signal['signal_time'] > timedelta(minutes=self.signal_ttl_minutes):
            return False, 'signal expired', warnings
        if signal.get('confidence') is None or signal['confidence'] < self.min_confidence:
            return False, f'confidence below threshold {self.min_confidence}', warnings
        if self.min_confidence_tier:
            signal_tier = signal.get('confidence_tier')
            if signal_tier:
                if self.CONFIDENCE_TIER_ORDER[signal_tier] < self.CONFIDENCE_TIER_ORDER[self.min_confidence_tier]:
                    return False, f'confidence tier below required {self.min_confidence_tier}', warnings
            else:
                required = self.CONFIDENCE_TIER_MINIMUMS[self.min_confidence_tier]
                if signal['confidence'] < required:
                    return False, f'confidence tier below required {self.min_confidence_tier}', warnings
        if signal.get('stop_loss') is None:
            warnings.append('stop_loss missing')
            if self.require_stop_loss:
                return False, 'stop_loss required', warnings
        return True, 'ok', warnings

    def risk_check(self, signal: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        details: Dict[str, Any] = {}
        if self.trend_veto_enabled and signal.get('trend_tf') == self.trend_veto_required_tf:
            trend_value = signal.get('trend_value')
            if trend_value and not self._trend_allows_action(trend_value, signal['action']):
                reason = f"trend veto: {signal['trend_tf']} trend={trend_value} blocks {signal['action']}"
                details['trend_veto'] = {
                    'enabled': True,
                    'required_tf': self.trend_veto_required_tf,
                    'trend': trend_value,
                    'action': signal['action'],
                }
                return False, reason, details
        if self.per_day_trade_cap > 0:
            submitted_today = self.repository.count_submitted_signals_for_day(signal['strategy_name'], signal['signal_time'])
            details['per_day_trade_cap'] = {
                'limit': self.per_day_trade_cap,
                'submitted_today': submitted_today,
            }
            if submitted_today >= self.per_day_trade_cap:
                return False, f'daily trade cap reached ({submitted_today}/{self.per_day_trade_cap})', details
        if self.repository.find_open_lifecycle(signal['symbol'], signal['direction']):
            return False, 'open lifecycle exists for same symbol and direction', details
        if self.repository.find_pending_order(signal['symbol'], signal['action']):
            return False, 'pending order exists for same symbol and side', details
        return True, 'ok', details

    def submit_signal(self, signal: Dict[str, Any], signal_id: int) -> Dict[str, Any]:
        try:
            return self.adapter.submit_order(
                symbol=signal['symbol'],
                action=signal['action'],
                quantity=signal['quantity'],
                price=signal['entry_price'],
                source_signal_id=signal_id,
                stop_loss=signal.get('stop_loss'),
                take_profit=signal.get('take_profit'),
            )
        except Exception as exc:
            return {
                'success': False,
                'broker': 'futu',
                'broker_order_id': None,
                'status': 'error',
                'raw': {},
                'error_message': str(exc),
            }

    def process_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        try:
            normalized = self.normalize_signal(signal)
        except Exception as exc:
            return RouterDecision(False, 'error', str(exc)).to_dict()

        is_valid, message = self.validate_signal(normalized)
        if not is_valid:
            return RouterDecision(False, 'error', message).to_dict()

        normalized['signal_hash'] = self.generate_signal_hash(normalized)

        is_unique, dedupe_message = self.dedupe_check(normalized)
        if not is_unique:
            existing = self.repository.get_signal_by_hash(normalized['signal_hash'])
            return RouterDecision(True, 'ignored', dedupe_message, signal_id=existing['id'] if existing else None).to_dict()

        signal_id = self.persist_signal({**normalized, 'status': 'new'})

        if not normalized.get('execution_enabled', True):
            self.repository.upsert_lifecycle(signal_id=signal_id, signal=normalized, status='signal_created')
            self.repository.update_signal_status(signal_id, 'ignored', 'execution disabled')
            return RouterDecision(True, 'ignored', 'execution disabled', signal_id=signal_id, lifecycle_status='signal_created').to_dict()

        eligible, eligibility_message, warnings = self.eligibility_check(normalized)
        if not eligible:
            self.repository.update_signal_status(signal_id, 'error', eligibility_message)
            self.repository.upsert_lifecycle(signal_id=signal_id, signal=normalized, status='rejected', rejection_reason=eligibility_message)
            return RouterDecision(False, 'error', eligibility_message, signal_id=signal_id, lifecycle_status='rejected', warnings=warnings).to_dict()

        risk_ok, risk_message, risk_details = self.risk_check(normalized)
        if not risk_ok:
            self.repository.upsert_lifecycle(signal_id=signal_id, signal=normalized, status='signal_created', rejection_reason=risk_message)
            self.repository.update_signal_status(signal_id, 'ignored', risk_message)
            return RouterDecision(True, 'ignored', risk_message, signal_id=signal_id, lifecycle_status='signal_created', warnings=warnings, details=risk_details).to_dict()

        adapter_result = self.submit_signal(normalized, signal_id)
        if not adapter_result.get('success') or not adapter_result.get('broker_order_id'):
            error_message = adapter_result.get('error_message') or 'adapter submit failed'
            self.repository.update_signal_status(signal_id, 'error', error_message)
            self.repository.upsert_lifecycle(signal_id=signal_id, signal=normalized, status='rejected', rejection_reason=error_message)
            return RouterDecision(False, 'error', error_message, signal_id=signal_id, broker='futu', lifecycle_status='rejected', warnings=warnings).to_dict()

        broker_order_pk = self.repository.insert_broker_order(signal_id=signal_id, signal=normalized, adapter_result=adapter_result)
        self.repository.update_signal_status(signal_id, 'submitted', None)
        self.repository.upsert_lifecycle(signal_id=signal_id, signal=normalized, status='order_submitted', entry_order_id=broker_order_pk)

        return RouterDecision(
            True,
            'submitted',
            'signal submitted to futu sim',
            signal_id=signal_id,
            broker='futu',
            broker_order_id=adapter_result['broker_order_id'],
            lifecycle_status='order_submitted',
            warnings=warnings,
            details=risk_details,
        ).to_dict()

    @staticmethod
    def _parse_signal_time(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            candidate = value.replace('Z', '+00:00')
            return datetime.fromisoformat(candidate)
        raise ValueError('signal_time must be datetime or ISO string')

    @staticmethod
    def _bucket_time(value: datetime) -> datetime:
        minute_bucket = (value.minute // 5) * 5
        return value.replace(minute=minute_bucket, second=0, microsecond=0)

    @staticmethod
    def _normalize_trend_value(value: Any) -> Optional[str]:
        if value in (None, ''):
            return None
        trend = str(value).strip().lower().replace(' ', '_')
        mapping = {
            'buy': 'bullish',
            'up': 'bullish',
            'long': 'bullish',
            'sell': 'bearish',
            'down': 'bearish',
            'short': 'bearish',
            'flat': 'neutral',
            'sideways': 'neutral',
        }
        return mapping.get(trend, trend)

    @staticmethod
    def _normalize_confidence_tier(value: Any) -> Optional[str]:
        if value in (None, ''):
            return None
        tier = str(value).strip().lower()
        if tier in SignalConsumer.CONFIDENCE_TIER_MINIMUMS:
            return tier
        return None

    @staticmethod
    def _normalize_strength(value: Any) -> Optional[str]:
        if value in (None, ''):
            return None
        return str(value).strip().lower()

    @staticmethod
    def _normalize_action(value: Any) -> Optional[str]:
        if value in (None, ''):
            return None
        return SignalConsumer.ACTION_ALIASES.get(str(value).strip().lower())

    @staticmethod
    def _normalize_reasons(value: Any) -> list[str]:
        if value in (None, ''):
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]

    @staticmethod
    def _first_present(primary: Dict[str, Any], secondary: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if primary.get(key) not in (None, ''):
                return primary.get(key)
            if secondary.get(key) not in (None, ''):
                return secondary.get(key)
        return None

    def _resolve_trend_value(self, signal: Dict[str, Any], metadata: Dict[str, Any], trend_tf: str) -> Optional[str]:
        trend_key = f'{trend_tf}_trend'
        raw = self._first_present(signal, metadata, trend_key, '1h_trend', 'trend_alignment')
        return self._normalize_trend_value(raw)

    @staticmethod
    def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        if value in (None, ''):
            return default
        return float(value)

    @staticmethod
    def _trend_allows_action(trend_value: str, action: str) -> bool:
        if trend_value == 'neutral':
            return True
        return (action == 'buy' and trend_value == 'bullish') or (action == 'sell' and trend_value == 'bearish')

    @staticmethod
    def _get_bool_config(key: str, default: bool) -> bool:
        try:
            return SystemConfig.get_bool(key, default)
        except Exception:
            return default

    @staticmethod
    def _get_int_config(key: str, default: int) -> int:
        try:
            return SystemConfig.get_int(key, default)
        except Exception:
            return default

    @staticmethod
    def _get_float_config(key: str, default: float) -> float:
        try:
            return SystemConfig.get_float(key, default)
        except Exception:
            return default


_default_consumer = SignalConsumer()


def normalize_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    return _default_consumer.normalize_signal(signal)


def validate_signal(signal: Dict[str, Any]):
    return _default_consumer.validate_signal(signal)


def generate_signal_hash(signal: Dict[str, Any]) -> str:
    return _default_consumer.generate_signal_hash(signal)


def persist_signal(signal: Dict[str, Any]) -> int:
    return _default_consumer.persist_signal(signal)


def dedupe_check(signal: Dict[str, Any]):
    return _default_consumer.dedupe_check(signal)


def eligibility_check(signal: Dict[str, Any]):
    return _default_consumer.eligibility_check(signal)


def risk_check(signal: Dict[str, Any]):
    return _default_consumer.risk_check(signal)


def submit_signal(signal: Dict[str, Any], signal_id: int):
    return _default_consumer.submit_signal(signal, signal_id)


def process_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    return _default_consumer.process_signal(signal)
