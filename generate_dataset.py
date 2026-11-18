"""Generate a realistic e-commerce order dataset (orders.csv).

Run:  python tools/generate_dataset.py [rows]
Output: sample_data/orders.csv  (order_id, customer, product, category,
        quantity, price, order_date, status)
Seeded, so everyone gets the same file.
"""
import csv, os, random, sys
from datetime import date, timedelta

random.seed(2026)
ROWS = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
START, END = date(2026, 1, 1), date(2026, 11, 15)

PRODUCTS = {
    "Electronics": [("Wireless Mouse", 500), ("Bluetooth Earbuds", 1450), ("Power Bank 10000mAh", 899),
                    ("USB-C Charger 65W", 1150), ("Mechanical Keyboard", 2300), ("Smart Watch", 1899),
                    ("Portable Speaker", 1350), ("Webcam 1080p", 1250)],
    "Fashion": [("Cotton T-Shirt", 350), ("Denim Jeans", 1100), ("Running Shoes", 2199),
                ("Canvas Sneakers", 1299), ("Hoodie Jacket", 950), ("Leather Belt", 450)],
    "Home & Living": [("LED Desk Lamp", 649), ("Electric Kettle", 780), ("Bed Sheet Set", 1250),
                      ("Storage Organizer", 420), ("Air Fryer 4L", 3200), ("Wall Clock", 380)],
    "Beauty & Health": [("Vitamin C Serum", 599), ("Sunscreen SPF50", 420), ("Facial Cleanser", 310),
                        ("Hair Dryer", 1100), ("Multivitamins 60s", 540)],
    "Groceries": [("Premium Coffee Beans 500g", 650), ("Organic Honey 350ml", 390),
                  ("Mixed Nuts 1kg", 780), ("Olive Oil 1L", 720)],
    "Books & Stationery": [("Notebook Set (5pcs)", 250), ("Gel Pen Pack", 120),
                           ("Programming Book", 1650), ("Planner 2026", 380)],
    "Sports & Outdoors": [("Yoga Mat", 650), ("Dumbbell Set 10kg", 1450), ("Water Bottle 1L", 399),
                          ("Hiking Backpack", 1799), ("Jump Rope", 220)],
    "Toys & Games": [("Building Blocks 500pcs", 899), ("Board Game Classic", 1150),
                     ("RC Car", 1399), ("Puzzle 1000pcs", 480)],
}
# popularity of each category (Electronics and Fashion lead)
CAT_W = {"Electronics": 24, "Fashion": 19, "Home & Living": 14, "Beauty & Health": 12,
         "Groceries": 10, "Books & Stationery": 7, "Sports & Outdoors": 9, "Toys & Games": 5}

FIRST = ["Juan", "Maria", "Jose", "Ana", "Mark", "Angel", "John", "Kristine", "Carlo", "Jasmine", "Paolo",
         "Bea", "Miguel", "Sofia", "Rey", "Liza", "Daniel", "Camille", "Joshua", "Nicole", "Ramon",
         "Trisha", "Allan", "Grace", "Patrick", "Dianne", "Jericho", "Hazel", "Noel", "Rhea", "Vincent",
         "Mika", "Francis", "Aileen", "Gabriel", "Irene", "Dennis", "Katrina", "Elmer", "Joy"]
LAST = ["Cruz", "Santos", "Reyes", "Garcia", "Dela Cruz", "Bautista", "Ramos", "Mendoza", "Torres",
        "Flores", "Aquino", "Villanueva", "Castillo", "Navarro", "Domingo", "Salazar", "Pascual",
        "Soriano", "Manalo", "Lopez", "Tolentino", "Valdez", "Aguilar", "Castro", "Rivera"]

names = set()
while len(names) < 240:
    names.add(f"{random.choice(FIRST)} {random.choice(LAST)}")
CUSTOMERS = sorted(names)
# Pareto-style loyalty: a few customers order far more often
CUST_W = [random.paretovariate(1.6) for _ in CUSTOMERS]

# date weights: growth trend + weekend lift + sale days (e.g. 3.3, 5.5, 9.9, 10.10, 11.11)
days = [START + timedelta(d) for d in range((END - START).days + 1)]
SALE = {(3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8), (9, 9), (10, 10), (11, 11)}
def day_weight(d):
    w = 1.0 + 0.9 * (d - START).days / len(days)         # steady growth
    if d.weekday() >= 5: w *= 1.25                       # weekend lift
    if (d.month, d.day) in SALE: w *= 3.2                # double-day sales
    if d.month == 12: w *= 1.8
    if d.month in (2,) : w *= 0.9
    return w
DAY_W = [day_weight(d) for d in days]

def pick_status(d):
    age = (END - d).days
    r = random.random()
    if age <= 1:
        return random.choices(["Pending", "Processing", "Shipped"], [60, 30, 10])[0] if r > 0.03 else "Cancelled"
    if age <= 4:
        return random.choices(["Processing", "Shipped", "Delivered", "Pending", "Cancelled"], [25, 35, 25, 7, 8])[0]
    if age <= 8:
        return random.choices(["Shipped", "Delivered", "Cancelled", "Pending"], [20, 66, 11, 3])[0]
    # older orders: mostly delivered; tiny number of stuck orders (anomalies for risk detection)
    return random.choices(["Delivered", "Cancelled", "Pending", "Processing", "Shipped"],
                          [91.0, 7.0, 0.7, 0.6, 0.7])[0]

rows = []
for i in range(ROWS):
    d = random.choices(days, DAY_W)[0]
    cat = random.choices(list(CAT_W), list(CAT_W.values()))[0]
    # within a category, a few products are bestsellers
    items = PRODUCTS[cat]
    pw = [1 / (k + 1) ** 0.8 for k in range(len(items))]
    prod, base = random.choices(items, pw)[0]
    price = base if random.random() > 0.15 else round(base * random.choice([0.9, 0.85, 1.05]))  # promos
    qty = random.choices([1, 2, 3, 4, 5], [58, 24, 10, 5, 3])[0]
    if cat in ("Groceries", "Books & Stationery") and random.random() < 0.3: qty += random.randint(1, 3)
    cust = random.choices(CUSTOMERS, CUST_W)[0]
    rows.append([d, cust, prod, cat, qty, price, pick_status(d)])

rows.sort(key=lambda r: r[0])
os.makedirs("sample_data", exist_ok=True)
with open("sample_data/orders.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["order_id", "customer", "product", "category", "quantity", "price", "order_date", "status"])
    for n, (d, c, p, cat, q, pr, st) in enumerate(rows, 1):
        w.writerow([f"ORD{n:05d}", c, p, cat, q, pr, d.isoformat(), st])
print(f"Wrote {len(rows)} orders to sample_data/orders.csv")
