import sqlite3

from flask import Flask, redirect, render_template, request, url_for

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)

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


@app.route("/login")
def login():
    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    return "Logout — coming in Step 3"


@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


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
