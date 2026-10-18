import pytest
from flask import url_for

from database import db


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


def _login(client, email="bob@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password})


def _user_id(app):
    with app.app_context():
        return db.get_user_by_email("bob@example.com")["id"]


def test_get_login_renders_form(client, app):
    resp = client.get("/login")
    assert resp.status_code == 200
    with app.test_request_context():
        assert f'action="{url_for("login")}"'.encode() in resp.data


def test_login_success_sets_session_and_redirects(client, app):
    resp = _login(client)
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/profile"
    with client.session_transaction() as sess:
        assert sess["user_id"] == _user_id(app)


def test_email_case_and_whitespace_ignored(client):
    assert _login(client, email="  BOB@Example.com ").status_code == 302


def test_wrong_password(client):
    resp = _login(client, password="nope")
    assert resp.status_code == 400
    assert b"Invalid email or password" in resp.data
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_unknown_email_same_message(client):
    resp = _login(client, email="who@example.com")
    assert resp.status_code == 400
    assert b"Invalid email or password" in resp.data


def test_failed_login_repopulates_email_not_password(client):
    resp = _login(client, password="secretwrong")
    assert b'value="bob@example.com"' in resp.data
    assert b"secretwrong" not in resp.data


def test_login_when_logged_in_redirects(client):
    _login(client)
    resp = client.get("/login")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/profile"


def test_logout_clears_session(client):
    _login(client)
    resp = client.get("/logout")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/"
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_logout_when_logged_out(client):
    assert client.get("/logout").status_code == 302


def test_navbar_reflects_state(client):
    assert b"Sign out" not in client.get("/").data
    _login(client)
    page = client.get("/").data
    assert b"Sign out" in page
    assert b"Get started" not in page


@pytest.mark.parametrize("path", ["/login", "/register"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_auth_pages_redirect_when_logged_in(client, path, method):
    _login(client)
    resp = getattr(client, method)(path, data={"email": "x@example.com", "password": "password123", "name": "X"})
    assert resp.status_code == 302
    assert resp.headers["Location"] == ("/profile" if path == "/login" else "/")
