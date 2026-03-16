-- 訂單表 (MySQL)
-- migrations/003_orders.sql

CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE,
    symbol VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    price DECIMAL(10, 2),
    quantity INT,
    filled_quantity INT DEFAULT 0,
    avg_fill_price DECIMAL(10, 2),
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    filled_at DATETIME,
    cancelled_at DATETIME,
    metadata TEXT,
    INDEX idx_orders_symbol (symbol),
    INDEX idx_orders_status (status),
    INDEX idx_orders_order_id (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
