import re
import sqlite3
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)
DATABASE = "quotetrack.db"
SERVICE_TYPES = ["Cleaning", "Handyman", "Maintenance", "Other"]


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


if __name__ == "__main__":
    app.run(debug=True)