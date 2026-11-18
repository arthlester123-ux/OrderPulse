"""
OrderPulse - E-Commerce Order Processing Analytics Dashboard
A data-driven decision support system built with Flask + SQLite + pandas + Chart.js.

Architecture:  CSV  ->  Flask (validation / cleaning)  ->  SQLite (orders table)
               ->  SQL queries  ->  Analytics engine (pandas)  ->  Dashboard & charts
"""
import csv
import io
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from flask import (Flask, Response, abort, flash, g, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "orderpulse-dev-key-change-me")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB upload limit

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "orders.db")
SAMPLE_CSV = os.path.join(BASE_DIR, "sample_data", "orders.csv")

APP_NAME = "OrderPulse"
APP_TITLE = "E-Commerce Order Processing Analytics Dashboard"

COLUMNS = ["order_id", "customer", "product", "category",
           "quantity", "price", "order_date", "status"]
STATUS_ORDER = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]
OPEN_STATUSES = ("Pending", "Processing", "Shipped")

# Column-name aliases so other datasets (e.g. Olist / Kaggle exports) can be loaded too
ALIASES = {
    "order_id": ["orderid", "order id", "order_no", "order number", "order_number"],
    "customer": ["customer_name", "customer name", "client", "buyer", "customer_id"],
    "product": ["product_name", "product name", "item", "item_name", "product_id"],
    "category": ["product_category", "product_category_name", "category_name"],
    "quantity": ["qty", "units", "order_item_qty"],
    "price": ["unit_price", "unit price", "price_php"],
    "order_date": ["date", "orderdate", "order date", "order_purchase_timestamp",
                   "purchase_date", "date_ordered"],
    "status": ["order_status"],
}
STATUS_MAP = {
    "pending": "Pending", "new": "Pending", "created": "Pending",
    "awaiting payment": "Pending", "placed": "Pending",
    "processing": "Processing", "approved": "Processing", "invoiced": "Processing",
    "packed": "Processing", "to ship": "Processing", "preparing": "Processing",
    "shipped": "Shipped", "in transit": "Shipped", "out for delivery": "Shipped",
    "delivered": "Delivered", "completed": "Delivered", "complete": "Delivered",
    "received": "Delivered",
    "cancelled": "Cancelled", "canceled": "Cancelled", "unavailable": "Cancelled",
    "returned": "Cancelled", "refunded": "Cancelled", "failed": "Cancelled",
}

# Risk-model parameters (documented in the Risk page and the README)
AGE_RULES = {            # status -> [(min_age_days, points, label)]  highest matching rule wins
    "Pending":    [(2, 25, "Pending"), (5, 45, "Pending"), (10, 60, "Pending")],
    "Processing": [(4, 25, "Processing"), (8, 45, "Processing"), (14, 60, "Processing")],
    "Shipped":    [(7, 25, "In transit"), (12, 45, "In transit"), (20, 60, "In transit")],
}
HIGH_VALUE_PERCENTILE = 90
HIGH_VALUE_POINTS = 15
REPEAT_CANCEL_MIN = 3
REPEAT_CANCEL_POINTS = 15
PRODUCT_CANCEL_FACTOR = 1.5
PRODUCT_CANCEL_POINTS = 10
PRODUCT_MIN_ORDERS = 10
LEVEL_HIGH, LEVEL_MEDIUM = 60, 30


# ---------------------------------------------------------------- database
SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    TEXT    NOT NULL UNIQUE,
    customer    TEXT    NOT NULL,
    product     TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    price       REAL    NOT NULL CHECK (price >= 0),
    order_date  TEXT    NOT NULL,                      -- ISO date YYYY-MM-DD
    status      TEXT    NOT NULL CHECK (status IN
                ('Pending','Processing','Shipped','Delivered','Cancelled')),
    line_total  REAL    NOT NULL                       -- quantity * price
);
CREATE INDEX IF NOT EXISTS idx_orders_date     ON orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_category ON orders(category);
CREATE INDEX IF NOT EXISTS idx_orders_product  ON orders(product);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer);

CREATE VIEW IF NOT EXISTS v_net_sales AS          -- revenue-generating orders only
    SELECT * FROM orders WHERE status <> 'Cancelled';

CREATE TABLE IF NOT EXISTS upload_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    filename    TEXT NOT NULL,
    mode        TEXT NOT NULL,
    rows_read   INTEGER NOT NULL,
    rows_loaded INTEGER NOT NULL,
    rows_rejected INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, timeout=15)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    con.commit()
    con.close()


init_db()


# ---------------------------------------------------------------- security / helpers
def csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(24)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def csrf_protect():
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
            abort(400, description="Form session expired. Go back, refresh the page and try again.")


@app.template_filter("peso")
def peso(v):
    return "₱{:,.0f}".format(v or 0)


@app.template_filter("peso2")
def peso2(v):
    return "₱{:,.2f}".format(v or 0)


@app.template_filter("num")
def num(v):
    return "{:,}".format(int(v or 0))


@app.template_filter("compact")
def compact(v):
    v = float(v or 0)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= div:
            return "₱{:.2f}{}".format(v / div, suf)
    return "₱{:,.0f}".format(v)


def py(x):
    """Convert numpy / pandas scalars to plain Python values (JSON friendly)."""
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if np.isnan(x) else float(x)
    return x


def table_has_data():
    return get_db().execute("SELECT 1 FROM orders LIMIT 1").fetchone() is not None


