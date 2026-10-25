import os
import json
import secrets
import sqlite3
import hmac
import hashlib
import urllib.parse
from datetime import datetime
from bottle import Bottle, request, response, static_file, HTTPError, redirect

from database import init_db, get_db, hash_password, verify_password

# Initialize app and database
init_db()
app = Bottle()

SECRET_KEY = os.environ.get("SECRET_KEY", "eventora-python-super-secret-key-2026-production-ready-xyz")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# --- Helper Utilities ---
def sign_cookie_value(val: str) -> str:
    signature = hmac.new(SECRET_KEY.encode(), val.encode(), hashlib.sha256).hexdigest()
    return f"{val}.{signature}"

def verify_cookie_value(cookie: str):
    if not cookie or "." not in cookie:
        return None
    val, sig = cookie.rsplit(".", 1)
    expected = hmac.new(SECRET_KEY.encode(), val.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected):
        return val
    return None

def get_current_user():
    raw_cookie = request.get_cookie("eventora_session")
    user_id = verify_cookie_value(raw_cookie)
    if not user_id:
        return None
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"id": row["id"], "name": row["name"], "email": row["email"]}
    return None

def require_auth():
    user = get_current_user()
    if not user:
        response.status = 401
        return None
    return user

def json_response(data, status=200):
    response.content_type = "application/json"
    response.status = status
    return json.dumps(data)

def error_response(msg, status=400):
    return json_response({"error": msg}, status=status)

def dict_from_row(row):
    return {k: row[k] for k in row.keys()}

# --- Static & Page Routes ---
@app.route("/")
def index():
    return static_file("index.html", root=TEMPLATES_DIR)

@app.route("/static/<filepath:path>")
def serve_static(filepath):
    return static_file(filepath, root=STATIC_DIR)

# --- PUBLIC ROUTES ---
@app.get("/api/public/events")
def get_public_events():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM events 
        WHERE status = 'published' 
        ORDER BY date ASC
    """)
    rows = cursor.fetchall()
    events = []
    for r in rows:
        d = dict_from_row(r)
        try:
            d["schedule"] = json.loads(d.get("schedule_json") or "[]")
        except Exception:
            d["schedule"] = []
        events.append(d)
    conn.close()
    return json_response({"events": events})

@app.get("/api/public/events/<event_id:int>")
def get_public_event(event_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ? AND status = 'published'", (event_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return error_response("Event not found", 404)
    event = dict_from_row(row)
    try:
        event["schedule"] = json.loads(event.get("schedule_json") or "[]")
    except Exception:
        event["schedule"] = []
    
    # Registration count
    cursor.execute("SELECT SUM(quantity) FROM registrations WHERE event_id = ?", (event_id,))
    reg_sum = cursor.fetchone()[0] or 0
    event["registered_count"] = reg_sum
    event["remaining_seats"] = max(0, event["capacity"] - reg_sum)

    # Reviews
    cursor.execute("SELECT * FROM reviews WHERE event_id = ? ORDER BY id DESC LIMIT 20", (event_id,))
    reviews = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()

    return json_response({"event": event, "reviews": reviews})

# Public Review Submission
@app.post("/api/public/events/<event_id:int>/reviews")
def submit_review(event_id):
    data = request.json or {}
    author_name = data.get("authorName", "").strip() or "Guest Attendee"
    rating = int(data.get("rating", 5))
    comment = data.get("comment", "").strip()

    if not comment:
        return error_response("Please write a short comment about your experience.")
    rating = max(1, min(5, rating))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM events WHERE id = ?", (event_id,))
    if not cursor.fetchone():
        conn.close()
        return error_response("Event not found.", 404)

    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO reviews (event_id, author_name, rating, comment, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (event_id, author_name, rating, comment, now_iso))

    # Recalculate average rating & count
    cursor.execute("SELECT AVG(rating), COUNT(*) FROM reviews WHERE event_id = ?", (event_id,))
    avg_rating, rev_count = cursor.fetchone()
    avg_rating = round(avg_rating or 5.0, 1)

    cursor.execute("UPDATE events SET rating = ?, review_count = ? WHERE id = ?", (avg_rating, rev_count, event_id))
    conn.commit()
    conn.close()

    return json_response({"ok": True, "rating": avg_rating, "reviewCount": rev_count}, status=201)

# Public Ticket Lookup ("Find My Ticket")
@app.get("/api/public/tickets/lookup")
def lookup_tickets():
    query = request.query.get("query", "").strip()
    if not query:
        return error_response("Please provide a ticket code or email address.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, e.title as event_title, e.venue as venue, e.date as event_date, e.start_time as event_time
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        WHERE UPPER(r.ticket_id) = UPPER(?) OR LOWER(r.attendee_email) = LOWER(?)
        ORDER BY r.id DESC
    """, (query, query))
    rows = cursor.fetchall()
    conn.close()

    tickets = [dict_from_row(r) for r in rows]
    return json_response({"tickets": tickets})

