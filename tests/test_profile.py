import re
from pathlib import Path

import pytest

from database import db

ROOT = Path(__file__).resolve().parent.parent
PROFILE_TEMPLATE = ROOT / "templates" / "profile.html"
PROFILE_CSS = ROOT / "static" / "css" / "profile.css"


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        db.create_user("Bob", "bob@example.com", "password123")
    yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": "bob@example.com", "password": "password123"})
    return client


def test_profile_requires_login(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_profile_renders_when_logged_in(logged_in):
    resp = logged_in.get("/profile")
    assert resp.status_code == 200
    assert b"<html" in resp.data


def test_user_info_present(logged_in):
    import app as app_module

    html = logged_in.get("/profile").get_data(as_text=True)
    assert app_module.PROFILE_USER["name"] in html
    assert app_module.PROFILE_USER["email"] in html
    assert app_module.PROFILE_USER["member_since"] in html
    assert "PS" in html


def test_stats_match_hardcoded_transactions(logged_in):
    import app as app_module

    transactions = app_module.PROFILE_TRANSACTIONS
    total = sum(t["amount"] for t in transactions)
    html = logged_in.get("/profile").get_data(as_text=True)
    assert f"₹{total:,}" in html
    assert f'<span class="profile-stat-value">{len(transactions)}</span>' in html
    assert '<span class="profile-stat-value">Food</span>' in html


def test_transaction_table_has_enough_rows(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    tbody = html.split("<tbody>")[1].split("</tbody>")[0]
    assert tbody.count("<tr>") >= 3
    assert "profile-badge-" in tbody


def test_category_breakdown(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    fills = re.findall(r'class="(profile-bar-fill[^"]*)"', html)
    assert len(fills) >= 3
    assert all("profile-bar-w-" in classes for classes in fills)


def test_navbar_logged_in(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert 'href="/profile"' in html
    assert "Profile" in html
    assert "Sign out" in html
    assert "Get started" not in html


def test_navbar_logged_out(client):
    html = client.get("/login").get_data(as_text=True)
    assert "Sign in" in html
    assert "Get started" in html
    assert 'href="/profile"' not in html


@pytest.mark.parametrize("path", [PROFILE_TEMPLATE, PROFILE_CSS], ids=lambda p: p.name)
def test_no_inline_styles_or_hex_colours(path):
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"style\s*=", text, re.I)
    assert "<style" not in text.lower()
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text)