# ---------------------------------------------------------------- filters
def get_filters():
    f = {
        "start": request.args.get("start", "").strip(),
        "end": request.args.get("end", "").strip(),
        "category": request.args.get("category", "").strip(),
        "status": request.args.get("status", "").strip(),
    }
    for key in ("start", "end"):          # validate dates
        try:
            if f[key]:
                datetime.strptime(f[key], "%Y-%m-%d")
        except ValueError:
            f[key] = ""
    if f["status"] not in STATUS_ORDER:
        f["status"] = ""
    return f


def where_clause(f):
    conds, params = ["1=1"], []
    if f.get("start"):
        conds.append("order_date >= ?")
        params.append(f["start"])
    if f.get("end"):
        conds.append("order_date <= ?")
        params.append(f["end"])
    if f.get("category"):
        conds.append("category = ?")
        params.append(f["category"])
    if f.get("status"):
        conds.append("status = ?")
        params.append(f["status"])
    return "WHERE " + " AND ".join(conds), params


def filter_qs(f):
    return {k: v for k, v in f.items() if v}


# ---------------------------------------------------------------- SQL query registry
# Every number on the dashboard comes from one of these queries ({W} = the active filter).
QUERIES = {}


def register(key, title, purpose, sql, group="Dashboard"):
    QUERIES[key] = {"key": key, "title": title, "purpose": purpose,
                    "sql": sql.strip(), "group": group}


register("kpi", "KPI summary", "Total orders, revenue, delivered, pending and other headline numbers in one pass.",
         """SELECT COUNT(*)                                                        AS total_orders,
       SUM(CASE WHEN status <> 'Cancelled' THEN line_total ELSE 0 END)  AS revenue,
       SUM(CASE WHEN status  = 'Cancelled' THEN line_total ELSE 0 END)  AS lost_revenue,
       SUM(status = 'Delivered')                                         AS delivered,
       SUM(status = 'Pending')                                           AS pending,
       SUM(status = 'Processing')                                        AS processing,
       SUM(status = 'Shipped')                                           AS shipped,
       SUM(status = 'Cancelled')                                         AS cancelled,
       COUNT(DISTINCT customer)                                          AS customers,
       SUM(CASE WHEN status <> 'Cancelled' THEN quantity ELSE 0 END)    AS units
FROM orders {W}""")

register("status", "Orders by status", "Chart 1 - how many orders sit in each stage of the pipeline.",
         """SELECT status, COUNT(*) AS orders, ROUND(SUM(line_total), 2) AS order_value
FROM orders {W}
GROUP BY status""")

register("monthly", "Monthly sales trend", "Chart 2 - revenue and order volume per month (cancelled orders excluded from revenue).",
         """SELECT strftime('%Y-%m', order_date) AS month,
       COUNT(*)                                                       AS orders,
       ROUND(SUM(CASE WHEN status <> 'Cancelled' THEN line_total ELSE 0 END), 2) AS revenue
FROM orders {W}
GROUP BY month
ORDER BY month""")

register("status_month", "Status mix per month", "Chart 5 - monthly orders split by status (stacked).",
         """SELECT strftime('%Y-%m', order_date) AS month, status, COUNT(*) AS orders
FROM orders {W}
GROUP BY month, status
ORDER BY month""")

register("top_products", "Top 10 products by revenue", "Chart 3 - best sellers (ORDER BY revenue DESC).",
         """SELECT product, category, SUM(quantity) AS units, ROUND(SUM(line_total), 2) AS revenue
FROM orders {W} AND status <> 'Cancelled'
GROUP BY product, category
ORDER BY revenue DESC
LIMIT 10""")

register("bottom_products", "Bottom 10 products by revenue", "Slowest movers (ORDER BY revenue ASC) - candidates for promotion or delisting.",
         """SELECT product, category, SUM(quantity) AS units, ROUND(SUM(line_total), 2) AS revenue
FROM orders {W} AND status <> 'Cancelled'
GROUP BY product, category
ORDER BY revenue ASC
LIMIT 10""")

register("category", "Revenue by category", "Chart 4 - revenue, volume and cancellation rate per category.",
         """SELECT category,
       COUNT(*)      AS orders,
       SUM(quantity) AS units,
       ROUND(SUM(CASE WHEN status <> 'Cancelled' THEN line_total ELSE 0 END), 2) AS revenue,
       ROUND(100.0 * SUM(status = 'Cancelled') / COUNT(*), 1)                  AS cancel_rate
FROM orders {W}
GROUP BY category
ORDER BY revenue DESC""")

register("weekday", "Orders by weekday", "Chart 6 - which days customers order the most (0 = Sunday).",
         """SELECT CAST(strftime('%w', order_date) AS INTEGER) AS weekday,
       COUNT(*) AS orders,
       ROUND(SUM(CASE WHEN status <> 'Cancelled' THEN line_total ELSE 0 END), 2) AS revenue
FROM orders {W}
GROUP BY weekday
ORDER BY weekday""")

register("top_customers", "Top 10 customers by spend", "Highest-value customers (ORDER BY spent DESC).",
         """SELECT customer, COUNT(*) AS orders, ROUND(SUM(line_total), 2) AS spent
FROM orders {W} AND status <> 'Cancelled'
GROUP BY customer
ORDER BY spent DESC
LIMIT 10""")