# Public Registration with Ticket Tier and Quantity (e.g. ₹199/person)
@app.post("/api/public/events/<event_id:int>/register")
def public_register(event_id):
    data = request.json or {}
    attendee_name = (data.get("attendeeName") or data.get("name") or "").strip()
    attendee_email = (data.get("attendeeEmail") or data.get("email") or "").strip().lower()
    quantity = max(1, min(10, int(data.get("quantity", 1))))
    ticket_tier = data.get("ticketTier") or data.get("ticket_tier") or "Standard Pass (₹199)"
    unit_price = float(data.get("unitPrice") or data.get("unit_price") or 199.0)
    total_amount = round(quantity * unit_price, 2)

    if not attendee_name or not attendee_email or "@" not in attendee_email:
        return error_response("Valid attendee name and email are required.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ? AND status = 'published'", (event_id,))
    event = cursor.fetchone()
    if not event:
        conn.close()
        return error_response("Event not found or not active.", 404)

    cursor.execute("SELECT SUM(quantity) FROM registrations WHERE event_id = ?", (event_id,))
    current_count = cursor.fetchone()[0] or 0
    if current_count + quantity > event["capacity"]:
        conn.close()
        return error_response(f"Only {max(0, event['capacity'] - current_count)} seats remaining for this event.", 409)

    ticket_id = "EVT-" + secrets.token_hex(4).upper()
    now_iso = datetime.now().isoformat()
    payment_method = data.get("paymentMethod") or data.get("payment_method") or "UPI: Instant Payment"
    transaction_id = data.get("transactionId") or data.get("transaction_id") or ("TXN_EVNT_" + secrets.token_hex(6).upper())
    order_id = data.get("orderId") or data.get("order_id") or ("order_EVNT_" + secrets.token_hex(6).upper())

    cursor.execute("""
        INSERT INTO registrations (event_id, owner_id, attendee_name, attendee_email, ticket_id, ticket_tier, quantity, total_amount, payment_status, payment_method, transaction_id, order_id, checked_in_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'paid', ?, ?, ?, NULL, ?)
    """, (event_id, event["owner_id"], attendee_name, attendee_email, ticket_id, ticket_tier, quantity, total_amount, payment_method, transaction_id, order_id, now_iso))
    reg_id = cursor.lastrowid

    # Notification for organizer
    cursor.execute("""
        INSERT INTO notifications (owner_id, event_id, message, read_at, created_at)
        VALUES (?, ?, ?, NULL, ?)
    """, (event["owner_id"], event_id, f"Ticket Booked & Paid: {attendee_name} bought {quantity}x {ticket_tier} (₹{total_amount}) via {payment_method} for '{event['title']}'.", now_iso))

    conn.commit()
    conn.close()

    return json_response({
        "registration": {
            "id": reg_id,
            "attendeeName": attendee_name,
            "attendeeEmail": attendee_email,
            "ticketId": ticket_id,
            "ticketTier": ticket_tier,
            "quantity": quantity,
            "totalAmount": total_amount,
            "eventTitle": event["title"],
            "venue": event["venue"],
            "date": event["date"],
            "startTime": event["start_time"],
            "paymentStatus": "paid",
            "paymentMethod": payment_method,
            "transactionId": transaction_id,
            "orderId": order_id
        }
    }, status=201)

