import calendar
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_id,
)

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


# ------------------------------------------------------------------ #
# Profile                                                             #
# ------------------------------------------------------------------ #

KNOWN_CATEGORY_SLUGS = {"food", "transport", "bills", "health", "shopping", "entertainment"}


def get_initials(name):
    return "".join(word[0] for word in name.split()[:2]).upper() or "?"


def format_display_date(iso_date):
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return iso_date


def category_slug(name):
    slug = name.lower()
    return slug if slug in KNOWN_CATEGORY_SLUGS else "other"


def bar_bucket(pct):
    return min(100, max(0, 5 * round(pct / 5)))


def parse_date_range(raw_from, raw_to):
    parsed = []
    for raw in (raw_from, raw_to):
        raw = (raw or "").strip()
        if not raw:
            parsed.append(None)
            continue
        try:
            parsed_date = datetime.strptime(raw, "%Y-%m-%d").date()
            parsed.append(parsed_date.isoformat())
        except ValueError:
            return None, None, "Enter dates as YYYY-MM-DD"
    date_from, date_to = parsed
    if date_from and date_to and date_from > date_to:
        return None, None, "Start date must be on or before end date"
    return date_from, date_to, None


def shift_months(day, months):
    """Move back `months` months, clamping the day to that month's end."""
    year, month_index = divmod(day.year * 12 + day.month - 1 - months, 12)
    month = month_index + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def get_filter_presets(today, date_from, date_to):
    month_start = today.replace(day=1)
    month_end = today.replace(
        day=calendar.monthrange(today.year, today.month)[1]
    )
    ranges = [
        ("All Time", None, None),
        ("This Month", month_start, month_end),
    ]
    ranges += [
        (f"Last {months} Months", shift_months(today, months), None)
        for months in (3, 6)
    ]
    presets = []
    for label, start, end in ranges:
        start_iso = start.isoformat() if start else None
        end_iso = end.isoformat() if end else None
        presets.append({
            "label": label,
            "date_from": start_iso,
            "date_to": end_iso,
            "active": (start_iso, end_iso) == (date_from, date_to),
        })
    return presets


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    raw_from = request.args.get("date_from", "").strip()
    raw_to = request.args.get("date_to", "").strip()
    date_from, date_to, filter_error = parse_date_range(raw_from, raw_to)
    date_range = {"date_from": date_from, "date_to": date_to}

    transactions = [
        {**t, "date": format_display_date(t["date"])}
        for t in get_recent_transactions(user_id, **date_range)
    ]
    categories = [
        {
            "name": c["name"],
            "slug": category_slug(c["name"]),
            "amount": c["amount"],
            "pct": c["pct"],
            "bucket": bar_bucket(c["pct"]),
        }
        for c in get_category_breakdown(user_id, **date_range)
    ]
    return render_template(
        "profile.html",
        user={**user, "initials": get_initials(user["name"])},
        stats=get_summary_stats(user_id, **date_range),
        transactions=transactions,
        categories=categories,
        date_from=raw_from,
        date_to=raw_to,
        filter_error=filter_error,
        filter_active=bool(date_from or date_to),
        presets=get_filter_presets(date.today(), date_from, date_to),
    )


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
