# ============================================================
# Furniture Order Tracking System - app.py (Enhanced)
# ============================================================

from flask import (Flask, render_template, request, redirect,
                   url_for, flash, session, Response)
import sqlite3
import csv
import io
from datetime import date, datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = "furniture_tracker_secret_key_2024"
DATABASE = "orders.db"

# ============================================================
# USERS (simple hardcoded auth — upgrade to DB for production)
# ============================================================
USERS = {
    "admin": {"password": "admin123", "role": "Admin"},
    "staff": {"password": "staff123", "role": "Staff"},
}

# ============================================================
# AUTH HELPERS
# ============================================================

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def current_user():
    return session.get("username", "Unknown")

# ============================================================
# DATABASE HELPERS
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    # Orders table (with soft-delete)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT    NOT NULL,
            phone         TEXT    NOT NULL,
            item          TEXT    NOT NULL,
            quantity      INTEGER NOT NULL,
            order_date    TEXT    NOT NULL,
            delivery_date TEXT    NOT NULL,
            status        TEXT    DEFAULT 'Pending',
            is_deleted    INTEGER DEFAULT 0,
            deleted_at    TEXT,
            deleted_by    TEXT
        )
    """)

    # Audit log table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER NOT NULL,
            action     TEXT    NOT NULL,
            field      TEXT,
            old_value  TEXT,
            new_value  TEXT,
            username   TEXT    NOT NULL,
            timestamp  TEXT    NOT NULL
        )
    """)

    conn.commit()

    # Migrate existing orders table — add soft-delete columns if missing
    existing = [row[1] for row in conn.execute("PRAGMA table_info(orders)").fetchall()]
    if "is_deleted" not in existing:
        conn.execute("ALTER TABLE orders ADD COLUMN is_deleted INTEGER DEFAULT 0")
    if "deleted_at" not in existing:
        conn.execute("ALTER TABLE orders ADD COLUMN deleted_at TEXT")
    if "deleted_by" not in existing:
        conn.execute("ALTER TABLE orders ADD COLUMN deleted_by TEXT")
    conn.commit()
    conn.close()


