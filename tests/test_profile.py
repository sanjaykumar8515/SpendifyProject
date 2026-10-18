import re
from pathlib import Path

import pytest

from database import db

ROOT = Path(__file__).resolve().parent.parent


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


def _login(client):
    return client.post(
        "/login", data={"email": "bob@example.com", "password": "password123"}
    )


def test_profile_requires_login(client):
    resp = client.get("/profile")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_profile_renders_when_logged_in(client):
    _login(client)
    resp = client.get("/profile")
    assert resp.status_code == 200
    page = resp.data
    for text in (b"Total spent", b"Transactions", b"Top category",
                 b"Transaction history", b"Category breakdown",
                 b"Member since"):
        assert text in page


def test_profile_has_enough_content(client):
    _login(client)
    page = client.get("/profile").data.decode()
    assert page.count("<tr>") - 1 >= 3  # header row excluded
    assert page.count('class="category-row"') >= 3


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
