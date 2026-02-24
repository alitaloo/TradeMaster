-- 信號表
-- migrations/001_signals.sql

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10) NOT NULL,
    strategy_type VARCHAR(50),
    signal_type VARCHAR(10) NOT NULL,
    price DECIMAL(10, 2),
    quantity INTEGER,
    confidence DECIMAL(4, 3),
    status VARCHAR(20) DEFAULT 'PENDING',
    risk_score INTEGER,
    news_weight INTEGER,
    stop_loss DECIMAL(10, 2),
    take_profit DECIMAL(10, 2),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    sent_at DATETIME,
    executed_at DATETIME,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
