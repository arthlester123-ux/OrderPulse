# OrderPulse — Portfolio Documentation

**Project title:** E-Commerce Order Processing Analytics Dashboard: A Data-Driven Decision Support System for Order Monitoring and Fulfilment
**Subject:** Advanced Database Systems · **Task:** #13 E-Commerce Order Processing Platform
**Stack:** Python Flask · SQLite (MySQL schema included) · pandas · Chart.js

---

## Project Overview

Online stores record every order (who bought what, when, for how much, and what happened to it), but raw spreadsheets make it hard to see trends, bottlenecks or problems. OrderPulse imports order records from a CSV file, stores them in a relational database, and turns them into KPIs, charts, statistics, automatic insights and a risk report that helps sellers and administrators decide what to do next.

```
CSV file → Flask (validation & cleaning) → SQLite database → SQL queries → Analytics engine (pandas) → Dashboard & charts
```

## Section 1 · Project Background

**What problem does the project solve?**
Order data usually sits in spreadsheets or system exports. Managers cannot quickly answer: *How much did we sell? Which products and categories drive revenue? How many orders are still pending? Are cancellations rising? Which orders are stuck?* OrderPulse answers these in one place, instantly, without manual computation.

**Why is the project important?**
Fulfilment delays and cancellations directly cost revenue and customer trust. Seeing the pipeline (Pending → Processing → Shipped → Delivered / Cancelled), the best and worst products, and the orders at risk lets a business act early — restock, promote, chase a late shipment — instead of discovering problems after customers complain.

## Section 2 · Beneficiaries

**Primary:** Online-store owners and sellers · Order-processing / fulfilment staff · Customer-service staff (can see which orders are stuck).
**Secondary:** Inventory and purchasing managers (best/worst products, categories) · Store administrators and decision-makers (KPIs, forecast) · Customers (faster, fewer-error deliveries).

## Section 3 · System Features

| # | Feature | Purpose | Benefit |
|---|---|---|---|
| 1 | **CSV Import Module** | Upload order files; validates columns, cleans text, maps status synonyms, rejects bad rows, removes duplicate order IDs, supports Replace/Append, logs every import. | Removes manual encoding and prevents bad data from reaching the dashboard. |
| 2 | **Relational database** | `orders` table with constraints, 5 indexes, view `v_net_sales`, and `upload_log`. | Reliable storage and fast queries. |
| 3 | **KPI cards** | Total Orders, Total Revenue, Delivered, Pending (+ AOV, fulfilment success, cancellation rate, high-risk orders). | Instant business snapshot. |
| 4 | **Analytics dashboard** | Orders by Status, Monthly Sales Trend with 3-month forecast, Top 10 Products, Revenue by Category, status mix per month, weekday pattern, order-value histogram. | Reveals trends and patterns at a glance. |
| 5 | **Order statistics** | Mean, median, mode, standard deviation, variance, min/max, quartiles, IQR, coefficient of variation, skewness, fulfilment success rate. | Fast, quantitative summary of order behaviour. |
| 6 | **Auto-generated insights** | Plain-language findings (leading category, growth vs last month, busiest day, cancellation warning, loyalty…). | Speeds up decision-making. |
| 7 | **Filters** | Date range, category and status filters update every KPI, chart and table. | Lets users drill down. |
| 8 | **SQL Queries page** | Shows all 14 SQL queries, live results and execution plans. | Transparency; demonstrates database skills. |
| 9 | **Order Risk Detection (enhancement)** | Scores open orders 0–100 (High/Medium/Low) from order age, value, customer and product cancellation history. | Shows which orders to act on first. |
| 10 | **Orders browser & exports** | Search, sort, paginate; export filtered orders and the risk report as CSV; JSON API at `/api/dashboard`. | Integration and reporting. |

### Required enhancement — Order Risk Detection (Option A equivalent)
The template's *Academic Risk Prediction* (flag students at risk from grades) is adapted to e-commerce: flag **orders at risk** from their status and history.

| Rule | Points |
|---|---|
| Pending > 2 / 5 / 10 days | 25 / 45 / 60 |
| Processing > 4 / 8 / 14 days | 25 / 45 / 60 |
| Shipped (in transit) > 7 / 12 / 20 days | 25 / 45 / 60 |
| Order value in the top 10% | +15 |
| Customer has ≥ 3 cancelled orders | +15 |
| Product's cancellation rate ≥ 1.5× average | +10 |

