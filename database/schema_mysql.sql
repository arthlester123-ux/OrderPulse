-- OPTIONAL: MySQL version of the same schema (the project template mentions MySQL).
-- The app ships with SQLite so it runs with zero setup; use this file to show the
-- equivalent MySQL design or to migrate the data (export CSV from the app, then LOAD DATA).
CREATE DATABASE IF NOT EXISTS orderpulse CHARACTER SET utf8mb4;
USE orderpulse;

CREATE TABLE IF NOT EXISTS orders (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    order_id    VARCHAR(30)  NOT NULL UNIQUE,
    customer    VARCHAR(100) NOT NULL,
    product     VARCHAR(120) NOT NULL,
    category    VARCHAR(60)  NOT NULL,
    quantity    INT          NOT NULL CHECK (quantity > 0),
    price       DECIMAL(10,2) NOT NULL CHECK (price >= 0),
    order_date  DATE         NOT NULL,
    status      ENUM('Pending','Processing','Shipped','Delivered','Cancelled') NOT NULL,
    line_total  DECIMAL(12,2) AS (quantity * price) STORED,
    INDEX idx_date (order_date), INDEX idx_status (status), INDEX idx_category (category),
    INDEX idx_product (product), INDEX idx_customer (customer)
);

CREATE OR REPLACE VIEW v_net_sales AS SELECT * FROM orders WHERE status <> 'Cancelled';

-- Example: Top 10 products (MySQL syntax)
SELECT product, SUM(line_total) AS revenue FROM v_net_sales GROUP BY product ORDER BY revenue DESC LIMIT 10;
-- Example: monthly trend (MySQL uses DATE_FORMAT instead of strftime)
SELECT DATE_FORMAT(order_date, '%Y-%m') AS month, SUM(line_total) AS revenue FROM v_net_sales GROUP BY month ORDER BY month;