def log_action(conn, order_id, action, username, field=None, old_value=None, new_value=None):
    """Insert a row into audit_logs."""
    conn.execute("""
        INSERT INTO audit_logs (order_id, action, field, old_value, new_value, username, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (order_id, action, field, old_value, new_value, username,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def check_delays(conn):
    today = date.today().isoformat()
    # Fetch orders that WILL become Delayed so we can log them
    rows = conn.execute("""
        SELECT id FROM orders
        WHERE delivery_date < ?
          AND status NOT IN ('Completed', 'Delayed')
          AND is_deleted = 0
    """, (today,)).fetchall()

    for row in rows:
        log_action(conn, row["id"], "Auto-Delayed", "System",
                   field="status", old_value="(previous)", new_value="Delayed")

    conn.execute("""
        UPDATE orders
        SET status = 'Delayed'
        WHERE delivery_date < ?
          AND status NOT IN ('Completed', 'Delayed')
          AND is_deleted = 0
    """, (today,))
    conn.commit()


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = USERS.get(username)
        if user and user["password"] == password:
            session["username"] = username
            session["role"] = user["role"]
            flash(f"Welcome back, {username}! 👋", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/")
@login_required
def index():
    conn = get_db()
    check_delays(conn)

    search        = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()
    date_from     = request.args.get("date_from", "").strip()
    date_to       = request.args.get("date_to", "").strip()
    recent_only   = request.args.get("recent_only", "").strip()

    query  = "SELECT * FROM orders WHERE is_deleted = 0"
    params = []

    if search:
        query += " AND LOWER(customer_name) LIKE LOWER(?)"
        params.append(f"%{search}%")
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    if date_from:
        query += " AND order_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND order_date <= ?"
        params.append(date_to)
    if recent_only:
        cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        # Orders that have audit activity in last 24h
        query += """ AND id IN (
            SELECT DISTINCT order_id FROM audit_logs WHERE timestamp >= ?
        )"""
        params.append(cutoff)

    query += " ORDER BY id DESC"
    orders = conn.execute(query, params).fetchall()

    # --- Smart dashboard stats ---
    today_str = date.today().isoformat()
    today_start = datetime.now().strftime("%Y-%m-%d") + " 00:00:00"

    updates_today = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE timestamp >= ?", (today_start,)
    ).fetchone()[0]

    completed_today = conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='Status Changed' AND new_value='Completed' AND timestamp >= ?",
        (today_start,)
    ).fetchone()[0]

    delayed_count = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE status='Delayed' AND is_deleted=0"
    ).fetchone()[0]

    near_delivery = conn.execute(
        """SELECT * FROM orders
           WHERE is_deleted=0 AND status NOT IN ('Completed','Delayed')
             AND delivery_date BETWEEN ? AND ?
           ORDER BY delivery_date""",
        (today_str, (date.today() + timedelta(days=3)).isoformat())
    ).fetchall()

    recently_modified = conn.execute(
        """SELECT o.*, a.timestamp as last_action, a.action as last_action_type
           FROM orders o
           JOIN (
               SELECT order_id, MAX(timestamp) as timestamp, action
               FROM audit_logs GROUP BY order_id
           ) a ON o.id = a.order_id
           WHERE o.is_deleted = 0
           ORDER BY a.timestamp DESC LIMIT 5"""
    ).fetchall()

    conn.close()

    return render_template("index.html",
                           orders=orders,
                           search=search,
                           status_filter=status_filter,
                           date_from=date_from,
                           date_to=date_to,
                           recent_only=recent_only,
                           updates_today=updates_today,
                           completed_today=completed_today,
                           delayed_count=delayed_count,
                           near_delivery=near_delivery,
                           recently_modified=recently_modified)


# ============================================================
# ADD ORDER
# ============================================================

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_order():
    if request.method == "POST":
        customer_name = request.form["customer_name"].strip()
        phone         = request.form["phone"].strip()
        item          = request.form["item"].strip()
        quantity      = request.form["quantity"]
        order_date    = request.form["order_date"]
        delivery_date = request.form["delivery_date"]

        if not all([customer_name, phone, item, quantity, order_date, delivery_date]):
            flash("All fields are required!", "error")
            return redirect(url_for("add_order"))

        if delivery_date <= order_date:
            flash("Delivery date must be after the order date.", "error")
            return redirect(url_for("add_order"))

        conn = get_db()
        cur = conn.execute("""
            INSERT INTO orders (customer_name, phone, item, quantity, order_date, delivery_date, status)
            VALUES (?, ?, ?, ?, ?, ?, 'Pending')
        """, (customer_name, phone, item, quantity, order_date, delivery_date))
        new_id = cur.lastrowid
        log_action(conn, new_id, "Order Created", current_user(),
                   new_value=f"{customer_name} | {item} x{quantity}")
        conn.commit()
        conn.close()

        flash(f"Order for {customer_name} added successfully!", "success")
        return redirect(url_for("index"))

    today = date.today().isoformat()
    return render_template("add_order.html", today=today)


# ============================================================
# UPDATE STATUS
# ============================================================

@app.route("/update_status/<int:order_id>", methods=["POST"])
@login_required
def update_status(order_id):
    new_status = request.form["status"]
    allowed    = ["Pending", "In Progress", "Completed", "Delayed"]
    if new_status not in allowed:
        flash("Invalid status.", "error")
        return redirect(url_for("index"))

    conn = get_db()
    row = conn.execute("SELECT status FROM orders WHERE id=?", (order_id,)).fetchone()
    if row:
        old_status = row["status"]
        conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
        log_action(conn, order_id, "Status Changed", current_user(),
                   field="status", old_value=old_status, new_value=new_status)
        conn.commit()
        flash(f"Order #{order_id} updated to '{new_status}'.", "success")
    conn.close()

    # Return to previous page (order detail or dashboard)
    referrer = request.referrer or url_for("index")
    return redirect(referrer)


# ============================================================
# UPDATE DELIVERY DATE (from order detail page)
# ============================================================

@app.route("/update_delivery/<int:order_id>", methods=["POST"])
@login_required
def update_delivery(order_id):
    new_date = request.form.get("delivery_date", "").strip()
    if not new_date:
        flash("Invalid date.", "error")
        return redirect(url_for("view_order", order_id=order_id))

    conn = get_db()
    row = conn.execute("SELECT delivery_date FROM orders WHERE id=?", (order_id,)).fetchone()
    if row:
        old_date = row["delivery_date"]
        conn.execute("UPDATE orders SET delivery_date=? WHERE id=?", (new_date, order_id))
        log_action(conn, order_id, "Delivery Date Updated", current_user(),
                   field="delivery_date", old_value=old_date, new_value=new_date)
        conn.commit()
        flash(f"Delivery date updated to {new_date}.", "success")
    conn.close()
    return redirect(url_for("view_order", order_id=order_id))


# ============================================================
# SOFT DELETE
# ============================================================

@app.route("/delete/<int:order_id>", methods=["POST"])
@login_required
def delete_order(order_id):
    conn = get_db()
    conn.execute("""
        UPDATE orders SET is_deleted=1, deleted_at=?, deleted_by=?
        WHERE id=?
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), current_user(), order_id))
    log_action(conn, order_id, "Order Deleted", current_user())
    conn.commit()
    conn.close()
    flash(f"Order #{order_id} moved to trash.", "success")
    return redirect(url_for("index"))


