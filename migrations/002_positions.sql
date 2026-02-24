-- 持倉表
-- migrations/002_positions.sql

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10) NOT NULL,
    status VARCHAR(20) DEFAULT 'WATCHING',
    total_capital DECIMAL(15, 2),
    entry_price DECIMAL(10, 2),
    entry_quantity INTEGER,
    entry_total DECIMAL(15, 2),
    exit_price DECIMAL(10, 2),
    exit_quantity INTEGER,
    exit_total DECIMAL(15, 2),
    current_quantity INTEGER,
    current_value DECIMAL(15, 2),
    average_cost DECIMAL(10, 2),
    unrealized_pnl DECIMAL(15, 2),
    return_pct DECIMAL(8, 4),
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
