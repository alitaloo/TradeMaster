-- Stage 3 dry-run exit action proposals (no live broker orders yet)
-- migrations/008_exit_action_proposals.sql

CREATE TABLE IF NOT EXISTS lifecycle_exit_action_proposals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    candidate_id BIGINT NOT NULL,
    lifecycle_id BIGINT NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    action_type ENUM('exit_market') NOT NULL DEFAULT 'exit_market',
    action_side ENUM('buy','sell') NOT NULL,
    proposal_mode ENUM('dry_run','live') NOT NULL DEFAULT 'dry_run',
    status ENUM('proposed','blocked','stale','cancelled','executed') NOT NULL,
    gate_enabled TINYINT(1) NOT NULL DEFAULT 0,
    gate_mode VARCHAR(16) NOT NULL DEFAULT 'off',
    freshness_window_seconds INT NOT NULL DEFAULT 120,
    freshness_checked_at DATETIME NOT NULL,
    candidate_last_detected_at DATETIME NULL,
    lifecycle_status VARCHAR(32) NULL,
    snapshot_time DATETIME NULL,
    snapshot_age_seconds INT NULL,
    action_reason TEXT NULL,
    block_reason TEXT NULL,
    audit_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_candidate_mode (candidate_id, proposal_mode),
    KEY idx_proposal_status_time (status, updated_at),
    KEY idx_proposal_lifecycle (lifecycle_id, updated_at),
    CONSTRAINT fk_action_proposal_candidate FOREIGN KEY (candidate_id) REFERENCES lifecycle_exit_candidates(id),
    CONSTRAINT fk_action_proposal_lifecycle FOREIGN KEY (lifecycle_id) REFERENCES trade_lifecycles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;