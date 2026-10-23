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


def _form(**overrides):
    data = {
        "amount": "99.99",
        "category": "Bills",
        "date": "2024-06-01",
        "description": "Updated",
    }
    data.update(overrides)
    return data


class TestAuthGuard:
    def test_get_redirects_to_login(self, client, app):
        expense_id = _make_expense(app)
        r = client.get(f"/expenses/{expense_id}/edit")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]

    def test_post_redirects_and_changes_nothing(self, client, app):
        expense_id = _make_expense(app)
        r = client.post(f"/expenses/{expense_id}/edit", data=_form())
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]
        assert _row(app, expense_id)["description"] == "Lunch"


class TestGet:
    def test_prefills_form(self, logged_in, app):
        expense_id = _make_expense(app)
        r = logged_in.get(f"/expenses/{expense_id}/edit")
        body = r.get_data(as_text=True)
        assert r.status_code == 200
        assert "Edit Expense" in body
        assert "Save changes" in body
        assert 'value="12.50"' in body
        assert 'value="2024-05-10"' in body
        assert 'value="Lunch"' in body
        assert '<option value="Food" selected>' in body
        assert f'action="/expenses/{expense_id}/edit"' in body

    def test_nonexistent_returns_404(self, logged_in):
        assert logged_in.get("/expenses/9999/edit").status_code == 404

    def test_foreign_expense_returns_404(self, logged_in, app):
        expense_id = _make_expense(app, email="eve@example.com")
        assert logged_in.get(f"/expenses/{expense_id}/edit").status_code == 404


class TestPost:
    def test_valid_update_redirects_and_saves(self, logged_in, app):
        expense_id = _make_expense(app)
        r = logged_in.post(f"/expenses/{expense_id}/edit", data=_form())
        assert r.status_code == 302
        assert r.headers["Location"].endswith("/profile")
        row = _row(app, expense_id)
        assert row["amount"] == 99.99
        assert row["category"] == "Bills"
        assert row["date"] == "2024-06-01"
        assert row["description"] == "Updated"

    def test_profile_reflects_edit(self, logged_in, app):
        expense_id = _make_expense(app)
        logged_in.post(f"/expenses/{expense_id}/edit", data=_form())
        body = logged_in.get("/profile").get_data(as_text=True)
        assert "Updated" in body
        assert "99.99" in body
        assert "Bills" in body

    def test_nonexistent_returns_404(self, logged_in):
        assert logged_in.post("/expenses/9999/edit", data=_form()).status_code == 404

    def test_foreign_expense_404_and_unchanged(self, logged_in, app):
        expense_id = _make_expense(app, email="eve@example.com")
        r = logged_in.post(f"/expenses/{expense_id}/edit", data=_form())
        assert r.status_code == 404
        row = _row(app, expense_id)
        assert row["description"] == "Lunch"
        assert row["amount"] == 12.5

    @pytest.mark.parametrize("overrides", [
        {"amount": ""},
        {"amount": "abc"},
        {"amount": "-5"},
        {"amount": "0"},
        {"amount": "1.234"},
        {"category": "Nope"},
        {"date": "2024-13-45"},
        {"date": ""},
        {"description": "x" * 201},
    ])
    def test_invalid_input_returns_400_and_unchanged(self, logged_in, app, overrides):
        expense_id = _make_expense(app)
        r = logged_in.post(f"/expenses/{expense_id}/edit", data=_form(**overrides))
        assert r.status_code == 400
        assert 'role="alert"' in r.get_data(as_text=True)
        row = _row(app, expense_id)
        assert row["amount"] == 12.5
        assert row["category"] == "Food"
        assert row["date"] == "2024-05-10"
        assert row["description"] == "Lunch"

    def test_error_preserves_values_and_action(self, logged_in, app):
        expense_id = _make_expense(app)
        r = logged_in.post(
            f"/expenses/{expense_id}/edit", data=_form(amount="abc")
        )
        body = r.get_data(as_text=True)
        assert 'value="abc"' in body
        assert 'value="Updated"' in body
        assert f'action="/expenses/{expense_id}/edit"' in body

    def test_forged_user_id_ignored(self, logged_in, app):
        expense_id = _make_expense(app)
        eve_id = _user_id(app, "eve@example.com")
        logged_in.post(
            f"/expenses/{expense_id}/edit", data=_form(user_id=str(eve_id))
        )
        assert _row(app, expense_id)["user_id"] == _user_id(app, "bob@example.com")


class TestProfileLinks:
    def test_edit_link_per_row(self, logged_in, app):
        first = _make_expense(app)
        second = _make_expense(app, description="Dinner")
        body = logged_in.get("/profile").get_data(as_text=True)
        assert f"/expenses/{first}/edit" in body
        assert f"/expenses/{second}/edit" in body


class TestAddPageUnchanged:
    def test_add_form_still_in_add_mode(self, logged_in):
        body = logged_in.get("/expenses/add").get_data(as_text=True)
        assert 'action="/expenses/add"' in body
        assert "Add expense" in body
        assert "Save changes" not in body
        assert "Edit Expense" not in body
