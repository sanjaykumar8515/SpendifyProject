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
        return redirect(url_for("profile"))
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


# Hardcoded profile data — replaced by database queries in a later step.
PROFILE_USER = {
    "name": "Priya Sharma",
    "email": "priya.sharma@example.com",
    "member_since": "March 2025",
}

PROFILE_TRANSACTIONS = [
    {"date": "14 Oct 2025", "description": "Grocery run", "category": "Food", "amount": 1840},
    {"date": "12 Oct 2025", "description": "Metro card top-up", "category": "Transport", "amount": 500},
    {"date": "10 Oct 2025", "description": "Electricity bill", "category": "Bills", "amount": 2300},
    {"date": "07 Oct 2025", "description": "Dinner with friends", "category": "Food", "amount": 1260},
    {"date": "03 Oct 2025", "description": "Pharmacy", "category": "Health", "amount": 640},
    {"date": "29 Sep 2025", "description": "Headphones", "category": "Shopping", "amount": 2450},
]


def _initials(name):
    return "".join(word[0] for word in name.split()[:2]).upper()


def _profile_context():
    totals = {}
    for transaction in PROFILE_TRANSACTIONS:
        category = transaction["category"]
        totals[category] = totals.get(category, 0) + transaction["amount"]

    total_spent = sum(totals.values())
    categories = []
    for name, amount in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        pct = round(amount / total_spent * 100)
        categories.append({
            "name": name,
            "slug": name.lower(),
            "amount": amount,
            "pct": pct,
            "bucket": 5 * round(pct / 5),
        })

    return {
        "user": {**PROFILE_USER, "initials": _initials(PROFILE_USER["name"])},
        "stats": {
            "total_spent": total_spent,
            "transaction_count": len(PROFILE_TRANSACTIONS),
            "top_category": categories[0]["name"],
        },
        "transactions": PROFILE_TRANSACTIONS,
        "categories": categories,
    }


# The page shows the same hardcoded user for every logged-in account for now.
@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("profile.html", **_profile_context())


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

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