Levels: **High ≥ 60**, **Medium 30–59**, **Low < 30**. Ages are measured against the newest order date in the data, so historical datasets still work.

## Section 4 · Community Impact

1. **How does the system help students?** It gives students a complete, working example of data-driven system design — importing, cleaning, storing, querying and visualising real-world-style data — and a portfolio-ready project.
2. **How does it help sellers/staff (the "teachers" of the business)?** It replaces manual spreadsheet work with instant answers, shows which orders are stuck, and highlights best- and worst-selling products so they can restock, promote or delist.
3. **How does it improve quality?** Monitoring cancellation and delivery rates, and flagging risky orders, leads to faster fulfilment, fewer lost sales and better customer experience.
4. **Future enhancements:** MySQL/PostgreSQL server database · user login and roles · multi-table import of the full Olist dataset (orders, items, payments, reviews) · machine-learning forecasts (ARIMA/Prophet) and churn prediction · e-mail/SMS alerts for high-risk orders · live connection to a real shop's database/API · inventory and branch modules.

---

## Dataset

Columns (as required by task #13): `order_id, customer, product, category, quantity, price, order_date, status`.
`sample_data/orders.csv` contains **1,500 orders** (Jan 1 – Nov 15, 2026; 237 customers; 42 products in 8 categories; prices in PHP) produced by the seeded script `tools/generate_dataset.py`. It models growth over time, weekend and double-day sale spikes (3.3, 4.4 … 11.11), a few best-selling products, loyal repeat customers and realistic status ageing (old orders mostly Delivered, recent ones Pending/Processing/Shipped, a small number of stuck orders). Real order data is private, so a generated set is appropriate; the system accepts any CSV in the same format (e.g. a flattened Olist/Kaggle export).

## Database Design

| Object | Description |
|---|---|
| `orders` | One row per order: `id` (PK), `order_id` (UNIQUE), `customer`, `product`, `category`, `quantity` (CHECK > 0), `price` (CHECK ≥ 0), `order_date` (ISO), `status` (CHECK in 5 values), `line_total` (= quantity × price) |
| `v_net_sales` | VIEW of orders where status ≠ Cancelled (revenue-generating orders) |
| `upload_log` | History of every import (file, mode, rows read/loaded/rejected, time) |
| Indexes | `order_date`, `status`, `category`, `product`, `customer` |

**Revenue definition:** quantity × price for all orders that are not Cancelled. The value of cancelled orders is reported separately as "lost revenue".

## SQL Queries (shown live on the *SQL Queries* page)

1. KPI summary (conditional aggregation) · 2. Orders by status (`GROUP BY`) · 3. Monthly sales trend (`strftime`, `GROUP BY`) · 4. Status mix per month · 5. **Top 10 products** (`ORDER BY revenue DESC LIMIT 10`) · 6. **Bottom 10 products** (`ORDER BY revenue ASC LIMIT 10`) · 7. Revenue by category · 8. Orders by weekday · 9. Top 10 customers · 10. Best product per category (**window function** `RANK() OVER (PARTITION BY …)` + CTE) · 11. Month-over-month growth and running total (`LAG`, cumulative `SUM() OVER`) · 12. Aging of open orders (`julianday`, subquery) · 13. Repeat cancellers (`GROUP BY … HAVING`) · 14. Net revenue through a **VIEW**.

## Statistical Measures

Mean (average order value), **median** (typical order), **mode** (most common order value / quantity), **standard deviation** and variance (spread), min/max, **quartiles & IQR**, **coefficient of variation** (relative variability), **skewness** (shape), **fulfilment success rate** = Delivered ÷ (Delivered + Cancelled) — the equivalent of the template's "pass rate". SQL computes the aggregates (`SUM`, `AVG`, `COUNT`, `MIN`, `MAX`); pandas computes median, mode, standard deviation, quartiles and skewness; NumPy fits the forecast line (least-squares linear regression on complete months, reported with R²).

---

## Defense Q&A

**1. Why did you choose this dataset?**
Task #13 is an e-commerce order platform. Order data (customer, product, category, quantity, price, date, status) directly supports the required KPIs and charts, is easy for users to understand, and lets us show the whole order pipeline. Real order data is private, so we generated a realistic 1,500-order dataset with a seeded script, and the system also accepts any CSV in the same format (for example a flattened Olist/Kaggle export).

**2. What database tables did you create?**
`orders` (main fact table with constraints and a computed `line_total`), `upload_log` (import history), the view `v_net_sales`, and five indexes on date, status, category, product and customer. A MySQL version of the schema is in `database/schema_mysql.sql`.

**3. What SQL queries generate the dashboard?**
They are all listed on the SQL Queries page. Examples: KPIs use conditional aggregation (`SUM(CASE WHEN …)`); Orders by Status uses `GROUP BY status`; the Sales Trend uses `strftime('%Y-%m', order_date)` with `GROUP BY month`; Top/Bottom 10 products use `ORDER BY revenue DESC/ASC LIMIT 10`; advanced ones use a window function (`RANK() OVER (PARTITION BY category …)`), `LAG`, a CTE, `HAVING` and a VIEW. All user inputs are passed as bound parameters (no string-built SQL values).

**4. What statistical measures did you use?**
Mean, median, mode, standard deviation, variance, min/max, quartiles/IQR, coefficient of variation, skewness and the fulfilment success rate, plus a linear-regression forecast with R². The order-value mean (about ₱1,568) is higher than the median (₱1,100) and skewness is positive, meaning a few large orders pull the average up.

**5. What insights can administrators gain from the dashboard?**
Revenue and average order value; which categories and products drive sales (Electronics ≈ 31% of revenue; top 10 products ≈ 49%); month-over-month growth and the next-month forecast; the busiest weekday; delivery performance and cancellation rate (and which category cancels most); how many open orders are at risk; how much revenue depends on the top 10% of customers.

**6. How does the system support decision-making?**
It converts raw rows into KPIs, trends and plain-language insights, with filters to drill down. Examples: restock best sellers before sale days, promote or delist the bottom-10 products, investigate categories with above-average cancellations, and act first on High-risk orders listed with the reason for each flag.

**7. What enhancement did your group implement?**
**Order Risk Detection** (the e-commerce version of "Academic Risk Prediction"). Each open order receives a transparent 0–100 score from order age by status, high value, the customer's cancellation history and the product's cancellation rate, and is classed High/Medium/Low. The page lists the reasons, shows value at stake, and exports a CSV report. We also added a 3-month sales forecast, filters, dark mode and a JSON API.

**8. How does this project demonstrate System Integration and Architecture?**
It is a layered architecture: *presentation* (HTML/Jinja templates, Chart.js), *application* (Flask routes, validation/cleaning), *data* (SQLite with constraints, view, indexes), and *analytics* (pandas/NumPy). Components integrate through well-defined interfaces: CSV import/export, SQL, and a JSON endpoint (`/api/dashboard`) that other systems can consume. The same SQL registry feeds both the dashboard and the SQL Queries page, keeping documentation and behaviour consistent.

**9. What are the limitations of your project?**
SQLite is single-file and suited to one or a few users (not heavy concurrent production use); the sample data is synthetic; the risk score is rule-based, not a trained model; the forecast is a simple linear trend; each CSV row is one product line (no separate order-items/payments tables); there is no user login; revenue ignores shipping, discounts and refunds beyond the Cancelled status.

**10. What future improvements would you recommend?**
Move to MySQL/PostgreSQL, add authentication and roles, import the full multi-table Olist dataset, add machine-learning forecasting and churn/risk prediction, send alerts for High-risk orders, schedule automatic imports, and connect directly to a live store database or API.

---

## Appendix — Screenshots

| Screen | File |
|---|---|
| Screen 1 — Empty state / load sample | `screenshots/00_empty_state.png` |
| Screen 2 — Dashboard (KPIs, insights, charts, statistics, tables) | `screenshots/02_dashboard_full.png` |
| Screen 3 — Dashboard with filters applied | `screenshots/07_dashboard_filtered.png` |
| Screen 4 — Dark mode | `screenshots/08_dashboard_dark.png` |
| Screen 5 — Order records | `screenshots/03_orders.png` |
| Screen 6 — Order Risk Detection | `screenshots/04_risk.png` |
| Screen 7 — SQL Queries | `screenshots/05_sql_queries.png` |
| Screen 8 — Upload CSV | `screenshots/06_upload.png` |
| Screen 9 — Mobile view | `screenshots/09_mobile.png` |
