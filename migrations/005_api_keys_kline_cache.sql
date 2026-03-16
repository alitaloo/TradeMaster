-- API Keys 表（從 SQLite auth 遷移）
-- migrations/005_api_keys_kline_cache.sql

CREATE TABLE IF NOT EXISTS api_keys (
    id INT AUTO_INCREMENT PRIMARY KEY,
    key_id VARCHAR(50) UNIQUE NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    name VARCHAR(100),
    permissions VARCHAR(200),
    rate_limit INT DEFAULT 100,
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_used_at DATETIME,
    INDEX idx_api_keys_key_id (key_id),
    INDEX idx_api_keys_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- K線快取表（從 SQLite kline_cache.db 遷移）
CREATE TABLE IF NOT EXISTS kline_cache (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    interval_val VARCHAR(10) NOT NULL,
    timestamp DATETIME NOT NULL,
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    close_price DECIMAL(12,4),
    volume BIGINT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_kline (symbol, interval_val, timestamp),
    INDEX idx_kline_symbol (symbol),
    INDEX idx_kline_interval (interval_val),
    INDEX idx_kline_ts (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 即時報價表（取代 SQLite realtime_quote）
CREATE TABLE IF NOT EXISTS realtime_quote (
    symbol VARCHAR(20) NOT NULL PRIMARY KEY,
    last_price DECIMAL(12,4),
    open_price DECIMAL(12,4),
    high_price DECIMAL(12,4),
    low_price DECIMAL(12,4),
    prev_close DECIMAL(12,4),
    volume BIGINT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_quote_updated (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
