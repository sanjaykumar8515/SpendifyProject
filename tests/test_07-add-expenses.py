"""Tests for Step 7: Add Expenses (.claude/specs/07-add-expenses.md)."""
from datetime import date

import pytest

from database import db

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        db.create_user("Alice", "alice@example.com", "password123")
        db.create_user("Bob", "bob@example.com", "password123")
        yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, email="alice@example.com", password="password123"):
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture
def logged_in(client):
    _login(client)
    return client


def _user_id(app, email):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        ).fetchone()["id"]
    finally:
        conn.close()


def _expenses(app):
    conn = db.get_db()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT user_id, amount, category, date, description "
                "FROM expenses ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()


def _valid(**overrides):
    data = {
        "amount": "12.50",
        "category": "Food",
        "date": "2026-10-01",
        "description": "Lunch",
    }
    data.update(overrides)
    return data


class TestAuthGuard:
    def test_get_logged_out_redirects_to_login(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_post_logged_out_redirects_and_inserts_nothing(self, client, app):
        resp = client.post("/expenses/add", data=_valid())
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _expenses(app) == []


class TestForm:
    def test_get_logged_in_shows_form(self, logged_in):
        resp = logged_in.get("/expenses/add")
        assert resp.status_code == 200
        for field in (b'name="amount"', b'name="category"', b'name="date"',
                      b'name="description"'):
            assert field in resp.data, f"Missing field {field!r}"

    def test_form_lists_all_seven_categories(self, logged_in):
        html = logged_in.get("/expenses/add").data.decode()
        for cat in CATEGORIES:
            assert cat in html, f"Category {cat} missing from form"

    def test_form_date_defaults_to_today(self, logged_in):
        html = logged_in.get("/expenses/add").data.decode()
        assert date.today().isoformat() in html

    def test_form_has_cancel_link_to_profile(self, logged_in):
        html = logged_in.get("/expenses/add").data.decode()
        assert 'href="/profile"' in html


class TestCreateSuccess:
    def test_valid_post_redirects_to_profile(self, logged_in):
        resp = logged_in.post("/expenses/add", data=_valid())
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/profile")

    def test_valid_post_inserts_row_for_logged_in_user(self, logged_in, app):
        logged_in.post("/expenses/add", data=_valid())
        rows = _expenses(app)
        assert len(rows) == 1
        row = rows[0]
        assert row["user_id"] == _user_id(app, "alice@example.com")
        assert row["amount"] == 12.5
        assert row["category"] == "Food"
        assert row["date"] == "2026-10-01"
        assert row["description"] == "Lunch"

    def test_new_expense_appears_on_profile(self, logged_in):
        logged_in.post(
            "/expenses/add",
            data=_valid(amount="77.25", description="Unique zebra purchase"),
        )
        html = logged_in.get("/profile").data.decode()
        assert "Unique zebra purchase" in html
        assert "77.25" in html, "Total spent / transaction should reflect amount"

    def test_category_breakdown_reflects_expense(self, logged_in):
        logged_in.post("/expenses/add", data=_valid(category="Health"))
        html = logged_in.get("/profile").data.decode()
        assert "Health" in html

    def test_expense_not_visible_to_other_user(self, client, app):
        _login(client)
        client.post("/expenses/add", data=_valid(description="Alice secret"))
        client.get("/logout")
        _login(client, "bob@example.com")
        html = client.get("/profile").data.decode()
        assert "Alice secret" not in html

    def test_empty_description_accepted(self, logged_in, app):
        resp = logged_in.post("/expenses/add", data=_valid(description=""))
        assert resp.status_code == 302
        assert len(_expenses(app)) == 1

    def test_description_missing_field_accepted(self, logged_in, app):
        data = _valid()
        del data["description"]
        resp = logged_in.post("/expenses/add", data=data)
        assert resp.status_code == 302
        assert len(_expenses(app)) == 1

    def test_description_is_stripped(self, logged_in, app):
        logged_in.post("/expenses/add", data=_valid(description="  padded  "))
        assert _expenses(app)[0]["description"] == "padded"

    def test_description_exactly_200_chars_accepted(self, logged_in, app):
        resp = logged_in.post("/expenses/add", data=_valid(description="a" * 200))
        assert resp.status_code == 302
        assert len(_expenses(app)) == 1

    @pytest.mark.parametrize("category", CATEGORIES)
    def test_every_category_accepted(self, logged_in, app, category):
        resp = logged_in.post("/expenses/add", data=_valid(category=category))
        assert resp.status_code == 302
        assert _expenses(app)[0]["category"] == category

    @pytest.mark.parametrize(
        "amount,expected",
        [("0.01", 0.01), ("5", 5.0), ("5.5", 5.5), ("1000000", 1000000.0),
         ("99.99", 99.99)],
    )
    def test_boundary_amounts_accepted(self, logged_in, app, amount, expected):
        resp = logged_in.post("/expenses/add", data=_valid(amount=amount))
        assert resp.status_code == 302
        assert _expenses(app)[0]["amount"] == expected

    def test_future_date_allowed(self, logged_in, app):
        resp = logged_in.post("/expenses/add", data=_valid(date="2099-12-31"))
        assert resp.status_code == 302
        assert _expenses(app)[0]["date"] == "2099-12-31"

    def test_leap_day_accepted(self, logged_in, app):
        resp = logged_in.post("/expenses/add", data=_valid(date="2028-02-29"))
        assert resp.status_code == 302
        assert len(_expenses(app)) == 1


class TestValidationErrors:
    @pytest.mark.parametrize(
        "amount",
        ["", "   ", "0", "0.00", "-5", "-0.01", "abc", "12abc", "1.234",
         "10.001", "1000000.01", "2000000", "nan", "inf", "-inf"],
    )
    def test_invalid_amount_returns_400_no_insert(self, logged_in, app, amount):
        resp = logged_in.post("/expenses/add", data=_valid(amount=amount))
        assert resp.status_code == 400, f"amount={amount!r}"
        assert _expenses(app) == []

    def test_missing_amount_field_returns_400(self, logged_in, app):
        data = _valid()
        del data["amount"]
        resp = logged_in.post("/expenses/add", data=data)
        assert resp.status_code == 400
        assert _expenses(app) == []

    @pytest.mark.parametrize(
        "category", ["", "Groceries", "food", "FOOD", "Food; DROP TABLE expenses"]
    )
    def test_invalid_category_returns_400_no_insert(self, logged_in, app, category):
        resp = logged_in.post("/expenses/add", data=_valid(category=category))
        assert resp.status_code == 400, f"category={category!r}"
        assert _expenses(app) == []

    def test_missing_category_field_returns_400(self, logged_in, app):
        data = _valid()
        del data["category"]
        resp = logged_in.post("/expenses/add", data=data)
        assert resp.status_code == 400
        assert _expenses(app) == []

    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "2026-13-01", "2026-02-30", "2027-02-29",
         "01/10/2026", "2026/10/01", "2026-1-1", "20261001"],
    )
    def test_invalid_date_returns_400_no_insert(self, logged_in, app, bad_date):
        resp = logged_in.post("/expenses/add", data=_valid(date=bad_date))
        assert resp.status_code == 400, f"date={bad_date!r}"
        assert _expenses(app) == []

    def test_missing_date_field_returns_400(self, logged_in, app):
        data = _valid()
        del data["date"]
        resp = logged_in.post("/expenses/add", data=data)
        assert resp.status_code == 400
        assert _expenses(app) == []

    def test_description_over_200_chars_returns_400(self, logged_in, app):
        resp = logged_in.post("/expenses/add", data=_valid(description="a" * 201))
        assert resp.status_code == 400
        assert _expenses(app) == []

    def test_error_response_shows_a_message(self, logged_in):
        resp = logged_in.post("/expenses/add", data=_valid(amount="-1"))
        assert resp.status_code == 400
        # form is re-rendered (not a bare string)
        assert b'name="amount"' in resp.data
        assert b"<html" in resp.data.lower()

    def test_submitted_values_preserved_after_error(self, logged_in):
        resp = logged_in.post(
            "/expenses/add",
            data=_valid(
                amount="abc",
                category="Transport",
                date="2026-05-06",
                description="Keep me around",
            ),
        )
        html = resp.data.decode()
        assert resp.status_code == 400
        assert "abc" in html
        assert "2026-05-06" in html
        assert "Keep me around" in html
        assert "Transport" in html

    def test_valid_other_fields_preserved_when_category_invalid(self, logged_in):
        resp = logged_in.post(
            "/expenses/add",
            data=_valid(category="Bogus", amount="33.30", description="Remember"),
        )
        html = resp.data.decode()
        assert resp.status_code == 400
        assert "33.30" in html
        assert "Remember" in html