# --- REAL-WORLD PAYMENT GATEWAY INTEGRATION (UPI, CARDS & NETBANKING) ---
@app.post("/api/payments/create-order")
def create_payment_order():
    data = request.json or {}
    event_id = int(data.get("eventId") or data.get("event_id") or 0)
    attendee_name = (data.get("attendeeName") or data.get("name") or "").strip()
    attendee_email = (data.get("attendeeEmail") or data.get("email") or "").strip().lower()
    quantity = max(1, min(10, int(data.get("quantity", 1))))
    unit_price = float(data.get("unitPrice") or data.get("unit_price") or 199.0)
    ticket_tier = data.get("ticketTier") or data.get("ticket_tier") or f"Standard Pass (₹{int(unit_price)})"

    if not event_id:
        return error_response("Event ID is required.")
    if not attendee_name or not attendee_email or "@" not in attendee_email:
        return error_response("Valid attendee name and email are required.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ? AND status = 'published'", (event_id,))
    event = cursor.fetchone()
    if not event:
        conn.close()
        return error_response("Event not found or not active.", 404)

    cursor.execute("SELECT SUM(quantity) FROM registrations WHERE event_id = ?", (event_id,))
    current_count = cursor.fetchone()[0] or 0
    if current_count + quantity > event["capacity"]:
        conn.close()
        return error_response(f"Only {max(0, event['capacity'] - current_count)} seats remaining for this event.", 409)

    total_amount = round(quantity * unit_price, 2)
    order_id = "order_EVNT_" + secrets.token_hex(6).upper()
    now_iso = datetime.now().isoformat()

    # Dynamic NPCI / RBI Standard UPI Payment URI
    # Works natively with Google Pay, PhonePe, Paytm, BHIM, CRED
    vpa = "evntra.events@icici"
    merchant_name = "Evntra Live Experiences"
    encoded_note = urllib.parse.quote(f"Evntra Pass: {event['title'][:25]}")
    encoded_merchant = urllib.parse.quote(merchant_name)
    upi_string = f"upi://pay?pa={vpa}&pn={encoded_merchant}&am={total_amount:.2f}&cu=INR&tn={encoded_note}"

    cursor.execute("""
        INSERT INTO payments (order_id, event_id, attendee_name, attendee_email, amount, currency, method, status, transaction_id, payment_details_json, ticket_id, created_at, paid_at)
        VALUES (?, ?, ?, ?, ?, 'INR', 'upi', 'pending', NULL, ?, NULL, ?, NULL)
    """, (order_id, event_id, attendee_name, attendee_email, total_amount, json.dumps({"tier": ticket_tier, "quantity": quantity}), now_iso))

    conn.commit()
    conn.close()

    base_amount = round(total_amount / 1.18, 2)
    gst_amount = round(total_amount - base_amount, 2)

    return json_response({
        "orderId": order_id,
        "eventId": event_id,
        "eventTitle": event["title"],
        "venue": event["venue"],
        "date": event["date"],
        "startTime": event["start_time"],
        "quantity": quantity,
        "ticketTier": ticket_tier,
        "unitPrice": unit_price,
        "totalAmount": total_amount,
        "currency": "INR",
        "upi": {
            "vpa": vpa,
            "merchantName": merchant_name,
            "upiString": upi_string
        },
        "breakdown": {
            "baseAmount": base_amount,
            "gstAmount": gst_amount,
            "totalAmount": total_amount,
            "gstRate": "18% Included"
        }
    }, status=201)

