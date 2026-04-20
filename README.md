# 🪑 Furniture Order Tracking & Audit System (Enhanced)

A production-grade Flask web application to manage furniture orders with full audit logging, user authentication, and real-world workflow tracking.

---

## 📁 Folder Structure

```
furniture_tracker/
├── app.py                      ← Main Flask application (all backend logic)
├── requirements.txt            ← Python dependencies
├── orders.db                   ← SQLite database (auto-created on first run)
└── templates/
    ├── base.html               ← Shared layout (nav, styles, flash messages)
    ├── login.html              ← Login page
    ├── index.html              ← Smart dashboard with stats & filters
    ├── add_order.html          ← Form to create a new order
    ├── view_order.html         ← Single order detail page
    ├── order_history.html      ← Per-order audit timeline
    ├── audit_logs.html         ← Global audit log viewer
    └── trash.html              ← Soft-deleted orders
```

---

## 🚀 How to Run Locally

```bash
# 1. Navigate to project folder
cd furniture_tracker

# 2. (Optional) Create a virtual environment
python -m venv venv
source venv/bin/activate      # Mac/Linux
venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
python app.py

# 5. Open browser
# → http://127.0.0.1:5000
```

---

## 👤 Login Credentials

| Username | Password  | Role  |
|----------|-----------|-------|
| admin    | admin123  | Admin |
| staff    | staff123  | Staff |

---

## ✅ Features

### 🔐 User Authentication
- Login / logout system with session management
- Role display (Admin / Staff) shown in navbar
- All routes protected — unauthenticated users redirected to login
- Audit logs record **who** performed each action

### 📋 Audit Logs (Core Feature)
- Dedicated **Audit Logs** page in the top navigation
- Every action is logged automatically:
  - ✚ Order Created
  - ✎ Status Changed (Old Value → New Value)
  - ✎ Delivery Date Updated
  - 🗑 Order Deleted (soft delete)
  - ↩ Order Restored
  - ⚠ Auto-Delayed (by system)
- Filter logs by: Action Type, User, Date
- Each log entry shows: Order #, Action, Field, Old → New value, Timestamp, User

### 📜 Per-Order History Timeline
- "View History" button on every order row and detail page
- Beautiful vertical timeline showing all events for that order
- Color-coded dots per action type
- Example:
  ```
  [10:00 AM] ✚ Order Created — Ravi Kumar | Sofa x2
  [10:05 AM] ✎ Status Changed — Pending → In Progress
  [10:30 AM] ✎ Delivery Date Updated — 2026-04-30 → 2026-05-15
  ```

### 📊 Smart Dashboard
- **Stat chips:** Total Shown, Pending, In Progress, Completed, Delayed
- **Activity summary:** "X updates today", "X completed today"
- **Near-delivery alert banner:** Highlights orders due within 3 days
- **Recently Modified:** Top 5 recently acted-upon orders shown above the main table
- **Delayed rows** highlighted in red in the order table

### 🔍 Enhanced Filters
- Search by customer name
- Filter by status
- **Date range filter** (From Date / To Date on order_date)
- **Recent activity checkbox** — shows only orders with activity in last 24h

### 🗑 Soft Delete (Instead of permanent delete)
- Orders are never permanently erased — marked as deleted
- Tracked: `deleted_at` timestamp and `deleted_by` username
- **Trash page** shows all soft-deleted orders
- **Restore** button brings orders back with a new audit log entry

### ⚠️ Notifications / Alerts
- Alert banner on dashboard if any order is due within 3 days
- Delayed order rows highlighted in red in the table
- Delivery date shown with ⚠️ icon when status is Delayed
- Flash messages for every action (success/error)

### 📤 Export Feature
- Export **all audit logs** as a CSV file
- Filename includes timestamp: `audit_log_20260420_104523.csv`
- Columns: ID, Order ID, Action, Field, Old Value, New Value, User, Timestamp

### 🔄 Delivery Date Update
- Update delivery date directly from the order detail page
- Change is logged to audit trail with old → new value

---

## 🔄 Order Status Workflow

```
[New Order Created]
       ↓
   Pending   ──→  In Progress  ──→  Completed
       ↓                ↓
   Delayed           Delayed
  (auto if past      (auto if past
  delivery date)     delivery date)
```

---

## 🛠 Tech Stack

- **Backend**: Python + Flask
- **Database**: SQLite (file-based, zero setup)
- **Frontend**: Plain HTML + CSS (DM Sans + DM Serif Display fonts)
- **Templating**: Jinja2

---

## 💡 Key New Concepts

| Concept | Where used |
|---|---|
| `session` | Login state, tracking current user |
| `@login_required` decorator | Protects all routes |
| `audit_logs` table | Stores every action with user + timestamp |
| `is_deleted` column | Soft delete — keeps record in DB |
| `log_action()` helper | Called on every create/update/delete |
| `Response` + `csv` | CSV export of audit logs |
| `request.referrer` | Status update redirects back to origin page |
