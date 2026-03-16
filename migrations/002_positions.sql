-- 持倉表 (MySQL)
-- migrations/002_positions.sql

CREATE TABLE IF NOT EXISTS positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    status VARCHAR(20) DEFAULT 'WATCHING',
    total_capital DECIMAL(15, 2),
    entry_price DECIMAL(10, 2),
    entry_quantity INT,
    entry_total DECIMAL(15, 2),
    exit_price DECIMAL(10, 2),
    exit_quantity INT,
    exit_total DECIMAL(15, 2),
    current_quantity INT,
    current_value DECIMAL(15, 2),
    average_cost DECIMAL(10, 2),
    unrealized_pnl DECIMAL(15, 2),
    return_pct DECIMAL(8, 4),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_positions_symbol (symbol),
    INDEX idx_positions_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
