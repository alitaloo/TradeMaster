from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class NormalizedSignal:
    strategy_name: str
    symbol: str
    action: str
    entry_price: float
    signal_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: Optional[float] = None
    confidence_tier: Optional[str] = None
    strength: Optional[str] = None
    reason: Optional[str] = None
    reasons: list[str] = field(default_factory=list)
    trend_tf: str = '1h'
    trend_value: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    quantity: float = 1.0
    execution_enabled: bool = True
    warnings: list[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)
    signal_hash: Optional[str] = None


@dataclass
class RouterDecision:
    success: bool
    decision: str
    message: str
    signal_id: Optional[int] = None
    broker: Optional[str] = None
    broker_order_id: Optional[str] = None
    lifecycle_status: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            'success': self.success,
            'decision': self.decision,
            'message': self.message,
        }
        if self.signal_id is not None:
            payload['signal_id'] = self.signal_id
        if self.broker is not None:
            payload['broker'] = self.broker
        if self.broker_order_id is not None:
            payload['broker_order_id'] = self.broker_order_id
        if self.lifecycle_status is not None:
            payload['lifecycle_status'] = self.lifecycle_status
        if self.warnings:
            payload['warnings'] = self.warnings
        if self.details:
            payload['details'] = self.details
        return payload
