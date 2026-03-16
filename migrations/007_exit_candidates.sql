-- Stage 2.5 exit candidate persistence (detect-only, no auto-exit yet)
-- migrations/007_exit_candidates.sql

CREATE TABLE IF NOT EXISTS lifecycle_exit_candidates (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    lifecycle_id BIGINT NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    candidate_type ENUM('holding_timeout','stop_loss','take_profit') NOT NULL,
    status ENUM('active','resolved','ignored') NOT NULL DEFAULT 'active',
    first_detected_at DATETIME NOT NULL,
    last_detected_at DATETIME NOT NULL,
    resolved_at DATETIME NULL,
    threshold_value DECIMAL(18,6) NULL,
    current_price DECIMAL(18,6) NULL,
    threshold_source VARCHAR(32) NULL,
    reason TEXT NULL,
    detection_count INT NOT NULL DEFAULT 1,
    metadata JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_candidate_lifecycle_status (lifecycle_id, status),
    KEY idx_candidate_symbol_status (symbol, status),
    KEY idx_candidate_type_status_time (candidate_type, status, last_detected_at),
    CONSTRAINT fk_exit_candidate_lifecycle FOREIGN KEY (lifecycle_id) REFERENCES trade_lifecycles(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
