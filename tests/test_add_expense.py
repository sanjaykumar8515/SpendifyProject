from datetime import date

import pytest

from database import db

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


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


def _rows(app, user_email=None):
    with app.app_context():
        conn = db.get_db()
        try:
            if user_email:
                return conn.execute(
                    "SELECT e.* FROM expenses e JOIN users u ON u.id = e.user_id "
                    "WHERE u.email = ?",
                    (user_email,),
                ).fetchall()
            return conn.execute("SELECT * FROM expenses").fetchall()
        finally:
            conn.close()


def _user_id(app, email):
    with app.app_context():
        conn = db.get_db()
        try:
            return conn.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()["id"]
        finally:
            conn.close()


def _form(**overrides):
    data = {
        "amount": "12.50",
        "category": "Food",
        "date": "2024-05-10",
        "description": "Lunch",
    }
    data.update(overrides)
    return data


class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        r = client.get("/expenses/add")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]

    def test_post_logged_out_redirects_and_inserts_nothing(self, client, app):
        r = client.post("/expenses/add", data=_form())
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]
        assert _rows(app) == [], "No row may be inserted when logged out"


class TestForm:
    def test_get_shows_form_with_today_and_all_categories(self, logged_in):
        r = logged_in.get("/expenses/add")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert date.today().isoformat() in html, "Date should default to today"
        for cat in CATEGORIES:
            assert cat in html, f"Missing category {cat}"
        assert 'type="date"' in html


class TestSuccess:
    def test_valid_post_redirects_to_profile_and_saves_row(self, logged_in, app):
        r = logged_in.post("/expenses/add", data=_form())
        assert r.status_code == 302
        assert "/profile" in r.headers["Location"]
        rows = _rows(app, "bob@example.com")
        assert len(rows) == 1
        row = rows[0]
        assert row["amount"] == 12.5
        assert row["category"] == "Food"
        assert row["date"] == "2024-05-10"
        assert row["description"] == "Lunch"

    def test_new_row_and_totals_appear_on_profile(self, logged_in):
        logged_in.post(
            "/expenses/add",
            data=_form(amount="77.25", category="Shopping", description="UniqueThing"),
        )
        html = logged_in.get("/profile").get_data(as_text=True)
        assert "UniqueThing" in html, "Recent transactions should list new expense"
        assert "77.25" in html, "Total spent should reflect new expense"
        assert "Shopping" in html, "Category breakdown should include category"

    def test_expense_owned_by_logged_in_user_and_hidden_from_others(self, client, app):
        client.post("/login", data={"email": "bob@example.com", "password": "password123"})
        client.post("/expenses/add", data=_form(description="BobSecretItem"))
        assert len(_rows(app, "bob@example.com")) == 1
        assert _rows(app, "eve@example.com") == []
        client.get("/logout")
        client.post("/login", data={"email": "eve@example.com", "password": "password123"})
        html = client.get("/profile").get_data(as_text=True)
        assert "BobSecretItem" not in html

    def test_forged_user_id_is_ignored(self, logged_in, app):
        eve_id = _user_id(app, "eve@example.com")
        logged_in.post("/expenses/add", data=_form(user_id=str(eve_id)))
        assert len(_rows(app, "bob@example.com")) == 1
        assert _rows(app, "eve@example.com") == []

    @pytest.mark.parametrize(
        "raw,expected",
        [("0.01", 0.01), ("1000000", 1000000.0), ("12.5", 12.5), ("7", 7.0)],
    )
    def test_boundary_amounts_accepted(self, logged_in, app, raw, expected):
        r = logged_in.post("/expenses/add", data=_form(amount=raw))
        assert r.status_code == 302, f"{raw} should be accepted"
        rows = _rows(app)
        assert len(rows) == 1
        assert rows[0]["amount"] == pytest.approx(expected)

    @pytest.mark.parametrize("cat", CATEGORIES)
    def test_every_category_accepted(self, logged_in, app, cat):
        r = logged_in.post("/expenses/add", data=_form(category=cat))
        assert r.status_code == 302
        assert _rows(app)[0]["category"] == cat

    def test_future_date_accepted(self, logged_in, app):
        r = logged_in.post("/expenses/add", data=_form(date="2999-12-31"))
        assert r.status_code == 302
        assert _rows(app)[0]["date"] == "2999-12-31"

    def test_description_200_chars_accepted(self, logged_in, app):
        r = logged_in.post("/expenses/add", data=_form(description="a" * 200))
        assert r.status_code == 302
        assert len(_rows(app)[0]["description"]) == 200

    def test_empty_description_stored_as_empty_string(self, logged_in, app):
        r = logged_in.post("/expenses/add", data=_form(description=""))
        assert r.status_code == 302
        assert _rows(app)[0]["description"] == ""

    def test_missing_description_field_accepted(self, logged_in, app):
        data = _form()
        del data["description"]
        r = logged_in.post("/expenses/add", data=data)
        assert r.status_code == 302
        assert _rows(app)[0]["description"] == ""

    def test_description_is_stripped(self, logged_in, app):
        logged_in.post("/expenses/add", data=_form(description="  padded  "))
        assert _rows(app)[0]["description"] == "padded"

    def test_sql_injection_in_description_stored_literally(self, logged_in, app):
        payload = "x'); DROP TABLE expenses;--"
        r = logged_in.post("/expenses/add", data=_form(description=payload))
        assert r.status_code == 302
        assert _rows(app)[0]["description"] == payload


class TestValidation:
    @pytest.mark.parametrize(
        "amount",
        ["", "0", "-5", "abc", "1.005", "nan", "inf", "1e3", "1000000.01"],
    )
    def test_bad_amount_returns_400_no_insert(self, logged_in, app, amount):
        r = logged_in.post("/expenses/add", data=_form(amount=amount))
        assert r.status_code == 400, f"amount {amount!r} should be rejected"
        assert _rows(app) == []

    @pytest.mark.parametrize("category", ["food", "Nope", ""])
    def test_invalid_category_returns_400_no_insert(self, logged_in, app, category):
        r = logged_in.post("/expenses/add", data=_form(category=category))
        assert r.status_code == 400
        assert _rows(app) == []

    @pytest.mark.parametrize("bad_date", ["", "2024-02-30", "2024-1-5", "abc"])
    def test_invalid_date_returns_400_no_insert(self, logged_in, app, bad_date):
        r = logged_in.post("/expenses/add", data=_form(date=bad_date))
        assert r.status_code == 400
        assert _rows(app) == []

    def test_description_201_chars_returns_400_no_insert(self, logged_in, app):
        r = logged_in.post("/expenses/add", data=_form(description="a" * 201))
        assert r.status_code == 400
        assert _rows(app) == []

    def test_error_response_renders_form_with_error_message(self, logged_in):
        r = logged_in.post("/expenses/add", data=_form(amount="abc"))
        html = r.get_data(as_text=True)
        assert r.status_code == 400
        assert "<form" in html
        assert "error" in html.lower(), "An error message/banner is expected"

    def test_values_preserved_after_error(self, logged_in):
        r = logged_in.post(
            "/expenses/add",
            data=_form(
                amount="abc",
                category="Bills",
                date="2024-03-04",
                description="KeepMeText",
            ),
        )
        html = r.get_data(as_text=True)
        assert r.status_code == 400
        assert "abc" in html
        assert "2024-03-04" in html
        assert "KeepMeText" in html
        assert "Bills" in html