# --- advanced queries (SQL Queries page only) -------------------------------------------------
register("best_in_category", "Best-selling product in each category (window function)",
         "RANK() OVER (PARTITION BY ...) ranks products inside their own category; we keep rank 1.",
         """WITH product_rev AS (
    SELECT category, product, SUM(line_total) AS revenue
    FROM orders {W} AND status <> 'Cancelled'
    GROUP BY category, product
)
SELECT category, product, ROUND(revenue, 2) AS revenue
FROM (SELECT *, RANK() OVER (PARTITION BY category ORDER BY revenue DESC) AS rnk
      FROM product_rev)
WHERE rnk = 1
ORDER BY revenue DESC""", group="Advanced")

register("growth", "Month-over-month growth and running total (LAG + cumulative SUM)",
         "Window functions compute growth against the previous month and a cumulative revenue line.",
         """WITH m AS (
    SELECT strftime('%Y-%m', order_date) AS month,
           SUM(CASE WHEN status <> 'Cancelled' THEN line_total ELSE 0 END) AS revenue
    FROM orders {W}
    GROUP BY month
)
SELECT month,
       ROUND(revenue, 2)                                        AS revenue,
       ROUND(SUM(revenue) OVER (ORDER BY month), 2)             AS cumulative_revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
                   / LAG(revenue) OVER (ORDER BY month), 1)     AS mom_growth_pct
FROM m
ORDER BY month""", group="Advanced")

register("aging", "Aging of open orders (julianday date arithmetic + subquery)",
         "Open orders ranked by how long they have waited, measured against the newest order date in the data.",
         """SELECT order_id, customer, status, order_date,
       CAST(julianday((SELECT MAX(order_date) FROM orders)) - julianday(order_date) AS INTEGER) AS age_days,
       line_total
FROM orders {W} AND status IN ('Pending', 'Processing', 'Shipped')
ORDER BY age_days DESC, line_total DESC
LIMIT 10""", group="Advanced")

register("repeat_cancel", "Customers with repeated cancellations (GROUP BY + HAVING)",
         "HAVING filters groups after aggregation - used by the risk model.",
         """SELECT customer,
       COUNT(*)                 AS orders,
       SUM(status = 'Cancelled') AS cancelled,
       ROUND(100.0 * SUM(status = 'Cancelled') / COUNT(*), 1) AS cancel_rate
FROM orders {W}
GROUP BY customer
HAVING SUM(status = 'Cancelled') >= 3
ORDER BY cancelled DESC, cancel_rate DESC
LIMIT 10""", group="Advanced")

register("view_sales", "Net revenue through a VIEW",
         "v_net_sales is a stored view of non-cancelled orders, so reports never repeat the cancel filter.",
         """SELECT category, ROUND(SUM(line_total), 2) AS net_revenue, COUNT(*) AS orders
FROM v_net_sales
WHERE 1=1 {F}
GROUP BY category
ORDER BY net_revenue DESC""", group="Advanced")


def render_query(key, f):
    spec = QUERIES[key]
    W, P = where_clause(f)
    sql = spec["sql"]
    if "{F}" in sql:                       # view query: reuse conditions without the WHERE keyword
        sql = sql.replace("{F}", " AND " + W[len("WHERE 1=1 AND "):] if len(P) else "")
        return sql, list(P)
    n = sql.count("{W}")
    return sql.replace("{W}", W), list(P) * n


def run_query(key, f):
    sql, params = render_query(key, f)
    return [dict(r) for r in get_db().execute(sql, params).fetchall()]


# ---------------------------------------------------------------- CSV import
def _normalise_columns(df):
    df = df.copy()
    df.columns = [str(c).strip().lower().replace("﻿", "") for c in df.columns]
    for canon, alts in ALIASES.items():
        if canon not in df.columns:
            for a in alts:
                if a in df.columns:
                    df = df.rename(columns={a: canon})
                    break
    return df


def import_dataframe(df, filename, mode="replace"):
    """Validate + clean a DataFrame and load it into the orders table. Returns a report dict."""
    df = _normalise_columns(df)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        return {"ok": False, "error": "Missing required column(s): " + ", ".join(missing)}

    rows_read = len(df)
    df = df[COLUMNS].copy()
    rejected = {}

    def reject(mask, reason):
        nonlocal df
        n = int(mask.sum())
        if n:
            rejected[reason] = rejected.get(reason, 0) + n
            df = df[~mask].copy()

    for c in ("order_id", "customer", "product", "category"):
        df[c] = df[c].astype(str).str.strip()
        df.loc[df[c].str.lower().isin(["", "nan", "none", "null"]), c] = None
    reject(df[["order_id", "customer", "product", "category"]].isna().any(axis=1), "missing text value")

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    reject(df["quantity"].isna() | (df["quantity"] <= 0), "invalid quantity")
    df["quantity"] = df["quantity"].round().astype(int)

    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    reject(df["price"].isna() | (df["price"] < 0), "invalid price")

    try:
        dates = pd.to_datetime(df["order_date"], errors="coerce", format="mixed")
    except (TypeError, ValueError):
        dates = pd.to_datetime(df["order_date"], errors="coerce")
    reject(dates.isna(), "invalid date")
    df["order_date"] = dates.loc[df.index].dt.strftime("%Y-%m-%d")

    df["status"] = df["status"].astype(str).str.strip().str.lower().map(STATUS_MAP)
    reject(df["status"].isna(), "unknown status")

    reject(df.duplicated(subset="order_id", keep="first"), "duplicate order_id in file")

    con = get_db()
    if mode == "append":
        existing = {r[0] for r in con.execute("SELECT order_id FROM orders")}
        reject(df["order_id"].isin(existing), "order_id already in database")

    if df.empty:
        return {"ok": False, "error": "No valid rows found. Rejected: " +
                ", ".join(f"{k} ({v})" for k, v in rejected.items())}

    df["line_total"] = (df["quantity"] * df["price"]).round(2)
    records = [tuple(py(v) for v in row) for row in
               df[COLUMNS + ["line_total"]].itertuples(index=False, name=None)]
    try:
        with con:
            if mode == "replace":
                con.execute("DELETE FROM orders")
            con.executemany(
                "INSERT INTO orders (order_id, customer, product, category, quantity, price,"
                " order_date, status, line_total) VALUES (?,?,?,?,?,?,?,?,?)", records)
            con.execute("INSERT INTO upload_log (filename, mode, rows_read, rows_loaded, rows_rejected)"
                        " VALUES (?,?,?,?,?)",
                        (filename, mode, rows_read, len(records), rows_read - len(records)))
    except sqlite3.Error as exc:
        return {"ok": False, "error": f"Database error: {exc}"}
    return {"ok": True, "read": rows_read, "loaded": len(records),
            "rejected": rows_read - len(records), "reasons": rejected}