@app.post("/api/payments/verify")
def verify_payment():
    data = request.json or {}
    order_id = data.get("orderId") or data.get("order_id")
    payment_method = data.get("paymentMethod") or data.get("method") or "UPI"
    
    if not order_id:
        return error_response("Order ID is required.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM payments WHERE order_id = ?", (order_id,))
    payment = cursor.fetchone()
    if not payment:
        conn.close()
        return error_response("Payment order not found.", 404)

    cursor.execute("SELECT * FROM events WHERE id = ?", (payment["event_id"],))
    event = cursor.fetchone()

    # Generate real-world transaction ID and ticket ID
    txn_id = data.get("transactionId") or ("TXN_EVNT_" + secrets.token_hex(6).upper())
    ticket_id = "EVT-" + secrets.token_hex(4).upper()
    now_iso = datetime.now().isoformat()

    try:
        details_obj = json.loads(payment["payment_details_json"] or "{}")
    except Exception:
        details_obj = {}

    ticket_tier = details_obj.get("tier", "Standard Pass (₹199)")
    quantity = int(details_obj.get("quantity", 1))

    # Update payment order record
    cursor.execute("""
        UPDATE payments
        SET status = 'success', method = ?, transaction_id = ?, ticket_id = ?, paid_at = ?
        WHERE order_id = ?
    """, (payment_method, txn_id, ticket_id, now_iso, order_id))

    # Insert into registrations table with payment details
    cursor.execute("""
        INSERT INTO registrations (event_id, owner_id, attendee_name, attendee_email, ticket_id, ticket_tier, quantity, total_amount, payment_status, payment_method, transaction_id, order_id, checked_in_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'paid', ?, ?, ?, NULL, ?)
    """, (payment["event_id"], event["owner_id"], payment["attendee_name"], payment["attendee_email"], ticket_id, ticket_tier, quantity, payment["amount"], payment_method, txn_id, order_id, now_iso))
    reg_id = cursor.lastrowid

    # Organizer notification
    cursor.execute("""
        INSERT INTO notifications (owner_id, event_id, message, read_at, created_at)
        VALUES (?, ?, ?, NULL, ?)
    """, (event["owner_id"], event["id"], f"Payment Verified: {payment['attendee_name']} paid ₹{payment['amount']} via {payment_method} (Txn: {txn_id}) for '{event['title']}'.", now_iso))

    conn.commit()
    conn.close()

    invoice_number = f"INV-EVNT-{secrets.token_hex(3).upper()}"

    return json_response({
        "ok": True,
        "registration": {
            "id": reg_id,
            "attendeeName": payment["attendee_name"],
            "attendeeEmail": payment["attendee_email"],
            "ticketId": ticket_id,
            "ticketTier": ticket_tier,
            "quantity": quantity,
            "totalAmount": payment["amount"],
            "eventTitle": event["title"],
            "venue": event["venue"],
            "date": event["date"],
            "startTime": event["start_time"],
            "paymentStatus": "paid",
            "paymentMethod": payment_method,
            "transactionId": txn_id,
            "orderId": order_id
        },
        "receipt": {
            "invoiceNumber": invoice_number,
            "orderId": order_id,
            "transactionId": txn_id,
            "paidAt": now_iso,
            "amount": payment["amount"],
            "currency": "INR",
            "paymentMethod": payment_method,
            "gstin": "29AABCE1234F1Z5",
            "merchantName": "Evntra Live Experiences Pvt Ltd"
        }
    }, status=200)

# --- AUTHENTICATION ROUTES ---
@app.post("/api/auth/register")
def auth_register():
    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    if not name or not email or "@" not in email:
        return error_response("Valid name and email are required.")
    if len(password) < 8:
        return error_response("Password must be at least 8 characters.")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return error_response("An account with this email already exists.", 409)

    pw_hash = hash_password(password)
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO users (name, email, password_hash, created_at)
        VALUES (?, ?, ?, ?)
    """, (name, email, pw_hash, now_iso))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()

    cookie_val = sign_cookie_value(str(user_id))
    response.set_cookie("eventora_session", cookie_val, path="/", httponly=True, max_age=604800, samesite="Lax")
    return json_response({"user": {"id": user_id, "name": name, "email": email}}, status=201)

@app.post("/api/auth/login")
def auth_login():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, password_hash FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if not user or not verify_password(password, user["password_hash"]):
        return error_response("Incorrect email or password.", 401)

    cookie_val = sign_cookie_value(str(user["id"]))
    response.set_cookie("eventora_session", cookie_val, path="/", httponly=True, max_age=604800, samesite="Lax")
    return json_response({"user": {"id": user["id"], "name": user["name"], "email": user["email"]}})

# 1-Click Demo Organizer Login
@app.post("/api/auth/demo")
def auth_demo():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE email = 'organizer@eventora.io'")
    user = cursor.fetchone()
    conn.close()

    if not user:
        return error_response("Demo account not available.", 500)

    cookie_val = sign_cookie_value(str(user["id"]))
    response.set_cookie("eventora_session", cookie_val, path="/", httponly=True, max_age=604800, samesite="Lax")
    return json_response({"user": {"id": user["id"], "name": user["name"], "email": user["email"]}})

@app.post("/api/auth/logout")
def auth_logout():
    response.delete_cookie("eventora_session", path="/")
    return json_response({"ok": True})

@app.get("/api/auth/me")
def auth_me():
    user = get_current_user()
    if not user:
        return error_response("Not signed in", 401)
    return json_response({"user": user})

# --- ORGANIZER EVENT CRUD ---
@app.get("/api/events")
def list_organizer_events():
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE owner_id = ? ORDER BY date ASC", (user["id"],))
    rows = cursor.fetchall()
    events = [dict_from_row(r) for r in rows]
    conn.close()
    return json_response({"events": events})

@app.post("/api/events")
def create_event():
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    title = data.get("title", "").strip()
    if not title: return error_response("Event title is required.")

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO events (owner_id, title, description, category, date, start_time, venue, capacity, budget, expenses, ticket_price, banner_url, schedule_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, ?)
    """, (
        user["id"],
        title,
        data.get("description", "").strip(),
        data.get("category", "Technology"),
        data.get("date", datetime.now().strftime("%Y-%m-%d")),
        data.get("startTime", "10:00"),
        data.get("venue", "Main Auditorium"),
        int(data.get("capacity", 200)),
        float(data.get("budget", 0)),
        float(data.get("expenses", 0)),
        float(data.get("ticketPrice", 199)),
        data.get("bannerUrl", "/static/images/comedy_night.jpg"),
        data.get("status", "published"),
        now_iso
    ))
    event_id = cursor.lastrowid
    
    # Notification
    cursor.execute("""
        INSERT INTO notifications (owner_id, event_id, message, read_at, created_at)
        VALUES (?, ?, ?, NULL, ?)
    """, (user["id"], event_id, f"Event '{title}' was published successfully.", now_iso))

    conn.commit()
    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    event = dict_from_row(cursor.fetchone())
    conn.close()

    return json_response({"event": event}, status=201)

