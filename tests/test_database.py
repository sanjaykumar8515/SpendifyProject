import re
import sqlite3
from datetime import date

import pytest
from werkzeug.security import check_password_hash

from database import db

CATEGORIES = {"Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"}


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    return db


def _scalar(sql, params=()):
    conn = db.get_db()
    try:
        return conn.execute(sql, params).fetchone()[0]
    finally:
        conn.close()


def test_tables_and_columns_exist(temp_db):
    conn = db.get_db()
    try:
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        expense_cols = {r["name"] for r in conn.execute("PRAGMA table_info(expenses)")}
    finally:
        conn.close()
    assert {"users", "expenses"} <= tables
    assert user_cols == {"id", "name", "email", "password_hash", "created_at"}
    assert expense_cols == {"id", "user_id", "amount", "category", "date", "description", "created_at"}


def test_init_db_is_idempotent(temp_db):
    db.init_db()
    db.init_db()


def test_get_db_settings(temp_db):
    conn = db.get_db()
    try:
        assert conn.row_factory is sqlite3.Row
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_seed_contents(temp_db):
    db.seed_db()
    assert _scalar("SELECT COUNT(*) FROM users") == 1
    assert _scalar("SELECT email FROM users") == "demo@spendly.com"
    assert _scalar("SELECT COUNT(*) FROM expenses") == 8

    conn = db.get_db()
    try:
        rows = conn.execute("SELECT category, date FROM expenses").fetchall()
    finally:
        conn.close()
    assert {r["category"] for r in rows} == CATEGORIES
    month = date.today().strftime("%Y-%m")
    for r in rows:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["date"])
        assert r["date"].startswith(month)


def test_seed_password_is_hashed(temp_db):
    db.seed_db()
    stored = _scalar("SELECT password_hash FROM users")
    assert stored != "demo123"
    assert check_password_hash(stored, "demo123")


def test_seed_is_idempotent(temp_db):
    db.seed_db()
    db.seed_db()
    assert _scalar("SELECT COUNT(*) FROM users") == 1
    assert _scalar("SELECT COUNT(*) FROM expenses") == 8


def test_duplicate_email_rejected(temp_db):
    db.seed_db()
    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Other", "demo@spendly.com", "x"),
            )
    finally:
        conn.close()


def test_invalid_user_id_rejected(temp_db):
    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
                (9999, 1.0, "Food", "2026-01-01"),
            )
    finally:
        conn.close()


@pytest.mark.parametrize(
    "sql, params",
    [
        ("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", (None, "a@x.com", "h")),
        ("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", ("A", None, "h")),
        ("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", ("A", "a@x.com", None)),
    ],
)
def test_users_not_null_constraints(temp_db, sql, params):
    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql, params)
    finally:
        conn.close()


@pytest.mark.parametrize(
    "values",
    [
        (None, "Food", "2026-01-01"),
        (1.0, None, "2026-01-01"),
        (1.0, "Food", None),
    ],
)
def test_expenses_not_null_constraints(temp_db, values):
    db.seed_db()
    conn = db.get_db()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date) VALUES (1, ?, ?, ?)",
                values,
            )
    finally:
        conn.close()


def test_description_is_optional(temp_db):
    db.seed_db()
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date) VALUES (1, 5.0, 'Food', '2026-01-01')"
        )
        conn.commit()
        row = conn.execute("SELECT description FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row["description"] is None


def test_created_at_defaults_are_set(temp_db):
    db.seed_db()
    assert _scalar("SELECT created_at FROM users") is not None
    assert _scalar("SELECT COUNT(*) FROM expenses WHERE created_at IS NULL") == 0


def test_amounts_stored_as_real(temp_db):
    db.seed_db()
    assert _scalar("SELECT COUNT(*) FROM expenses WHERE typeof(amount) != 'real'") == 0


def test_seed_expenses_belong_to_demo_user(temp_db):
    db.seed_db()
    user_id = _scalar("SELECT id FROM users WHERE email = ?", ("demo@spendly.com",))
    assert _scalar("SELECT COUNT(*) FROM expenses WHERE user_id = ?", (user_id,)) == 8


def test_foreign_keys_enforced_on_every_connection(temp_db):
    for _ in range(2):
        conn = db.get_db()
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()


def test_init_db_preserves_existing_data(temp_db):
    db.seed_db()
    db.init_db()
    assert _scalar("SELECT COUNT(*) FROM users") == 1
    assert _scalar("SELECT COUNT(*) FROM expenses") == 8


def test_seed_skips_when_any_user_exists(temp_db):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES ('Real', 'real@x.com', 'h')"
        )
        conn.commit()
    finally:
        conn.close()
    db.seed_db()
    assert _scalar("SELECT COUNT(*) FROM users") == 1
    assert _scalar("SELECT COUNT(*) FROM expenses") == 0


def test_rows_accessible_by_column_name(temp_db):
    db.seed_db()
    conn = db.get_db()
    try:
        row = conn.execute("SELECT name, email FROM users").fetchone()
    finally:
        conn.close()
    assert row["name"] == "Demo User"
    assert row["email"] == "demo@spendly.com"