def report_message(rep):
    msg = f"Imported {rep['loaded']:,} of {rep['read']:,} rows."
    if rep["rejected"]:
        msg += " Skipped " + ", ".join(f"{v} ({k})" for k, v in rep["reasons"].items()) + "."
    return msg


# ---------------------------------------------------------------- analytics engine
def load_df(f):
    W, P = where_clause(f)
    return pd.read_sql_query(
        f"SELECT order_id, customer, product, category, quantity, price, order_date, status, line_total "
        f"FROM orders {W}", get_db(), params=P)


def describe(series):
    """Descriptive statistics for a numeric series."""
    s = pd.Series(series).dropna().astype(float)
    if s.empty:
        return None
    mode_vals = s.mode()
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    mean, std = s.mean(), s.std(ddof=1) if len(s) > 1 else 0.0
    return {
        "count": int(len(s)), "mean": float(mean), "median": float(s.median()),
        "mode": float(mode_vals.iloc[0]), "mode_count": int((s == mode_vals.iloc[0]).sum()),
        "std": float(std), "variance": float(s.var(ddof=1)) if len(s) > 1 else 0.0,
        "min": float(s.min()), "max": float(s.max()), "q1": float(q1), "q3": float(q3),
        "iqr": float(q3 - q1), "cv": float(std / mean * 100) if mean else 0.0,
        "skew": float(s.skew()) if len(s) > 2 else 0.0,
    }


def histogram(values, bins=10):
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return {"labels": [], "values": []}
    cap = float(np.percentile(v, 95))
    step = max(100.0, round(cap / bins / 100.0) * 100.0)
    edges = [step * i for i in range(bins + 1)]
    counts = [int(((v >= edges[i]) & (v < edges[i + 1])).sum()) for i in range(bins)]
    counts.append(int((v >= edges[-1]).sum()))
    labels = [f"{int(edges[i]):,}–{int(edges[i + 1]):,}" for i in range(bins)] + [f"{int(edges[-1]):,}+"]
    return {"labels": labels, "values": counts}


def month_label(m):
    return datetime.strptime(m, "%Y-%m").strftime("%b %Y")


def next_months(last, n):
    y, m = map(int, last.split("-"))
    out = []
    for _ in range(n):
        m += 1
        if m > 12:
            y, m = y + 1, 1
        out.append(f"{y}-{m:02d}")
    return out


