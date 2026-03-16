-- 信號表 (MySQL)
-- migrations/001_signals.sql

CREATE TABLE IF NOT EXISTS signals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy_type VARCHAR(50),
    signal_type VARCHAR(10) NOT NULL,
    price DECIMAL(10, 2),
    quantity INT,
    confidence DECIMAL(4, 3),
    status VARCHAR(20) DEFAULT 'PENDING',
    risk_score INT,
    news_weight INT,
    stop_loss DECIMAL(10, 2),
    take_profit DECIMAL(10, 2),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME,
    executed_at DATETIME,
    metadata TEXT,
    INDEX idx_signals_symbol (symbol),
    INDEX idx_signals_status (status),
    INDEX idx_signals_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
