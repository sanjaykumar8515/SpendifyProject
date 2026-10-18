import os
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-insecure-secret-key")

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


DUPLICATE_EMAIL_ERROR = "An account with that email already exists"


def validate_registration(name, email, password):
    if not name or len(name) > 100:
        return "Name is required (max 100 characters)"
    local, sep, domain = email.partition("@")
    if not (local and sep and domain) or len(email) > 254:
        return "Enter a valid email address"
    if len(password) < 8:
        return "Password must be at least 8 characters"
    if get_user_by_email(email):
        return DUPLICATE_EMAIL_ERROR
    return None


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = validate_registration(name, email, password)
    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = DUPLICATE_EMAIL_ERROR
        else:
            return redirect(url_for("login"))

    return render_template("register.html", error=error, name=name, email=email), 400


LOGIN_ERROR = "Invalid email or password"


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error=LOGIN_ERROR, email=email), 400

    session.clear()
    session["user_id"] = user["id"]
    return redirect(url_for("profile"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

PROFILE_USER = {
    "name": "Demo User",
    "email": "demo@spendly.com",
    "initials": "DU",
    "member_since": "January 2026",
}

PROFILE_STATS = {
    "total_spent": "380.24",
    "transaction_count": 8,
    "top_category": "Bills",
}

PROFILE_TRANSACTIONS = [
    {"date": "24 Oct 2026", "description": "Groceries", "category": "Food", "amount": "42.75"},
    {"date": "19 Oct 2026", "description": "Miscellaneous", "category": "Other", "amount": "15.00"},
    {"date": "15 Oct 2026", "description": "New shoes", "category": "Shopping", "amount": "89.99"},
    {"date": "11 Oct 2026", "description": "Movie tickets", "category": "Entertainment", "amount": "25.00"},
    {"date": "08 Oct 2026", "description": "Pharmacy", "category": "Health", "amount": "30.00"},
    {"date": "05 Oct 2026", "description": "Electricity bill", "category": "Bills", "amount": "120.00"},
    {"date": "03 Oct 2026", "description": "Monthly bus pass", "category": "Transport", "amount": "45.00"},
    {"date": "01 Oct 2026", "description": "Lunch at cafe", "category": "Food", "amount": "12.50"},
]

PROFILE_CATEGORIES = [
    {"name": "Bills", "total": "120.00", "percent": 32},
    {"name": "Food", "total": "55.25", "percent": 15},
    {"name": "Shopping", "total": "89.99", "percent": 24},
    {"name": "Transport", "total": "45.00", "percent": 12},
    {"name": "Health", "total": "30.00", "percent": 8},
    {"name": "Entertainment", "total": "25.00", "percent": 7},
    {"name": "Other", "total": "15.00", "percent": 4},
]


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template(
        "profile.html",
        user=PROFILE_USER,
        stats=PROFILE_STATS,
        transactions=PROFILE_TRANSACTIONS,
        categories=sorted(PROFILE_CATEGORIES, key=lambda c: c["percent"], reverse=True),
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
