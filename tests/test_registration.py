import re

import pytest
from flask import url_for
from werkzeug.security import check_password_hash

from database import db

DUPLICATE_MESSAGE = "An account with that email already exists"
VALID = {"name": "Bob", "email": "bob@example.com", "password": "password123"}


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Importing app runs init_db()/seed_db(), so point it at a temp file first.
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
    yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


def _users(app):
    with app.app_context():
        conn = db.get_db()
        try:
            return conn.execute("SELECT * FROM users").fetchall()
        finally:
            conn.close()


def _post(client, **overrides):
    return client.post("/register", data={**VALID, **overrides})


def test_get_renders_form(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"<form" in response.data


def test_form_action_uses_url_for(app, client):
    html = client.get("/register").get_data(as_text=True)
    with app.test_request_context():
        expected = f'action="{url_for("register")}"'
    assert expected in html


def test_valid_registration_redirects_to_login(app, client):
    response = _post(client)
    assert response.status_code == 302
    with app.test_request_context():
        assert response.headers["Location"].endswith(url_for("login"))
    assert len(_users(app)) == 1


def test_name_and_email_are_normalised(app, client):
    _post(client, name="  Bob  ", email="  BoB@Example.COM ")
    user = _users(app)[0]
    assert user["name"] == "Bob"
    assert user["email"] == "bob@example.com"


def test_password_is_hashed(app, client):
    _post(client)
    stored = _users(app)[0]["password_hash"]
    assert stored != VALID["password"]
    assert check_password_hash(stored, VALID["password"])


def test_password_is_not_stripped(app, client):
    _post(client, password=" pass1234 ")
    stored = _users(app)[0]["password_hash"]
    assert check_password_hash(stored, " pass1234 ")


@pytest.mark.parametrize("second_email", ["bob@example.com", "BOB@Example.com"])
def test_duplicate_email_rejected(app, client, second_email):
    _post(client)
    response = _post(client, email=second_email)
    assert response.status_code == 400
    assert DUPLICATE_MESSAGE in response.get_data(as_text=True)
    assert len(_users(app)) == 1


def test_race_duplicate_returns_400_not_500(app, client, monkeypatch):
    import app as app_module

    with app.app_context():
        db.create_user("Bob", VALID["email"], VALID["password"])
    # Simulate losing the race: the pre-check misses, the INSERT hits UNIQUE.
    monkeypatch.setattr(app_module, "get_user_by_email", lambda email: None)
    response = _post(client)
    assert response.status_code == 400
    assert DUPLICATE_MESSAGE in response.get_data(as_text=True)
    assert len(_users(app)) == 1


def test_short_password_rejected(app, client):
    response = _post(client, password="short12")
    assert response.status_code == 400
    assert "at least 8" in response.get_data(as_text=True)
    assert _users(app) == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("name", ""),
        ("name", "   "),
        ("name", "x" * 101),
        ("email", ""),
        ("email", "noatsign"),
        ("email", "@x.com"),
        ("email", "a@"),
        ("email", "a" * 250 + "@x.com"),
    ],
)
def test_invalid_name_or_email_rejected(app, client, field, value):
    response = _post(client, **{field: value})
    assert response.status_code == 400
    assert _users(app) == []


def test_only_first_error_is_shown(client):
    response = _post(client, name="", email="bad")
    html = response.get_data(as_text=True)
    assert "Name is required" in html
    assert "valid email" not in html


def test_error_keeps_name_and_email_but_not_password(client):
    response = _post(client, name="Alice", email="alice@example.com", password="x")
    html = response.get_data(as_text=True)
    assert 'value="Alice"' in html
    assert 'value="alice@example.com"' in html
    password_input = re.search(r'<input type="password".*?>', html, re.DOTALL).group(0)
    assert "value=" not in password_input
