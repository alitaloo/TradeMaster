-- 訂單表
-- migrations/003_orders.sql

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id VARCHAR(50) UNIQUE,
    symbol VARCHAR(10) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    price DECIMAL(10, 2),
    quantity INTEGER,
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price DECIMAL(10, 2),
    status VARCHAR(20) DEFAULT 'PENDING',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    filled_at DATETIME,
    cancelled_at DATETIME,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
