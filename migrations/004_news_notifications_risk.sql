-- 新聞記錄表 (MySQL)
-- migrations/004_news.sql

CREATE TABLE IF NOT EXISTS news (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(10),
    title VARCHAR(500),
    content TEXT,
    weight INT DEFAULT 0,
    sentiment VARCHAR(20) DEFAULT 'neutral',
    source VARCHAR(100),
    url VARCHAR(500),
    news_type VARCHAR(50) DEFAULT 'general',
    relevance_score INT,
    processed TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_news_symbol (symbol),
    INDEX idx_news_created (created_at),
    INDEX idx_news_sentiment (sentiment)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 推送記錄表
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    signal_id INT,
    channel VARCHAR(50),
    status VARCHAR(20) DEFAULT 'PENDING',
    sent_at DATETIME,
    error_message TEXT,
    INDEX idx_notifications_signal (signal_id),
    CONSTRAINT fk_notifications_signal FOREIGN KEY (signal_id) REFERENCES signals(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 風控日誌表
CREATE TABLE IF NOT EXISTS risk_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(10),
    rule_name VARCHAR(100),
    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    action_taken VARCHAR(100),
    metadata TEXT,
    INDEX idx_risk_logs_symbol (symbol),
    INDEX idx_risk_logs_triggered (triggered_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
