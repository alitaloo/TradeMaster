-- Stage 3.5 pre-live safety pack (reservation/lease + submit attempts + external correlation hooks)
-- migrations/009_exit_submit_safety_pack.sql

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
    ADD COLUMN reconciliation_payload JSON NULL AFTER reconciliation_hook;

ALTER TABLE lifecycle_exit_action_proposals
    ADD KEY idx_proposal_lease (submit_state, lease_expires_at, updated_at),
    ADD KEY idx_proposal_broker_request_key (broker_request_key),
    ADD KEY idx_proposal_external_order_ref (external_order_ref);

CREATE TABLE IF NOT EXISTS lifecycle_exit_submit_attempts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    proposal_id BIGINT NOT NULL,
    candidate_id BIGINT NOT NULL,
    lifecycle_id BIGINT NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    attempt_no INT NOT NULL,
    lease_owner VARCHAR(128) NOT NULL,
    lease_token VARCHAR(128) NOT NULL,
    broker VARCHAR(32) NOT NULL DEFAULT 'futu',
    broker_request_key VARCHAR(128) NOT NULL,
    external_order_ref VARCHAR(128) NULL,
    submission_mode ENUM('dry_run','live') NOT NULL DEFAULT 'dry_run',
    attempt_status ENUM('leased','ready_to_submit','submit_blocked','submit_simulated','submit_failed') NOT NULL,
    failure_reason TEXT NULL,
    reconciliation_status ENUM('pending_submit','awaiting_reconciliation','reconciled','reconciliation_blocked') NOT NULL DEFAULT 'pending_submit',
    reconciliation_hook VARCHAR(128) NULL,
    reconciliation_payload JSON NULL,
    request_payload JSON NULL,
    response_payload JSON NULL,
    simulated_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_submit_attempt_request_key (broker, broker_request_key),
    UNIQUE KEY uq_submit_attempt_proposal_no (proposal_id, attempt_no),
    KEY idx_submit_attempt_proposal (proposal_id, created_at),
    KEY idx_submit_attempt_status (attempt_status, updated_at),
    KEY idx_submit_attempt_external_ref (external_order_ref),
    CONSTRAINT fk_submit_attempt_proposal FOREIGN KEY (proposal_id) REFERENCES lifecycle_exit_action_proposals(id),
    CONSTRAINT fk_submit_attempt_candidate FOREIGN KEY (candidate_id) REFERENCES lifecycle_exit_candidates(id),
    CONSTRAINT fk_submit_attempt_lifecycle FOREIGN KEY (lifecycle_id) REFERENCES trade_lifecycles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE lifecycle_exit_action_proposals
    ADD CONSTRAINT fk_proposal_last_attempt FOREIGN KEY (submit_last_attempt_id) REFERENCES lifecycle_exit_submit_attempts(id);
