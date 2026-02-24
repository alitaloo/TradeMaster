-- 新聞記錄表
-- migrations/004_news.sql

CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10),
    title VARCHAR(500),
    source VARCHAR(100),
    news_type VARCHAR(50),
    weight INTEGER DEFAULT 0,
    relevance_score INTEGER,
    processed BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_news_symbol ON news(symbol);
CREATE INDEX IF NOT EXISTS idx_news_created ON news(created_at);

-- 推送記錄表
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER,
    channel VARCHAR(50),
    status VARCHAR(20) DEFAULT 'PENDING',
    sent_at DATETIME,
    error_message TEXT,
    FOREIGN KEY (signal_id) REFERENCES signals(id)
);

CREATE INDEX IF NOT EXISTS idx_notifications_signal ON notifications(signal_id);

-- 風控日誌表
CREATE TABLE IF NOT EXISTS risk_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(10),
    rule_name VARCHAR(100),
    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    action_taken VARCHAR(100),
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_risk_logs_symbol ON risk_logs(symbol);
CREATE INDEX IF NOT EXISTS idx_risk_logs_triggered ON risk_logs(triggered_at);
