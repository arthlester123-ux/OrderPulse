# OrderPulse — E-Commerce Order Processing Analytics Dashboard

A web-based decision-support system built with **Flask + SQLite + pandas + Chart.js**.
It imports order records from a CSV file, stores them in a database, runs SQL queries and
statistics, and shows KPIs, charts, automatic insights and an order-risk report.

> Assigned task: **#13 E-Commerce Order Processing Platform** · Advanced Database Systems
> Structure follows the teacher's `student_analytics_dashboard` template (app.py, templates/, static/, CSV upload → database → dashboard).

## Run it (Windows)

```
cd OrderPulse
pip install -r requirements.txt      (or: pip install flask pandas)
python app.py
```
Open **http://127.0.0.1:5000** → click **Load sample dataset** (or **Upload CSV** and choose `sample_data/orders.csv`).

Troubleshooting: `No module named flask` → `pip install flask` · `No module named pandas` → `pip install pandas`.
Chart.js is bundled locally (`static/js/chart.umd.js`), so it works **without internet**.

## What the system does

| Template requirement | Where |
|---|---|
| Upload CSV files | **Upload CSV** page (validation, cleaning, replace/append, import history) |
| Store data in a database | `orders.db` (SQLite) · MySQL version in `database/schema_mysql.sql` |
| Statistical summaries | Dashboard → *Statistical analysis* (mean, median, mode, std dev, variance, quartiles, CV, skewness, success rate) |
| Dashboards + charts | Dashboard (4 required KPIs + 4 extra, 7 charts, tables) |
| Insights from the data | *Key insights* (auto-generated sentences) |
| SQL queries (Top 10, Bottom 10, …) | **SQL Queries** page — 14 queries with live results and execution plans |
| Required enhancement | **Order Risk** page — flags open orders likely to be stuck or cancelled |

### Required KPIs & charts (task #13)
KPIs: **Total Orders · Total Revenue · Delivered Orders · Pending Orders** (+ Avg Order Value, Fulfilment Success, Cancellation Rate, High-Risk Open Orders).
Charts: **Orders by Status · Sales Trend (with forecast) · Top Products · Revenue by Category** (+ status mix per month, weekday pattern, order-value histogram).

### Extras beyond the template
Date / category / status filters that update every number · dark mode · table view for every chart · CSV export (orders and risk report) ·
JSON API (`/api/dashboard`) · searchable, sortable order browser · 3-month sales forecast · SQL window functions, CTE, view, indexes · print-to-PDF.

## CSV format
```
order_id,customer,product,category,quantity,price,order_date,status
ORD001,John Cruz,Wireless Mouse,Electronics,2,500,2026-10-01,Delivered
```
Status values: Pending, Processing, Shipped, Delivered, Cancelled (common synonyms such as *completed*, *canceled*, *in transit* are mapped automatically).
Other datasets (e.g. the Olist Brazilian E-Commerce export) can be loaded once they are flattened to these columns; common column aliases are recognised.

To regenerate the sample file: `python tools/generate_dataset.py 1500`.

## Project structure
```
OrderPulse/
├── app.py                 Flask app: routes, import/cleaning, SQL registry, analytics, risk model
├── requirements.txt
├── database/              schema.sql (SQLite) · schema_mysql.sql (optional MySQL)
├── sample_data/orders.csv 1,500 generated orders (Jan–Nov 2026)
├── tools/generate_dataset.py
├── static/css/style.css · static/js/charts.js · static/js/chart.umd.js
├── templates/             base, dashboard, orders, risk, queries, upload …
├── screenshots/           for the documentation appendix
└── PORTFOLIO_DOCUMENTATION.md   background, features, impact, defense Q&A
```
`orders.db` is created automatically on first run (delete it to reset).

## Notes
* Revenue = quantity × price of every order that is **not Cancelled**; cancelled value is reported separately as "lost".
* The sample dataset is synthetic (seeded generator) because real order data is private. The system accepts any CSV in the format above.
* Set `SECRET_KEY` as an environment variable before any real deployment.
