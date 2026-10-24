import pytest

from database import db
from database.queries import get_category_breakdown, get_summary_stats


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        db.create_user("Bob", "bob@example.com", "password123")
        db.create_user("Eve", "eve@example.com", "password123")
        yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": "bob@example.com", "password": "password123"})
    return client


def _user_id(app, email):
    with app.app_context():
        conn = db.get_db()
        try:
            return conn.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()["id"]
        finally:
            conn.close()


def _make_expense(app, email="bob@example.com", amount=12.5, category="Food",
                  date="2024-05-10", description="Lunch"):
    user_id = _user_id(app, email)
    with app.app_context():
        return db.create_expense(user_id, amount, category, date, description)


def _row(app, expense_id):
    with app.app_context():
        conn = db.get_db()
        try:
            return conn.execute(
                "SELECT * FROM expenses WHERE id = ?", (expense_id,)
            ).fetchone()
        finally:
            conn.close()


class TestAuthGuard:
    def test_logged_out_redirects_to_login_and_deletes_nothing(self, app, client):
        expense_id = _make_expense(app)
        response = client.post(f"/expenses/{expense_id}/delete")
        assert response.status_code == 302
        assert "/login" in response.headers["Location"]
        assert _row(app, expense_id) is not None


class TestMethod:
    def test_get_returns_405_and_deletes_nothing(self, app, logged_in):
        expense_id = _make_expense(app)
        response = logged_in.get(f"/expenses/{expense_id}/delete")
        assert response.status_code == 405
        assert _row(app, expense_id) is not None


class TestDelete:
    def test_redirects_to_profile_and_removes_row(self, app, logged_in):
        expense_id = _make_expense(app, description="Unique lunch")
        response = logged_in.post(f"/expenses/{expense_id}/delete")
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/profile")
        assert _row(app, expense_id) is None
        page = logged_in.get("/profile").get_data(as_text=True)
        assert "Unique lunch" not in page

    def test_stats_reflect_deletion(self, app, logged_in):
        keep_id = _make_expense(app, amount=10.0, category="Food")
        drop_id = _make_expense(app, amount=30.0, category="Bills")
        logged_in.post(f"/expenses/{drop_id}/delete")
        user_id = _user_id(app, "bob@example.com")
        with app.app_context():
            stats = get_summary_stats(user_id)
            names = [c["name"] for c in get_category_breakdown(user_id)]
        assert stats["total_spent"] == 10.0
        assert stats["transaction_count"] == 1
        assert names == ["Food"]
        assert _row(app, keep_id) is not None

    def test_leaves_other_expenses_intact(self, app, logged_in):
        target = _make_expense(app, description="Target")
        own_other = _make_expense(app, description="Mine")
        eve_expense = _make_expense(app, email="eve@example.com")
        logged_in.post(f"/expenses/{target}/delete")
        assert _row(app, own_other) is not None
        assert _row(app, eve_expense) is not None

    def test_nonexistent_id_returns_404(self, logged_in):
        assert logged_in.post("/expenses/9999/delete").status_code == 404

    def test_other_users_expense_returns_404_and_survives(self, app, logged_in):
        eve_expense = _make_expense(app, email="eve@example.com")
        response = logged_in.post(f"/expenses/{eve_expense}/delete")
        assert response.status_code == 404
        assert _row(app, eve_expense) is not None

    def test_second_delete_returns_404(self, app, logged_in):
        expense_id = _make_expense(app)
        assert logged_in.post(f"/expenses/{expense_id}/delete").status_code == 302
        assert logged_in.post(f"/expenses/{expense_id}/delete").status_code == 404

    def test_edit_page_returns_404_after_delete(self, app, logged_in):
        expense_id = _make_expense(app)
        logged_in.post(f"/expenses/{expense_id}/delete")
        assert logged_in.get(f"/expenses/{expense_id}/edit").status_code == 404


class TestUi:
    def test_profile_row_has_edit_link_and_delete_form(self, app, logged_in):
        expense_id = _make_expense(app)
        page = logged_in.get("/profile").get_data(as_text=True)
        assert f'href="/expenses/{expense_id}/edit"' in page
        assert f'action="/expenses/{expense_id}/delete"' in page
        assert 'method="post"' in page
        assert "data-confirm=" in page

    def test_main_js_handles_data_confirm(self, client):
        script = client.get("/static/js/main.js").get_data(as_text=True)
        assert "data-confirm" in script
        assert "confirm(" in script

    def test_add_and_edit_still_work(self, app, logged_in):
        expense_id = _make_expense(app)
        assert logged_in.get("/expenses/add").status_code == 200
        assert logged_in.get(f"/expenses/{expense_id}/edit").status_code == 200


class TestDbHelper:
    def test_returns_false_for_wrong_user_true_for_owner(self, app):
        expense_id = _make_expense(app)
        eve_id = _user_id(app, "eve@example.com")
        bob_id = _user_id(app, "bob@example.com")
        with app.app_context():
            assert db.delete_expense(expense_id, eve_id) is False
            assert db.delete_expense(expense_id, bob_id) is True
        assert _row(app, expense_id) is None