# ============================================================
# RESTORE (soft-deleted)
# ============================================================

@app.route("/restore/<int:order_id>", methods=["POST"])
@login_required
def restore_order(order_id):
    conn = get_db()
    conn.execute("UPDATE orders SET is_deleted=0, deleted_at=NULL, deleted_by=NULL WHERE id=?",
                 (order_id,))
    log_action(conn, order_id, "Order Restored", current_user())
    conn.commit()
    conn.close()
    flash(f"Order #{order_id} has been restored.", "success")
    return redirect(url_for("trash"))


# ============================================================
# TRASH (soft-deleted orders)
# ============================================================

@app.route("/trash")
@login_required
def trash():
    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM orders WHERE is_deleted=1 ORDER BY deleted_at DESC"
    ).fetchall()
    conn.close()
    return render_template("trash.html", orders=orders)


# ============================================================
# VIEW ORDER DETAIL
# ============================================================

@app.route("/order/<int:order_id>")
@login_required
def view_order(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    if order is None:
        flash("Order not found.", "error")
        return redirect(url_for("index"))
    return render_template("view_order.html", order=order)


# ============================================================
# ORDER HISTORY (timeline)
# ============================================================

@app.route("/order/<int:order_id>/history")
@login_required
def order_history(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    logs  = conn.execute(
        "SELECT * FROM audit_logs WHERE order_id=? ORDER BY timestamp ASC", (order_id,)
    ).fetchall()
    conn.close()
    if order is None:
        flash("Order not found.", "error")
        return redirect(url_for("index"))
    return render_template("order_history.html", order=order, logs=logs)


# ============================================================
# GLOBAL AUDIT LOGS
# ============================================================

@app.route("/audit")
@login_required
def audit_logs():
    conn = get_db()
    action_filter = request.args.get("action", "").strip()
    user_filter   = request.args.get("user", "").strip()
    date_filter   = request.args.get("date", "").strip()

    query  = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    if action_filter:
        query += " AND action=?"
        params.append(action_filter)
    if user_filter:
        query += " AND username=?"
        params.append(user_filter)
    if date_filter:
        query += " AND timestamp LIKE ?"
        params.append(f"{date_filter}%")

    query += " ORDER BY timestamp DESC"
    logs  = conn.execute(query, params).fetchall()

    actions  = conn.execute("SELECT DISTINCT action FROM audit_logs").fetchall()
    userlist = conn.execute("SELECT DISTINCT username FROM audit_logs").fetchall()
    conn.close()

    return render_template("audit_logs.html",
                           logs=logs,
                           actions=actions,
                           userlist=userlist,
                           action_filter=action_filter,
                           user_filter=user_filter,
                           date_filter=date_filter)


# ============================================================
# EXPORT AUDIT LOGS AS CSV
# ============================================================

@app.route("/audit/export")
@login_required
def export_audit():
    conn = get_db()
    logs = conn.execute(
        "SELECT * FROM audit_logs ORDER BY timestamp DESC"
    ).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Order ID", "Action", "Field", "Old Value", "New Value", "User", "Timestamp"])
    for log in logs:
        writer.writerow([log["id"], log["order_id"], log["action"],
                         log["field"] or "", log["old_value"] or "",
                         log["new_value"] or "", log["username"], log["timestamp"]])

    output.seek(0)
    filename = f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    init_db()
    print("✅ Database initialized.")
    print("🚀 Furniture Order Tracking System — Enhanced Edition")
    print("👉 Open: http://127.0.0.1:5000")
    print("👤 Login: admin / admin123  or  staff / staff123")
    app.run(debug=True)
