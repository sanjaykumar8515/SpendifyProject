import os
import sqlite3
from datetime import date

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cursor.lastrowid

        today = date.today()
        samples = [
            (1, 12.50, "Food", "Lunch at cafe"),
            (3, 45.00, "Transport", "Monthly bus pass"),
            (5, 120.00, "Bills", "Electricity bill"),
            (8, 30.00, "Health", "Pharmacy"),
            (11, 25.00, "Entertainment", "Movie tickets"),
            (15, 89.99, "Shopping", "New shoes"),
            (19, 15.00, "Other", "Miscellaneous"),
            (24, 42.75, "Food", "Groceries"),
        ]
        rows = [
            (user_id, amount, category, today.replace(day=day).isoformat(), description)
            for day, amount, category, description in samples
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()
