import pytest

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


def _login(client):
    return client.post("/login", data={"email": "bob@example.com", "password": "password123"})


def test_analytics_redirects_when_logged_out(client):
    resp = client.get("/analytics")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/login"


def test_analytics_renders_coming_soon_when_logged_in(client):
    _login(client)
    resp = client.get("/analytics")
    assert resp.status_code == 200
    assert b"Advanced Analytics" in resp.data
    assert b"Coming Soon" in resp.data


def test_navbar_analytics_link_only_for_logged_in(client):
    assert b"Analytics" not in client.get("/").data
    _login(client)
    assert b'href="/analytics"' in client.get("/").data


def test_navbar_highlights_analytics_on_analytics_page(client):
    _login(client)
    page = client.get("/analytics").data
    assert b'href="/analytics" class="nav-link-always nav-link-active"' in page
    assert b'href="/profile" class="nav-link-always nav-link-active"' not in page