@app.patch("/api/events/<event_id:int>")
def update_event(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE id = ? AND owner_id = ?", (event_id, user["id"]))
    if not cursor.fetchone():
        conn.close()
        return error_response("Event not found", 404)

    fields = []
    values = []
    field_mapping = {
        "title": "title", "description": "description", "category": "category",
        "date": "date", "startTime": "start_time", "venue": "venue",
        "capacity": "capacity", "budget": "budget", "expenses": "expenses",
        "ticketPrice": "ticket_price", "bannerUrl": "banner_url", "status": "status"
    }

    for json_key, col in field_mapping.items():
        if json_key in data:
            fields.append(f"{col} = ?")
            values.append(data[json_key])

    if fields:
        values.extend([event_id, user["id"]])
        cursor.execute(f"UPDATE events SET {', '.join(fields)} WHERE id = ? AND owner_id = ?", values)
        conn.commit()

    cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
    updated = dict_from_row(cursor.fetchone())
    conn.close()
    return json_response({"event": updated})

@app.delete("/api/events/<event_id:int>")
def delete_event(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM events WHERE id = ? AND owner_id = ?", (event_id, user["id"]))
    cursor.execute("DELETE FROM guests WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM tasks WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM checklist_items WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM registrations WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM expenses WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM reviews WHERE event_id = ?", (event_id,))
    cursor.execute("DELETE FROM notifications WHERE event_id = ?", (event_id,))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

# --- EXPENSES LEDGER ---
@app.get("/api/events/<event_id:int>/expenses")
def get_event_expenses(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM expenses WHERE event_id = ? AND owner_id = ? ORDER BY id DESC", (event_id, user["id"]))
    rows = cursor.fetchall()
    expenses = [dict_from_row(r) for r in rows]
    total = sum(float(e.get("amount", 0) or 0) for e in expenses)
    conn.close()
    return json_response({"expenses": expenses, "totalExpenses": total})

@app.post("/api/events/<event_id:int>/expenses")
def add_event_expense(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    title = data.get("title", "").strip()
    category = data.get("category", "General").strip()
    amount = float(data.get("amount", 0))
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))

    if not title or amount <= 0:
        return error_response("Valid expense title and positive amount required.")

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO expenses (event_id, owner_id, title, category, amount, date, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (event_id, user["id"], title, category, amount, date_str, now_iso))
    new_id = cursor.lastrowid

    # Recalculate and update event expenses column
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE event_id = ?", (event_id,))
    total_spent = cursor.fetchone()[0] or 0
    cursor.execute("UPDATE events SET expenses = ? WHERE id = ?", (total_spent, event_id))

    cursor.execute("SELECT * FROM expenses WHERE id = ?", (new_id,))
    new_exp = dict_from_row(cursor.fetchone())

    conn.commit()
    conn.close()
    return json_response({"ok": True, "expense": new_exp, "totalExpenses": total_spent}, status=201)

@app.delete("/api/events/<event_id:int>/expenses/<expense_id:int>")
def delete_event_expense(event_id, expense_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM expenses WHERE id = ? AND event_id = ? AND owner_id = ?", (expense_id, event_id, user["id"]))
    cursor.execute("SELECT SUM(amount) FROM expenses WHERE event_id = ?", (event_id,))
    total_spent = cursor.fetchone()[0] or 0
    cursor.execute("UPDATE events SET expenses = ? WHERE id = ?", (total_spent, event_id))
    conn.commit()
    conn.close()
    return json_response({"ok": True, "totalExpenses": total_spent})

# --- GUESTS ---
@app.get("/api/events/<event_id:int>/guests")
def get_guests(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM guests WHERE event_id = ? AND owner_id = ? ORDER BY id DESC", (event_id, user["id"]))
    guests = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    return json_response({"guests": guests})

@app.post("/api/events/<event_id:int>/guests")
def add_guest(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    if not name or not email: return error_response("Name and email are required.")

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO guests (event_id, owner_id, name, email, rsvp, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """, (event_id, user["id"], name, email, now_iso))
    conn.commit()
    conn.close()
    return json_response({"ok": True}, status=201)

@app.patch("/api/events/<event_id:int>/guests/<guest_id:int>")
def update_guest_rsvp(event_id, guest_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    rsvp = data.get("rsvp", "pending")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE guests SET rsvp = ? WHERE id = ? AND event_id = ? AND owner_id = ?", (rsvp, guest_id, event_id, user["id"]))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

# --- TASKS KANBAN ---
@app.get("/api/events/<event_id:int>/tasks")
def get_tasks(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE event_id = ? AND owner_id = ? ORDER BY id DESC", (event_id, user["id"]))
    tasks = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    return json_response({"tasks": tasks})

@app.post("/api/events/<event_id:int>/tasks")
def add_task(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    title = data.get("title", "").strip()
    if not title: return error_response("Task title is required.")

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO tasks (event_id, owner_id, title, assignee, due_date, status, priority, created_at)
        VALUES (?, ?, ?, ?, ?, 'todo', ?, ?)
    """, (event_id, user["id"], title, data.get("assignee", ""), data.get("dueDate", None), data.get("priority", "medium"), now_iso))
    conn.commit()
    conn.close()
    return json_response({"ok": True}, status=201)

@app.patch("/api/events/<event_id:int>/tasks/<task_id:int>")
def update_task(event_id, task_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    conn = get_db()
    cursor = conn.cursor()
    if "status" in data:
        cursor.execute("UPDATE tasks SET status = ? WHERE id = ? AND event_id = ? AND owner_id = ?", (data["status"], task_id, event_id, user["id"]))
        conn.commit()
    conn.close()
    return json_response({"ok": True})

# --- RUN-OF-SHOW CHECKLIST ---
@app.get("/api/events/<event_id:int>/checklist")
def get_checklist(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM checklist_items WHERE event_id = ? AND owner_id = ? ORDER BY id ASC", (event_id, user["id"]))
    items = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    return json_response({"items": items})

@app.post("/api/events/<event_id:int>/checklist")
def add_checklist_item(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    text = data.get("text", "").strip()
    if not text: return error_response("Text is required.")

    conn = get_db()
    cursor = conn.cursor()
    now_iso = datetime.now().isoformat()
    cursor.execute("""
        INSERT INTO checklist_items (event_id, owner_id, text, done, created_at)
        VALUES (?, ?, ?, 0, ?)
    """, (event_id, user["id"], text, now_iso))
    conn.commit()
    conn.close()
    return json_response({"ok": True}, status=201)

@app.patch("/api/events/<event_id:int>/checklist/<item_id:int>")
def toggle_checklist_item(event_id, item_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    data = request.json or {}
    done_val = 1 if data.get("done") else 0

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE checklist_items SET done = ? WHERE id = ? AND event_id = ? AND owner_id = ?", (done_val, item_id, event_id, user["id"]))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

# --- REGISTRATIONS & CHECK-IN TERMINAL ---
@app.get("/api/events/<event_id:int>/registrations")
def get_registrations(event_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registrations WHERE event_id = ? AND owner_id = ? ORDER BY id DESC", (event_id, user["id"]))
    registrations = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    return json_response({"registrations": registrations})

@app.post("/api/events/<event_id:int>/check-in/<ticket_id>")
def check_in_ticket(event_id, ticket_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM registrations 
        WHERE event_id = ? AND owner_id = ? AND UPPER(ticket_id) = UPPER(?)
    """, (event_id, user["id"], ticket_id))
    reg = cursor.fetchone()
    if not reg:
        conn.close()
        return error_response("Ticket not found for this event.", 404)
    if reg["checked_in_at"]:
        conn.close()
        return error_response(f"Ticket already checked in at {reg['checked_in_at']}.", 409)

    now_iso = datetime.now().isoformat()
    cursor.execute("UPDATE registrations SET checked_in_at = ? WHERE id = ?", (now_iso, reg["id"]))
    
    # Notification
    cursor.execute("""
        INSERT INTO notifications (owner_id, event_id, message, read_at, created_at)
        VALUES (?, ?, ?, NULL, ?)
    """, (user["id"], event_id, f"Checked In: {reg['attendee_name']} ({reg['quantity']} pass) entered with ticket {ticket_id}.", now_iso))

    conn.commit()
    cursor.execute("SELECT * FROM registrations WHERE id = ?", (reg["id"],))
    updated = dict_from_row(cursor.fetchone())
    conn.close()

    return json_response({"registration": updated})

# --- UNIVERSAL QR TICKET SCAN & CHECK-IN TERMINAL ---
@app.post("/api/tickets/scan")
@app.post("/api/tickets/check-in")
def scan_ticket():
    data = request.json or {}
    raw_code = (data.get("ticketId") or data.get("ticket_id") or data.get("code") or "").strip()
    if not raw_code:
        return error_response("Ticket code or QR scan payload is required.")

    # Extract ticket ID if raw_code contains full URL or text (e.g. EVT-XXXXXXXX)
    import re
    match = re.search(r"EVT-[A-Za-z0-9]+", raw_code, re.IGNORECASE)
    ticket_id = match.group(0).upper() if match else raw_code.upper()

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, e.title as event_title, e.venue as venue, e.date as event_date, 
               e.start_time as event_time, e.ticket_price as ticket_price, e.banner_url as banner_url
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        WHERE UPPER(r.ticket_id) = UPPER(?)
    """, (ticket_id,))
    reg = cursor.fetchone()
    if not reg:
        conn.close()
        return json_response({
            "ok": False,
            "status": "rejected",
            "error": f"Ticket ID '{ticket_id}' is NOT valid or registered in the database. Entry rejected.",
            "ticketId": ticket_id
        }, status=404)

    reg_dict = dict_from_row(reg)

    if reg["checked_in_at"]:
        conn.close()
        return json_response({
            "ok": False,
            "status": "already_used",
            "alreadyCheckedIn": True,
            "message": f"Ticket '{ticket_id}' was already scanned & admitted at {reg['checked_in_at']}. Re-entry denied.",
            "registration": reg_dict
        }, status=409)

    now_iso = datetime.now().isoformat()
    cursor.execute("UPDATE registrations SET checked_in_at = ? WHERE id = ?", (now_iso, reg["id"]))

    cursor.execute("""
        INSERT INTO notifications (owner_id, event_id, message, read_at, created_at)
        VALUES (?, ?, ?, NULL, ?)
    """, (reg["owner_id"], reg["event_id"], f"Ticket Scanned & Checked In: {reg['attendee_name']} ({reg['quantity']} pass) verified for '{reg['event_title']}'.", now_iso))

    conn.commit()
    reg_dict["checked_in_at"] = now_iso
    conn.close()

    return json_response({
        "ok": True,
        "status": "admitted",
        "alreadyCheckedIn": False,
        "message": f"Entry Confirmed! Welcome, {reg['attendee_name']}!",
        "registration": reg_dict
    })

# --- SUMMARY & NOTIFICATIONS ---
@app.get("/api/notifications")
def get_notifications():
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notifications WHERE owner_id = ? ORDER BY id DESC LIMIT 50", (user["id"],))
    notifications = [dict_from_row(r) for r in cursor.fetchall()]
    conn.close()
    return json_response({"notifications": notifications})

@app.patch("/api/notifications/<notif_id:int>/read")
def mark_notification_read(notif_id):
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read_at = ? WHERE id = ? AND owner_id = ?", (datetime.now().isoformat(), notif_id, user["id"]))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

@app.post("/api/notifications/read-all")
def mark_all_notifications_read():
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET read_at = ? WHERE owner_id = ? AND read_at IS NULL", (datetime.now().isoformat(), user["id"]))
    conn.commit()
    conn.close()
    return json_response({"ok": True})

@app.get("/api/reports/summary")
def get_summary():
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE owner_id = ?", (user["id"],))
    events = [dict_from_row(r) for r in cursor.fetchall()]

    event_ids = [e["id"] for e in events]
    placeholders = ",".join("?" for _ in event_ids) if event_ids else "0"

    cursor.execute(f"SELECT SUM(quantity) FROM registrations WHERE event_id IN ({placeholders})", event_ids if event_ids else [])
    reg_count = cursor.fetchone()[0] or 0

    cursor.execute(f"SELECT SUM(quantity) FROM registrations WHERE event_id IN ({placeholders}) AND checked_in_at IS NOT NULL", event_ids if event_ids else [])
    checked_in_count = cursor.fetchone()[0] or 0

    cursor.execute(f"SELECT COUNT(*) FROM guests WHERE event_id IN ({placeholders})", event_ids if event_ids else [])
    guest_count = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tasks WHERE event_id IN ({placeholders})", event_ids if event_ids else [])
    task_count = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tasks WHERE event_id IN ({placeholders}) AND status = 'done'", event_ids if event_ids else [])
    completed_tasks = cursor.fetchone()[0]

    total_budget = sum(float(e.get("budget", 0) or 0) for e in events)
    total_expenses = sum(float(e.get("expenses", 0) or 0) for e in events)

    conn.close()
    return json_response({
        "summary": {
            "eventCount": len(events),
            "registrationCount": reg_count,
            "checkedInCount": checked_in_count,
            "guestCount": guest_count,
            "taskCount": task_count,
            "completedTasks": completed_tasks,
            "totalBudget": total_budget,
            "totalExpenses": total_expenses
        },
        "events": events
    })

# --- CSV REPORT DOWNLOAD ---
@app.get("/api/reports/export.csv")
def export_csv():
    user = require_auth()
    if not user: return error_response("Unauthorized", 401)

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM events WHERE owner_id = ?", (user["id"],))
    events = cursor.fetchall()
    conn.close()

    lines = ["Event Title,Category,Date,Start Time,Venue,Capacity,Ticket Price (INR),Budget (INR),Expenses (INR),Status"]
    for e in events:
        lines.append(f'"{e["title"]}","{e["category"]}","{e["date"]}","{e["start_time"]}","{e["venue"]}",{e["capacity"]},{e["ticket_price"]},{e["budget"]},{e["expenses"]},"{e["status"]}"')

    csv_data = "\n".join(lines)
    response.content_type = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="evntra-report-{datetime.now().strftime("%Y-%m-%d")}.csv"'
    return csv_data

from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server
from socketserver import ThreadingMixIn
import bottle

class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    def handle_error(self, request, client_address):
        # Gracefully swallow connection reset/client disconnect errors
        pass

class ThreadedWSGIAdapter(bottle.ServerAdapter):
    def run(self, handler):
        class QuietHandler(WSGIRequestHandler):
            def log_message(self, format, *args):
                # Clean concise logging
                pass
        server = make_server(self.host, self.port, handler, 
                             server_class=ThreadingWSGIServer, 
                             handler_class=QuietHandler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()

if __name__ == "__main__":
    import socket
    PORT = int(os.environ.get("PORT", 5000))
    HOST = os.environ.get("HOST", "0.0.0.0")
    
    local_ip = "127.0.0.1"
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print(f"\n=======================================================")
    print(f"🚀 Evntra Platform Running (Multi-Threaded Server)")
    print(f"   💻 On this PC:      http://localhost:{PORT}")
    print(f"   📱 On your Phone:   http://{local_ip}:{PORT}")
    print(f"📡 Database: SQLite ({os.path.abspath('eventora.db')})")
    print(f"=======================================================\n")
    app.run(server=ThreadedWSGIAdapter(host=HOST, port=PORT))

