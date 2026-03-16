-- Futu SIM lifecycle tracking schema
-- migrations/006_futu_sim_lifecycle.sql

CREATE TABLE IF NOT EXISTS strategy_signals (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    strategy_name VARCHAR(64) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    action ENUM('buy','sell') NOT NULL,
    entry_price DECIMAL(18,6) NOT NULL,
    stop_loss DECIMAL(18,6) NULL,
    take_profit DECIMAL(18,6) NULL,
    confidence DECIMAL(6,4) NULL,
    strength VARCHAR(16) NULL,
    reason TEXT NULL,
    signal_time DATETIME NOT NULL,
    signal_hash VARCHAR(128) NOT NULL,
    execution_enabled TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM('new','submitted','ignored','expired','error') NOT NULL DEFAULT 'new',
    status_reason TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_signal_hash (signal_hash),
    KEY idx_strategy_symbol_time (strategy_name, symbol, signal_time),
    KEY idx_signal_status_time (status, signal_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS broker_orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    signal_id BIGINT NULL,
    broker VARCHAR(32) NOT NULL DEFAULT 'futu',
    account_type VARCHAR(32) NOT NULL DEFAULT 'futu_sim',
    broker_order_id VARCHAR(128) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    side ENUM('buy','sell') NOT NULL,
    order_type VARCHAR(32) NOT NULL,
    qty DECIMAL(18,6) NOT NULL,
    price DECIMAL(18,6) NULL,
    status VARCHAR(32) NOT NULL,
    submitted_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    reject_reason TEXT NULL,
    raw_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_broker_order (broker, broker_order_id),
    KEY idx_signal_id (signal_id),
    KEY idx_symbol_status (symbol, status),
    KEY idx_submitted_at (submitted_at),
    CONSTRAINT fk_broker_orders_signal FOREIGN KEY (signal_id) REFERENCES strategy_signals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS broker_fills (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    broker VARCHAR(32) NOT NULL DEFAULT 'futu',
    broker_order_id VARCHAR(128) NOT NULL,
    broker_fill_id VARCHAR(128) NULL,
    symbol VARCHAR(32) NOT NULL,
    side ENUM('buy','sell') NOT NULL,
    fill_price DECIMAL(18,6) NOT NULL,
    fill_qty DECIMAL(18,6) NOT NULL,
    fill_time DATETIME NOT NULL,
    raw_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_fill (broker, broker_order_id, broker_fill_id),
    KEY idx_fill_symbol_time (symbol, fill_time),
    KEY idx_fill_order (broker, broker_order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS trade_lifecycles (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    signal_id BIGINT NULL,
    strategy_name VARCHAR(64) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    direction ENUM('long','short') NOT NULL,
    entry_order_id BIGINT NULL,
    exit_order_id BIGINT NULL,
    entry_price DECIMAL(18,6) NULL,
    exit_price DECIMAL(18,6) NULL,
    entry_time DATETIME NULL,
    exit_time DATETIME NULL,
    position_qty DECIMAL(18,6) NULL,
    status ENUM('signal_created','order_submitted','partially_filled','filled_open','exit_pending','closed','cancelled','rejected') NOT NULL,
    exit_reason ENUM('stop_loss','take_profit','manual','reverse_signal','timeout','cancelled','rejected') NULL,
    stop_loss DECIMAL(18,6) NULL,
    take_profit DECIMAL(18,6) NULL,
    pnl DECIMAL(18,6) NULL,
    pnl_pct DECIMAL(10,6) NULL,
    rr DECIMAL(10,6) NULL,
    holding_minutes INT NULL,
    rejection_reason TEXT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_lifecycle_status (status),
    KEY idx_lifecycle_symbol_status (symbol, status),
    KEY idx_lifecycle_strategy_time (strategy_name, created_at),
    CONSTRAINT fk_lifecycle_signal FOREIGN KEY (signal_id) REFERENCES strategy_signals(id),
    CONSTRAINT fk_lifecycle_entry_order FOREIGN KEY (entry_order_id) REFERENCES broker_orders(id),
    CONSTRAINT fk_lifecycle_exit_order FOREIGN KEY (exit_order_id) REFERENCES broker_orders(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS broker_positions_snapshot (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    snapshot_time DATETIME NOT NULL,
    broker VARCHAR(32) NOT NULL DEFAULT 'futu',
    account_type VARCHAR(32) NOT NULL DEFAULT 'futu_sim',
    symbol VARCHAR(32) NOT NULL,
    qty DECIMAL(18,6) NOT NULL,
    avg_cost DECIMAL(18,6) NULL,
    market_price DECIMAL(18,6) NULL,
    market_value DECIMAL(18,6) NULL,
    unrealized_pnl DECIMAL(18,6) NULL,
    realized_pnl DECIMAL(18,6) NULL,
    raw_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_position_snapshot_time (snapshot_time),
    KEY idx_position_symbol_time (symbol, snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS account_equity_snapshots (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    snapshot_time DATETIME NOT NULL,
    broker VARCHAR(32) NOT NULL DEFAULT 'futu',
    account_type VARCHAR(32) NOT NULL DEFAULT 'futu_sim',
    cash DECIMAL(18,6) NULL,
    equity DECIMAL(18,6) NOT NULL,
    market_value DECIMAL(18,6) NULL,
    realized_pnl DECIMAL(18,6) NULL,
    unrealized_pnl DECIMAL(18,6) NULL,
    drawdown_pct DECIMAL(10,6) NULL,
    raw_payload JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_equity_snapshot_time (snapshot_time),
    KEY idx_account_time (account_type, snapshot_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sync_checkpoints (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    sync_name VARCHAR(64) NOT NULL,
    checkpoint_value VARCHAR(255) NULL,
    checkpoint_time DATETIME NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_sync_name (sync_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
