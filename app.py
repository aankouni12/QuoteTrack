import os
import re
import sqlite3
from contextlib import closing
from datetime import date
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, abort, session
from werkzeug.security import check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("QUOTETRACK_SECRET_KEY", "dev-only-change-me")
DATABASE = "quotetrack.db"
SERVICE_TYPES = ["Cleaning", "Handyman", "Maintenance", "Other"]
STATUSES = ["New", "Contacted", "Estimate Sent", "Won", "Lost"]


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "owner_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target):
    # Only allow redirects to pages on this site
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("dashboard")


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


def valid_follow_up_date(value):
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


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


@app.route("/login", methods=["GET", "POST"])
def login():
    if "owner_id" in session:
        return redirect(url_for("dashboard"))

    next_page = request.values.get("next", "")
    if request.method == "GET":
        return render_template("login.html", error=None, username="", next_page=next_page)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    with closing(get_db()) as conn:
        owner = conn.execute(
            "SELECT id, password_hash FROM owners WHERE username = ?", (username,)
        ).fetchone()

    if owner is None or not check_password_hash(owner["password_hash"], password):
        error = "Invalid username or password."
        return render_template("login.html", error=error, username=username, next_page=next_page), 401

    session.clear()
    session["owner_id"] = owner["id"]
    session["username"] = username
    return redirect(safe_next(next_page))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    query = """
        SELECT requests.id, requests.service_type, requests.status, requests.created_at,
               requests.follow_up_date, customers.name, customers.email
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
@login_required
def request_detail(request_id):
    error = None
    with closing(get_db()) as conn:
        if request.method == "POST":
            new_status = request.form.get("status", "")
            notes = request.form.get("notes", "").strip()
            follow_up_date = request.form.get("follow_up_date")
            if new_status not in STATUSES:
                abort(400)
            if follow_up_date and not valid_follow_up_date(follow_up_date):
                error = "Enter a valid follow-up date in YYYY-MM-DD format."
            else:
                with conn:
                    # Older forms omit the date. An empty date field clears it.
                    updated = conn.execute(
                        """
                        UPDATE requests
                        SET status = :status, notes = :notes,
                            follow_up_date = CASE
                                WHEN :follow_up_date IS NULL THEN follow_up_date
                                ELSE NULLIF(:follow_up_date, '')
                            END
                        WHERE id = :request_id
                        """,
                        {
                            "status": new_status,
                            "notes": notes,
                            "follow_up_date": follow_up_date,
                            "request_id": request_id,
                        },
                    )
                    if updated.rowcount == 0:
                        abort(404)
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

    if row is None:
        abort(404)

    return render_template(
        "request_detail.html",
        r=row,
        statuses=STATUSES,
        form=request.form,
        error=error,
        saved=request.method == "GET" and request.args.get("saved"),
    ), 400 if error else 200


if __name__ == "__main__":
    app.run(debug=True)