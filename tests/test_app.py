import pytest

from database import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the DB at a temp file before app startup runs init_db()/seed_db().
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    import app as app_module

    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


@pytest.mark.parametrize("path", ["/", "/register", "/login"])
def test_implemented_pages_render(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert b"<html" in response.data.lower()


def test_unknown_route_returns_404(client):
    assert client.get("/does-not-exist").status_code == 404
