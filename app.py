import re
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, abort

app = Flask(__name__)
DATABASE = "quotetrack.db"
SERVICE_TYPES = ["Cleaning", "Handyman", "Maintenance", "Other"]
STATUSES = ["New", "Contacted", "Estimate Sent", "Won", "Lost"]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def validate_request(form):
    errors = []
    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    service_type = form.get("service_type", "")
    description = form.get("description", "").strip()

    if not name:
        errors.append("Name is required.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("A valid email is required.")
    if service_type not in SERVICE_TYPES:
        errors.append("Please choose a service type.")
    if len(description) < 10:
        errors.append("Please describe the job in at least 10 characters.")
    return errors


@app.route("/")
def home():
    return redirect(url_for("request_form"))


@app.route("/request", methods=["GET", "POST"])
def request_form():
    if request.method == "GET":
        return render_template("request_form.html", services=SERVICE_TYPES, errors=[], form={})

    errors = validate_request(request.form)
    if errors:
        return render_template("request_form.html", services=SERVICE_TYPES, errors=errors, form=request.form), 400

    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    phone = request.form.get("phone", "").strip()

    conn = get_db()
    customer = conn.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
    if customer:
        customer_id = customer["id"]
    else:
        cursor = conn.execute(
            "INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
            (name, email, phone),
        )
        customer_id = cursor.lastrowid

    conn.execute(
        "INSERT INTO requests (customer_id, service_type, description) VALUES (?, ?, ?)",
        (customer_id, request.form["service_type"], request.form["description"].strip()),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("confirmation"))


@app.route("/confirmation")
def confirmation():
    return render_template("confirmation.html")


@app.route("/dashboard")
def dashboard():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    query = """
        SELECT requests.id, requests.service_type, requests.status, requests.created_at,
               customers.name, customers.email
        FROM requests
        JOIN customers ON customers.id = requests.customer_id
        WHERE 1 = 1
    """
    params = []
    if search:
        query += " AND (customers.name LIKE ? OR customers.email LIKE ?)"
        params += [f"%{search}%", f"%{search}%"]
    if status in STATUSES:
        query += " AND requests.status = ?"
        params.append(status)
    query += " ORDER BY requests.created_at DESC"

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return render_template("dashboard.html", rows=rows, statuses=STATUSES, search=search, status=status)


@app.route("/requests/<int:request_id>", methods=["GET", "POST"])
def request_detail(request_id):
    conn = get_db()

    if request.method == "POST":
        new_status = request.form.get("status", "")
        notes = request.form.get("notes", "").strip()
        if new_status not in STATUSES:
            conn.close()
            abort(400)
        conn.execute(
            "UPDATE requests SET status = ?, notes = ? WHERE id = ?",
            (new_status, notes, request_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("request_detail", request_id=request_id, saved=1))

    row = conn.execute(
        """
        SELECT requests.*, customers.name, customers.email, customers.phone
        FROM requests
        JOIN customers ON customers.id = requests.customer_id
        WHERE requests.id = ?
        """,
        (request_id,),
    ).fetchone()
    conn.close()

    if row is None:
        abort(404)

    return render_template("request_detail.html", r=row, statuses=STATUSES, saved=request.args.get("saved"))


if __name__ == "__main__":
    app.run(debug=True)