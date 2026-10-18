import re
from pathlib import Path

import pytest

from database import db

ROOT = Path(__file__).resolve().parent.parent

DEMO_EXPENSES = [
    (12.50, "Food", "2026-10-01", "Lunch at cafe"),
    (45.00, "Transport", "2026-10-03", "Monthly bus pass"),
    (120.00, "Bills", "2026-10-05", "Electricity bill"),
    (30.00, "Health", "2026-10-08", "Pharmacy"),
    (25.00, "Entertainment", "2026-10-11", "Movie tickets"),
    (89.99, "Shopping", "2026-10-15", "New shoes"),
    (15.00, "Other", "2026-10-19", "Miscellaneous"),
    (42.75, "Food", "2026-10-24", "Groceries"),
]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        db.create_user("Bob", "bob@example.com", "password123")
        demo_id = db.create_user("Demo User", "demo@spendly.com", "demo123")
        conn = db.get_db()
        try:
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                [(demo_id, *row) for row in DEMO_EXPENSES],
            )
            conn.commit()
        finally:
            conn.close()
    yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


def test_profile_requires_login(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_profile_shows_real_user_data(client):
    _login(client)
    resp = client.get("/profile")
    assert resp.status_code == 200
    page = resp.data.decode()
    assert "Demo User" in page
    assert "demo@spendly.com" in page
    assert "Member since" in page
    assert "₹380.24" in page
    assert "Bills" in page  # top category
    assert re.search(r'profile-stat-value">8<', page)


def test_profile_transactions_newest_first(client):
    _login(client)
    page = client.get("/profile").data.decode()
    assert page.count("<tr>") - 1 == 8
    order = ["Groceries", "Miscellaneous", "New shoes", "Movie tickets",
             "Pharmacy", "Electricity bill", "Monthly bus pass", "Lunch at cafe"]
    positions = [page.index(desc) for desc in order]
    assert positions == sorted(positions)


def test_profile_category_breakdown(client):
    _login(client)
    page = client.get("/profile").data.decode()
    assert page.count('class="profile-cat-row"') == 7
    pcts = [int(p) for p in re.findall(r'profile-cat-pct">(\d+)%', page)]
    assert sum(pcts) == 100
    assert pcts == sorted(pcts, reverse=True)


def test_profile_uses_rupee_not_other_currencies(client):
    _login(client)
    page = client.get("/profile").data.decode()
    assert "₹" in page
    assert "$" not in page and "£" not in page


def test_profile_empty_state_for_user_without_expenses(client):
    _login(client, "bob@example.com", "password123")
    resp = client.get("/profile")
    assert resp.status_code == 200
    page = resp.data.decode()
    assert "₹0.00" in page
    assert "No expenses yet" in page
    assert 'class="profile-cat-row"' not in page


def test_profile_does_not_leak_other_users_data(client):
    _login(client, "bob@example.com", "password123")
    page = client.get("/profile").data.decode()
    assert "Groceries" not in page and "demo@spendly.com" not in page


def test_profile_stale_session_redirects_to_login(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 9999
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_navbar_shows_profile_and_sign_out(client):
    _login(client)
    page = client.get("/profile").data
    assert b"Profile" in page and b"Sign out" in page
    assert b"Get started" not in page


def test_no_inline_styles_or_hex_in_profile_assets(client):
    _login(client)
    assert b'style="' not in client.get("/profile").data
    template = (ROOT / "templates" / "profile.html").read_text(encoding="utf-8")
    css = (ROOT / "static" / "css" / "profile.css").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", template)
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)


def test_no_hardcoded_profile_constants_in_app():
    assert "PROFILE_" not in (ROOT / "app.py").read_text(encoding="utf-8")
