-- Stage 3.5 pre-live safety pack follow-up for environments where 009 already exists
-- migrations/010_exit_submit_safety_pack_v2.sql

ALTER TABLE lifecycle_exit_action_proposals
    ADD COLUMN lease_owner VARCHAR(128) NULL AFTER block_reason,
    ADD COLUMN lease_token VARCHAR(128) NULL AFTER lease_owner,
    ADD COLUMN leased_at DATETIME NULL AFTER lease_token,
    ADD COLUMN lease_expires_at DATETIME NULL AFTER leased_at,
    ADD COLUMN submit_state ENUM('proposed','leased','ready_to_submit','submit_blocked','submit_simulated','submit_failed') NOT NULL DEFAULT 'proposed' AFTER lease_expires_at,
    ADD COLUMN submit_state_reason TEXT NULL AFTER submit_state,
    ADD COLUMN submit_ready_at DATETIME NULL AFTER submit_state_reason,
    ADD COLUMN submit_last_attempt_id BIGINT NULL AFTER submit_ready_at,
    ADD COLUMN broker_request_key VARCHAR(128) NULL AFTER submit_last_attempt_id,
    ADD COLUMN external_order_ref VARCHAR(128) NULL AFTER broker_request_key,
    ADD COLUMN reconciliation_status ENUM('pending_submit','awaiting_reconciliation','reconciled','reconciliation_blocked') NOT NULL DEFAULT 'pending_submit' AFTER external_order_ref,
    ADD COLUMN reconciliation_hook VARCHAR(128) NULL AFTER reconciliation_status,
    ADD COLUMN reconciliation_payload JSON NULL AFTER reconciliation_hook,
    ADD KEY idx_proposal_lease (submit_state, lease_expires_at, updated_at),
    ADD KEY idx_proposal_broker_request_key (broker_request_key),
    ADD KEY idx_proposal_external_order_ref (external_order_ref);

ALTER TABLE lifecycle_exit_submit_attempts
    ADD COLUMN attempt_no INT NOT NULL DEFAULT 1 AFTER symbol,
    ADD COLUMN lease_token VARCHAR(128) NULL AFTER lease_owner,
    ADD COLUMN broker VARCHAR(32) NOT NULL DEFAULT 'futu' AFTER lease_token,
    ADD COLUMN broker_request_key VARCHAR(128) NULL AFTER broker,
    ADD COLUMN external_order_ref VARCHAR(128) NULL AFTER broker_request_key,
    ADD COLUMN submission_mode ENUM('dry_run','live') NOT NULL DEFAULT 'dry_run' AFTER external_order_ref,
    ADD COLUMN attempt_status ENUM('leased','ready_to_submit','submit_blocked','submit_simulated','submit_failed') NOT NULL DEFAULT 'leased' AFTER submission_mode,
    ADD COLUMN failure_reason TEXT NULL AFTER attempt_status,
    ADD COLUMN reconciliation_status ENUM('pending_submit','awaiting_reconciliation','reconciled','reconciliation_blocked') NOT NULL DEFAULT 'pending_submit' AFTER failure_reason,
    ADD COLUMN reconciliation_hook VARCHAR(128) NULL AFTER reconciliation_status,
    ADD COLUMN reconciliation_payload JSON NULL AFTER reconciliation_hook,
    ADD COLUMN request_payload JSON NULL AFTER reconciliation_payload,
    ADD COLUMN response_payload JSON NULL AFTER request_payload,
    ADD COLUMN simulated_at DATETIME NULL AFTER response_payload,
    ADD UNIQUE KEY uq_submit_attempt_request_key (broker, broker_request_key),
    ADD UNIQUE KEY uq_submit_attempt_proposal_no (proposal_id, attempt_no),
    ADD KEY idx_submit_attempt_status (attempt_status, updated_at),
    ADD KEY idx_submit_attempt_external_ref (external_order_ref);

ALTER TABLE lifecycle_exit_action_proposals
    ADD CONSTRAINT fk_proposal_last_attempt FOREIGN KEY (submit_last_attempt_id) REFERENCES lifecycle_exit_submit_attempts(id);

UPDATE lifecycle_exit_submit_attempts
SET lease_token = COALESCE(lease_token, reservation_key),
    broker_request_key = COALESCE(broker_request_key, idempotency_key),
    external_order_ref = COALESCE(external_order_ref, external_correlation_id),
    submission_mode = COALESCE(submission_mode, proposal_mode),
    attempt_status = CASE
        WHEN submit_state IN ('reconciled') THEN 'submit_simulated'
        WHEN submit_state IN ('failed') THEN 'submit_failed'
        ELSE COALESCE(attempt_status, 'leased')
    END,
    failure_reason = COALESCE(failure_reason, last_error),
    simulated_at = COALESCE(simulated_at, submit_finished_at),
    reconciliation_status = CASE
        WHEN reconciled_at IS NOT NULL THEN 'reconciled'
        WHEN submit_state IN ('reconcile_pending','ack_pending','submitted','submitting') THEN 'awaiting_reconciliation'
        WHEN submit_state IN ('failed','cancelled','expired') THEN 'reconciliation_blocked'
        ELSE COALESCE(reconciliation_status, 'pending_submit')
    END;
