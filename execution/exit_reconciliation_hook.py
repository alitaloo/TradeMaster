from __future__ import annotations

from typing import Any, Dict


class ExitReconciliationHook:
    """Pre-live adapter boundary for wiring submit attempts into reconciliation later."""

    def build_pending_payload(self, proposal: Dict[str, Any], attempt: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'hook': 'paper_position_reconciliation',
            'proposal_id': proposal.get('id'),
            'lifecycle_id': proposal.get('lifecycle_id'),
            'candidate_id': proposal.get('candidate_id'),
            'submit_attempt_id': attempt.get('id'),
            'broker': attempt.get('broker', 'futu'),
            'broker_request_key': attempt.get('broker_request_key'),
            'external_order_ref': attempt.get('external_order_ref'),
            'expected_transition': 'exit_pending -> closed',
            'mode': attempt.get('submission_mode'),
            'armed': False,
            'note': 'Stage 3.5 safety hook only; real broker/order reconciliation remains disabled.',
        }