def build_trend(monthly, data_max):
    """Monthly revenue + linear-regression forecast over *complete* months only."""
    months = [r["month"] for r in monthly]
    revenue = [r["revenue"] for r in monthly]
    orders = [r["orders"] for r in monthly]
    complete = []
    for m, rev in zip(months, revenue):
        y, mo = map(int, m.split("-"))
        month_end = (datetime(y + (mo == 12), mo % 12 + 1, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
        complete.append(bool(data_max and month_end <= data_max))
    out = {"months": months, "labels": [month_label(m) for m in months], "revenue": revenue,
           "orders": orders, "complete": complete, "forecast": None}
    idx = [i for i, c in enumerate(complete) if c]
    if len(idx) >= 4:
        x = np.arange(len(idx), dtype=float)
        y = np.array([revenue[i] for i in idx], dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        pred = slope * x + intercept
        ss_res, ss_tot = float(((y - pred) ** 2).sum()), float(((y - y.mean()) ** 2).sum())
        r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
        last_complete = months[idx[-1]]
        fut = next_months(last_complete, 3)
        fvals = [max(0.0, float(slope * (len(idx) + k) + intercept)) for k in range(3)]
        all_months = months + [m for m in fut if m not in months]
        fc = [None] * len(all_months)
        fc[all_months.index(last_complete)] = revenue[idx[-1]]       # anchor so the line connects
        for m, v in zip(fut, fvals):
            fc[all_months.index(m)] = round(v, 2)
        out.update({
            "months": all_months, "labels": [month_label(m) for m in all_months],
            "revenue": revenue + [None] * (len(all_months) - len(months)),
            "orders": orders + [None] * (len(all_months) - len(months)),
            "complete": complete + [False] * (len(all_months) - len(months)),
            "forecast": fc,
            "forecast_info": {"slope": float(slope), "r2": float(r2),
                              "next_month": fut[0], "next_value": fvals[0],
                              "next3_total": float(sum(fvals)), "last_complete": last_complete},
        })
    return out


# ---------------------------------------------------------------- risk detection (required enhancement)
def compute_risk(f):
    """Score every open order 0-100 and classify High / Medium / Low risk."""
    con = get_db()
    ref = con.execute("SELECT MAX(order_date) FROM orders").fetchone()[0]
    if not ref:
        return pd.DataFrame(), {}
    W, P = where_clause({**f, "status": ""})
    open_df = pd.read_sql_query(
        f"SELECT order_id, customer, product, category, quantity, order_date, status, line_total "
        f"FROM orders {W} AND status IN ('Pending','Processing','Shipped')", con, params=P)

    all_df = pd.read_sql_query("SELECT customer, product, status, line_total FROM orders", con)
    net = all_df[all_df.status != "Cancelled"]["line_total"]
    high_value_cut = float(np.percentile(net, HIGH_VALUE_PERCENTILE)) if len(net) else float("inf")
    cust_cancel = all_df[all_df.status == "Cancelled"].groupby("customer").size()
    overall_rate = float((all_df.status == "Cancelled").mean()) if len(all_df) else 0.0
    prod = all_df.groupby("product").agg(n=("status", "size"), c=("status", lambda s: (s == "Cancelled").sum()))
    risky_products = set(prod[(prod.n >= PRODUCT_MIN_ORDERS) &
                              (prod.c / prod.n >= overall_rate * PRODUCT_CANCEL_FACTOR)].index)

    ref_dt = pd.Timestamp(ref)
    scores, levels, reasons, ages = [], [], [], []
    for r in open_df.itertuples(index=False):
        age = int((ref_dt - pd.Timestamp(r.order_date)).days)
        pts, why = 0, []
        for min_age, p, label in AGE_RULES[r.status]:
            if age > min_age and p > pts:
                pts, text = p, f"{label} for {age} days"
        if pts:
            why.append(text)
        if r.line_total >= high_value_cut:
            pts += HIGH_VALUE_POINTS
            why.append(f"High-value order (≥ ₱{high_value_cut:,.0f})")
        n_c = int(cust_cancel.get(r.customer, 0))
        if n_c >= REPEAT_CANCEL_MIN:
            pts += REPEAT_CANCEL_POINTS
            why.append(f"Customer has {n_c} cancelled orders")
        if r.product in risky_products:
            pts += PRODUCT_CANCEL_POINTS
            why.append("Product has high cancellation rate")
        pts = min(100, pts)
        scores.append(pts)
        levels.append("High" if pts >= LEVEL_HIGH else "Medium" if pts >= LEVEL_MEDIUM else "Low")
        reasons.append("; ".join(why) if why else "On schedule")
        ages.append(age)
    open_df["age_days"], open_df["risk_score"] = ages, scores
    open_df["risk_level"], open_df["reasons"] = levels, reasons
    open_df = open_df.sort_values(["risk_score", "line_total"], ascending=False).reset_index(drop=True)

    buckets = {"0-2 days": 0, "3-5 days": 0, "6-10 days": 0, "11+ days": 0}
    for a in ages:
        buckets["0-2 days" if a <= 2 else "3-5 days" if a <= 5 else "6-10 days" if a <= 10 else "11+ days"] += 1
    summary = {
        "reference_date": ref, "open_orders": int(len(open_df)),
        "levels": {lv: int((open_df.risk_level == lv).sum()) for lv in ("High", "Medium", "Low")},
        "value_at_risk": float(open_df[open_df.risk_level == "High"]["line_total"].sum()) if len(open_df) else 0.0,
        "open_value": float(open_df["line_total"].sum()) if len(open_df) else 0.0,
        "age_buckets": buckets, "high_value_cut": high_value_cut if np.isfinite(high_value_cut) else 0,
        "overdue": int(sum(1 for a, s in zip(ages, open_df.status) if a > AGE_RULES[s][0][0] + 5)) if len(open_df) else 0,
    }
    return open_df, summary


# ---------------------------------------------------------------- insights
def build_insights(d, risk_summary):
    k, items = d["kpi"], []

    def add(level, title, text):
        items.append({"level": level, "title": title, "text": text})

    if not k["total_orders"]:
        return items
    add("info", "Revenue overview",
        f"{k['total_orders']:,} orders generated {peso(k['revenue'])} in net revenue "
        f"(average order value {peso(k['aov'])}). {peso(k['lost_revenue'])} was lost to {k['cancelled']:,} cancellations.")

    cats = d["category"]
    if cats and k["revenue"]:
        top = cats[0]
        top3 = sum(c["revenue"] for c in cats[:3]) / k["revenue"] * 100
        add("info", f"{top['category']} leads sales",
            f"{top['category']} brings in {top['share']:.1f}% of revenue; the top 3 categories together account for {top3:.0f}%.")

    tp = d["top_products"]
    if tp and k["revenue"]:
        top10 = sum(p["revenue"] for p in tp) / k["revenue"] * 100
        add("info", f"Best seller: {tp[0]['product']}",
            f"It earned {peso(tp[0]['revenue'])} from {tp[0]['units']:,} units. The top 10 products make up {top10:.0f}% of revenue.")

    tr = d["trend"]
    done = [(m, v) for m, v, c in zip(tr["months"], tr["revenue"], tr["complete"]) if c and v is not None]
    if len(done) >= 2:
        (m1, v1), (m2, v2) = done[-2], done[-1]
        g = (v2 - v1) / v1 * 100 if v1 else 0
        add("good" if g >= 0 else "warn", "Month-over-month growth",
            f"{month_label(m2)} revenue was {peso(v2)}, {'up' if g >= 0 else 'down'} {abs(g):.1f}% from {month_label(m1)}.")
        best = max(done, key=lambda x: x[1])
        add("info", "Best month", f"{month_label(best[0])} is the strongest complete month at {peso(best[1])}.")
    if tr.get("forecast_info"):
        fi = tr["forecast_info"]
        add("info", "Sales forecast",
            f"A linear trend (R² = {fi['r2']:.2f}) projects {peso(fi['next_value'])} for {month_label(fi['next_month'])} "
            f"and about {peso(fi['next3_total'])} over the next 3 months.")

    wd = [w for w in d["weekday"] if w["orders"]]
    if wd:
        best_d = max(wd, key=lambda w: w["orders"])
        add("info", f"{best_d['name']} is the busiest day",
            f"{best_d['orders']:,} orders were placed on {best_d['name']}s ({best_d['orders'] / k['total_orders'] * 100:.0f}% of all orders) - schedule stock and support accordingly.")

    done_rate = k["delivery_rate"]
    add("good" if done_rate >= 85 else "warn", "Delivery performance",
        f"{done_rate:.1f}% of orders are Delivered ({k['delivered']:,} of {k['total_orders']:,}).")
    add("good" if k["cancel_rate"] <= 8 else "bad", "Cancellation rate",
        f"{k['cancel_rate']:.1f}% of orders were cancelled" +
        (" - within the healthy range (≤ 8%)." if k["cancel_rate"] <= 8 else " - above the 8% warning level; review stock availability and checkout friction."))
    big = [c for c in cats if c["orders"] >= 30]
    if big:
        worst = max(big, key=lambda c: c["cancel_rate"])
        add("warn" if worst["cancel_rate"] > k["cancel_rate"] * 1.2 else "info", "Highest cancellation category",
            f"{worst['category']} has the highest cancellation rate at {worst['cancel_rate']:.1f}% (overall {k['cancel_rate']:.1f}%).")

    if risk_summary and risk_summary.get("open_orders"):
        h = risk_summary["levels"]["High"]
        add("bad" if h else "good", "Order risk",
            f"{h} high-risk and {risk_summary['levels']['Medium']} medium-risk open orders "
            f"(₱{risk_summary['value_at_risk']:,.0f} at stake in high-risk orders). See the Risk page.")

    cu = d["customer_stats"]
    if cu:
        add("info", "Customer loyalty",
            f"{cu['repeat_pct']:.0f}% of customers ordered more than once; the top 10% of customers generate {cu['top10_share']:.0f}% of revenue.")
    return items


# ---------------------------------------------------------------- dashboard builder
WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def build_dashboard(f):
    k = run_query("kpi", f)[0]
    k = {key: (v or 0) for key, v in k.items()}
    total, cancelled = k["total_orders"], k["cancelled"]
    k["open_orders"] = k["pending"] + k["processing"] + k["shipped"]
    k["aov"] = k["revenue"] / (total - cancelled) if total - cancelled > 0 else 0
    k["delivery_rate"] = k["delivered"] / total * 100 if total else 0
    k["cancel_rate"] = cancelled / total * 100 if total else 0
    closed = k["delivered"] + cancelled
    k["success_rate"] = k["delivered"] / closed * 100 if closed else 0

    status_rows = {r["status"]: r for r in run_query("status", f)}
    status = [{"status": s, "orders": status_rows.get(s, {}).get("orders", 0),
               "value": status_rows.get(s, {}).get("order_value", 0) or 0,
               "pct": (status_rows.get(s, {}).get("orders", 0) / total * 100) if total else 0}
              for s in STATUS_ORDER]

    W, P = where_clause(f)
    data_max = get_db().execute(f"SELECT MAX(order_date) FROM orders {W}", P).fetchone()[0]
    trend = build_trend(run_query("monthly", f), data_max)

    sm = run_query("status_month", f)
    sm_months = sorted({r["month"] for r in sm})
    status_month = {"labels": [month_label(m) for m in sm_months],
                    "series": {s: [next((r["orders"] for r in sm if r["month"] == m and r["status"] == s), 0)
                                   for m in sm_months] for s in STATUS_ORDER}}

    top_products = run_query("top_products", f)
    bottom_products = run_query("bottom_products", f)
    categories = run_query("category", f)
    cat_total = sum(c["revenue"] for c in categories) or 1
    for c in categories:
        c["share"] = c["revenue"] / cat_total * 100
        c["aov"] = c["revenue"] / max(1, c["orders"] * (1 - c["cancel_rate"] / 100))

    wd_rows = {r["weekday"]: r for r in run_query("weekday", f)}
    weekday = [{"name": WEEKDAYS[i], "short": WEEKDAYS[i][:3],
                "orders": wd_rows.get(i, {}).get("orders", 0),
                "revenue": wd_rows.get(i, {}).get("revenue", 0) or 0} for i in (1, 2, 3, 4, 5, 6, 0)]

    top_customers = run_query("top_customers", f)

    df = load_df(f)
    net = df[df.status != "Cancelled"]
    order_stats = describe(net["line_total"])
    qty_stats = describe(net["quantity"])
    hist = histogram(net["line_total"].values) if len(net) else {"labels": [], "values": []}

    customer_stats = None
    if len(net):
        per = net.groupby("customer")["line_total"].sum().sort_values(ascending=False)
        cnt = net.groupby("customer").size()
        n_top = max(1, int(round(len(per) * 0.10)))
        customer_stats = {"customers": len(per), "repeat_pct": float((cnt > 1).mean() * 100),
                          "top10_share": float(per.head(n_top).sum() / per.sum() * 100)}

    _, risk_summary = compute_risk(f) if total else (None, {})

    d = {"kpi": k, "status": status, "trend": trend, "status_month": status_month,
         "top_products": top_products, "bottom_products": bottom_products,
         "category": categories, "weekday": weekday, "top_customers": top_customers,
         "order_stats": order_stats, "qty_stats": qty_stats, "hist": hist,
         "customer_stats": customer_stats, "risk": risk_summary}
    d["insights"] = build_insights(d, risk_summary)
    return d


def chart_payload(d):
    """The JSON handed to Chart.js (also served by /api/dashboard)."""
    return {
        "status": {"labels": [s["status"] for s in d["status"]], "values": [s["orders"] for s in d["status"]]},
        "trend": d["trend"],
        "statusMonth": d["status_month"],
        "topProducts": {"labels": [p["product"] for p in d["top_products"]],
                        "values": [p["revenue"] for p in d["top_products"]],
                        "units": [p["units"] for p in d["top_products"]]},
        "category": {"labels": [c["category"] for c in d["category"]],
                     "values": [c["revenue"] for c in d["category"]],
                     "share": [round(c["share"], 1) for c in d["category"]]},
        "weekday": {"labels": [w["short"] for w in d["weekday"]], "names": [w["name"] for w in d["weekday"]],
                    "values": [w["orders"] for w in d["weekday"]]},
        "hist": d["hist"],
        "risk": ({"labels": ["High", "Medium", "Low"],
                  "values": [d["risk"]["levels"][x] for x in ("High", "Medium", "Low")]}
                 if d.get("risk") else None),
    }


def date_bounds():
    row = get_db().execute("SELECT MIN(order_date), MAX(order_date) FROM orders").fetchone()
    return row[0], row[1]


def categories_list():
    return [r[0] for r in get_db().execute("SELECT DISTINCT category FROM orders ORDER BY category")]


def common_ctx(f):
    dmin, dmax = date_bounds()
    return {"f": f, "fq": filter_qs(f), "date_min": dmin, "date_max": dmax,
            "categories": categories_list(), "statuses": STATUS_ORDER,
            "has_data": table_has_data()}


# ---------------------------------------------------------------- routes
@app.route("/")
def dashboard():
    f = get_filters()
    ctx = common_ctx(f)
    if not ctx["has_data"]:
        return render_template("dashboard.html", empty=True, page="dashboard", **ctx)
    d = build_dashboard(f)
    return render_template("dashboard.html", empty=False, page="dashboard", d=d,
                           chart_data=chart_payload(d), **ctx)


@app.route("/api/dashboard")
def api_dashboard():
    """JSON endpoint - lets other systems consume the same analytics (system integration)."""
    f = get_filters()
    d = build_dashboard(f) if table_has_data() else {}
    return jsonify({"filters": f, "kpi": d.get("kpi"), "charts": chart_payload(d) if d else None,
                    "insights": d.get("insights"), "statistics": {
                        "order_value": d.get("order_stats"), "quantity": d.get("qty_stats")}})


SORTABLE = {"order_id": "order_id", "customer": "customer", "product": "product", "category": "category",
            "quantity": "quantity", "price": "price", "total": "line_total", "date": "order_date", "status": "status"}


@app.route("/orders")
def orders():
    f = get_filters()
    ctx = common_ctx(f)
    q = request.args.get("q", "").strip()[:80]
    sort = request.args.get("sort", "date")
    direction = "ASC" if request.args.get("dir") == "asc" else "DESC"
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 20
    W, P = where_clause(f)
    if q:
        W += " AND (order_id LIKE ? OR customer LIKE ? OR product LIKE ?)"
        P = P + [f"%{q}%"] * 3
    db = get_db()
    total = db.execute(f"SELECT COUNT(*) FROM orders {W}", P).fetchone()[0]
    col = SORTABLE.get(sort, "order_date")
    rows = db.execute(f"SELECT * FROM orders {W} ORDER BY {col} {direction}, id DESC LIMIT ? OFFSET ?",
                      P + [per_page, (page - 1) * per_page]).fetchall()
    pages = max(1, -(-total // per_page))
    return render_template("orders.html", page="orders", rows=rows, total=total, q=q, sort=sort,
                           direction=direction.lower(), pg=page, pages=pages, **ctx)


@app.route("/risk")
def risk():
    f = get_filters()
    ctx = common_ctx(f)
    level = request.args.get("level", "")
    df, summary = compute_risk(f) if ctx["has_data"] else (pd.DataFrame(), {})
    shown = df
    if level in ("High", "Medium", "Low") and len(df):
        shown = df[df.risk_level == level]
    rows = shown.head(100).to_dict("records") if len(shown) else []

    cust = run_query("repeat_cancel", {**f, "status": ""}) if ctx["has_data"] else []
    prods = []
    if ctx["has_data"]:
        W, P = where_clause({**f, "status": ""})
        prods = [dict(r) for r in get_db().execute(
            f"""SELECT product, category, COUNT(*) AS orders, SUM(status='Cancelled') AS cancelled,
                       ROUND(100.0*SUM(status='Cancelled')/COUNT(*),1) AS cancel_rate
                FROM orders {W} GROUP BY product, category HAVING COUNT(*) >= {PRODUCT_MIN_ORDERS}
                ORDER BY cancel_rate DESC LIMIT 8""", P).fetchall()]
    risk_chart = {"levels": {"labels": ["High", "Medium", "Low"],
                             "values": [summary["levels"][x] for x in ("High", "Medium", "Low")]},
                  "ages": {"labels": list(summary["age_buckets"].keys()),
                           "values": list(summary["age_buckets"].values())}} if summary else None
    return render_template("risk.html", page="risk", rows=rows, summary=summary, level=level,
                           shown_total=len(shown), cust=cust, prods=prods, risk_chart=risk_chart,
                           rules=AGE_RULES, consts={
                               "hv_pct": HIGH_VALUE_PERCENTILE, "hv_pts": HIGH_VALUE_POINTS,
                               "rc_min": REPEAT_CANCEL_MIN, "rc_pts": REPEAT_CANCEL_POINTS,
                               "pc_factor": PRODUCT_CANCEL_FACTOR, "pc_pts": PRODUCT_CANCEL_POINTS,
                               "high": LEVEL_HIGH, "medium": LEVEL_MEDIUM}, **ctx)


@app.route("/queries")
def queries():
    f = get_filters()
    ctx = common_ctx(f)
    results = []
    if ctx["has_data"]:
        for key, spec in QUERIES.items():
            sql, params = render_query(key, f)
            try:
                rows = [dict(r) for r in get_db().execute(sql, params).fetchall()]
                plan = [r["detail"] for r in get_db().execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()]
            except sqlite3.Error as exc:                       # e.g. old SQLite without window functions
                rows, plan = [], [f"Error: {exc}"]
            results.append({**spec, "shown_sql": sql, "params": params, "rows": rows[:12],
                            "cols": list(rows[0].keys()) if rows else [], "plan": plan, "n": len(rows)})
    return render_template("queries.html", page="queries", results=results, **ctx)


# ---- upload / data management
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        file = request.files.get("file")
        mode = "append" if request.form.get("mode") == "append" else "replace"
        if not file or not file.filename:
            flash("Please choose a CSV file.", "error")
            return redirect(url_for("upload"))
        if not file.filename.lower().endswith(".csv"):
            flash("Only .csv files are supported.", "error")
            return redirect(url_for("upload"))
        try:
            df = pd.read_csv(file, dtype=str, keep_default_na=False)
        except Exception:
            flash("Could not read that file. Make sure it is a valid UTF-8 CSV.", "error")
            return redirect(url_for("upload"))
        rep = import_dataframe(df, file.filename, mode)
        if not rep["ok"]:
            flash(rep["error"], "error")
            return redirect(url_for("upload"))
        flash(report_message(rep), "success")
        return redirect(url_for("dashboard"))
    log = get_db().execute("SELECT * FROM upload_log ORDER BY id DESC LIMIT 8").fetchall()
    n = get_db().execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    return render_template("upload.html", page="upload", log=log, n=n, columns=COLUMNS,
                           sample_exists=os.path.exists(SAMPLE_CSV), **common_ctx(get_filters()))


@app.route("/load-sample", methods=["POST"])
def load_sample():
    if not os.path.exists(SAMPLE_CSV):
        flash("sample_data/orders.csv was not found. Run tools/generate_dataset.py first.", "error")
        return redirect(url_for("upload"))
    rep = import_dataframe(pd.read_csv(SAMPLE_CSV, dtype=str, keep_default_na=False), "orders.csv (sample)", "replace")
    flash(report_message(rep) if rep["ok"] else rep["error"], "success" if rep["ok"] else "error")
    return redirect(url_for("dashboard"))


@app.route("/clear", methods=["POST"])
def clear():
    with get_db() as con:
        con.execute("DELETE FROM orders")
    flash("All order data was removed.", "success")
    return redirect(url_for("upload"))


@app.route("/template.csv")
def template_csv():
    body = ",".join(COLUMNS) + "\nORD00001,John Cruz,Wireless Mouse,Electronics,2,500,2026-10-01,Delivered\n" \
                               "ORD00002,Maria Santos,Cotton T-Shirt,Fashion,1,350,2026-10-02,Pending\n"
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=orders_template.csv"})


@app.route("/sample.csv")
def sample_csv():
    if not os.path.exists(SAMPLE_CSV):
        abort(404)
    return send_file(SAMPLE_CSV, as_attachment=True, download_name="orders_sample.csv")


def csv_response(rows, header, name):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


@app.route("/export/orders.csv")
def export_orders():
    W, P = where_clause(get_filters())
    rows = get_db().execute(f"SELECT {', '.join(COLUMNS)} FROM orders {W} ORDER BY order_date, order_id", P).fetchall()
    return csv_response([tuple(r) for r in rows], COLUMNS, "orders_export.csv")


@app.route("/export/risk.csv")
def export_risk():
    df, _ = compute_risk(get_filters())
    cols = ["order_id", "customer", "product", "category", "status", "order_date", "age_days",
            "line_total", "risk_score", "risk_level", "reasons"]
    return csv_response([] if df.empty else df[cols].values.tolist(), cols, "order_risk_report.csv")


# ---- errors
@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(413)
def handle_error(err):
    msg = {413: "That file is too large (limit 25 MB)."}.get(err.code, getattr(err, "description", "Something went wrong."))
    return render_template("error.html", code=err.code, message=msg, page="", has_data=True), err.code


if __name__ == "__main__":
    app.run(debug=True)