class TestSecurity:
    def test_forged_user_id_ignored(self, logged_in, app):
        bob_id = _user_id(app, "bob@example.com")
        alice_id = _user_id(app, "alice@example.com")
        resp = logged_in.post("/expenses/add", data=_valid(user_id=str(bob_id)))
        assert resp.status_code == 302
        rows = _expenses(app)
        assert len(rows) == 1
        assert rows[0]["user_id"] == alice_id
        assert rows[0]["user_id"] != bob_id

    def test_sql_injection_in_description_stored_literally(self, logged_in, app):
        payload = "x'); DROP TABLE expenses; --"
        resp = logged_in.post("/expenses/add", data=_valid(description=payload))
        assert resp.status_code == 302
        rows = _expenses(app)
        assert len(rows) == 1
        assert rows[0]["description"] == payload

    def test_amount_stored_rounded_to_two_decimals(self, logged_in, app):
        logged_in.post("/expenses/add", data=_valid(amount="10.10"))
        assert _expenses(app)[0]["amount"] == 10.1


class TestCreateExpenseHelper:
    def test_create_expense_inserts_and_returns_id(self, app):
        uid = _user_id(app, "alice@example.com")
        new_id = db.create_expense(uid, 20.0, "Bills", "2026-10-02", "Power")
        assert isinstance(new_id, int) and new_id > 0
        rows = _expenses(app)
        assert rows == [
            {
                "user_id": uid,
                "amount": 20.0,
                "category": "Bills",
                "date": "2026-10-02",
                "description": "Power",
            }
        ]
