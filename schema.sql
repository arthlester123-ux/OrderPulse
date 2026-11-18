-- OrderPulse database schema (SQLite). Created automatically by app.py on first run.
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT    NOT NULL UNIQUE,
    customer    TEXT    NOT NULL,
    product     TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    price       REAL    NOT NULL CHECK (price >= 0),
    order_date  TEXT    NOT NULL,                       -- ISO date YYYY-MM-DD
    status      TEXT    NOT NULL CHECK (status IN ('Pending','Processing','Shipped','Delivered','Cancelled')),
    line_total  REAL    NOT NULL                        -- quantity * price
);
CREATE INDEX IF NOT EXISTS idx_orders_date     ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_category ON orders(category);
CREATE INDEX IF NOT EXISTS idx_orders_product  ON orders(product);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer);

CREATE VIEW IF NOT EXISTS v_net_sales AS SELECT * FROM orders WHERE status <> 'Cancelled';

CREATE TABLE IF NOT EXISTS upload_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, mode TEXT NOT NULL,
    rows_read INTEGER NOT NULL, rows_loaded INTEGER NOT NULL, rows_rejected INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
