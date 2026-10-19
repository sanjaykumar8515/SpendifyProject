import re

import pytest

from database import db
from database.queries import (
    get_category_breakdown,
    get_recent_transactions,
    get_summary_stats,
)

# (amount, category, iso_date, description)
DEMO_EXPENSES = [
    (12.50, "Food", "2026-10-01", "Lunch at cafe"),
    (45.00, "Transport", "2026-10-03", "Monthly bus pass"),
    (120.00, "Bills", "2026-10-05", "Electricity bill"),
    (30.00, "Health", "2026-10-08", "Pharmacy"),
    (25.00, "Entertainment", "2026-10-11", "Movie tickets"),
    (89.99, "Shopping", "2026-10-15", "New shoes"),
    (15.00, "Other", "2026-10-19", "Miscellaneous"),
    (42.75, "Food", "2026-10-24", "Groceries"),
]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        db.create_user("Demo User", "demo@spendly.com", "demo123")
        db.create_user("Other User", "other@example.com", "password123")
        conn = db.get_db()
        try:
            demo_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
            ).fetchone()["id"]
            other_id = conn.execute(
                "SELECT id FROM users WHERE email = ?", ("other@example.com",)
            ).fetchone()["id"]
            conn.executemany(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                [(demo_id, *row) for row in DEMO_EXPENSES],
            )
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (other_id, 999.0, "Food", "2026-10-10", "Not yours"),
            )
            conn.commit()
        finally:
            conn.close()
        flask_app.demo_id = demo_id
        yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    return client


def _stat_values(page):
    return re.findall(r'profile-stat-value">([^<]*)<', page)


# ------------------------------------------------------------------ #
# Query helpers                                                       #
# ------------------------------------------------------------------ #

class TestQueryHelpers:
    def test_no_range_returns_everything(self, app):
        stats = get_summary_stats(app.demo_id)
        assert stats["transaction_count"] == 8
        assert stats["total_spent"] == 380.24

    def test_from_only(self, app):
        stats = get_summary_stats(app.demo_id, date_from="2026-10-15")
        assert stats["transaction_count"] == 3
        assert stats["total_spent"] == 147.74

    def test_to_only(self, app):
        stats = get_summary_stats(app.demo_id, date_to="2026-10-05")
        assert stats["transaction_count"] == 3
        assert stats["total_spent"] == 177.5
        assert stats["top_category"] == "Bills"

    def test_both_bounds_are_inclusive(self, app):
        rows = get_recent_transactions(
            app.demo_id, date_from="2026-10-03", date_to="2026-10-08"
        )
        assert [r["date"] for r in rows] == ["2026-10-08", "2026-10-05", "2026-10-03"]

    def test_empty_range(self, app):
        kwargs = {"date_from": "2027-01-01", "date_to": "2027-01-31"}
        assert get_summary_stats(app.demo_id, **kwargs) == {
            "total_spent": 0,
            "transaction_count": 0,
            "top_category": "—",
        }
        assert get_recent_transactions(app.demo_id, **kwargs) == []
        assert get_category_breakdown(app.demo_id, **kwargs) == []

    def test_breakdown_percentages_sum_to_100(self, app):
        breakdown = get_category_breakdown(
            app.demo_id, date_from="2026-10-01", date_to="2026-10-11"
        )
        assert breakdown
        assert sum(item["pct"] for item in breakdown) == 100

    def test_limit_still_applies_within_range(self, app):
        rows = get_recent_transactions(app.demo_id, limit=2, date_from="2026-10-01")
        assert len(rows) == 2

    def test_other_users_rows_never_leak(self, app):
        kwargs = {"date_from": "2026-10-10", "date_to": "2026-10-10"}
        assert get_recent_transactions(app.demo_id, **kwargs) == []
        assert get_summary_stats(app.demo_id, **kwargs)["transaction_count"] == 0

    def test_values_are_parameterised(self, app):
        # Treated as a plain string (sorts before any digit), never as SQL:
        # the other user's row must not be pulled in by an injected OR clause.
        stats = get_summary_stats(app.demo_id, date_from="' OR 1=1 --")
        assert stats["transaction_count"] == 8
        assert get_summary_stats(app.demo_id, date_to="' OR 1=1 --")["transaction_count"] == 0


# ------------------------------------------------------------------ #
# Route                                                               #
# ------------------------------------------------------------------ #

class TestProfileRoute:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/profile?date_from=2026-01-01")
        assert resp.status_code == 302
        assert resp.headers["Location"] == "/login"

    def test_no_params_is_unfiltered(self, logged_in):
        page = logged_in.get("/profile").get_data(as_text=True)
        assert "₹380.24" in page
        assert page.count("<tr>") - 1 == 8
        assert "profile-filter-error" not in page

    def test_filter_form_present(self, logged_in):
        page = logged_in.get("/profile").get_data(as_text=True)
        assert 'name="date_from"' in page
        assert 'name="date_to"' in page
        assert 'href="/profile"' in page
        assert 'style="' not in page

    def test_range_updates_every_section(self, logged_in):
        page = logged_in.get(
            "/profile?date_from=2026-10-01&date_to=2026-10-05"
        ).get_data(as_text=True)
        assert _stat_values(page) == ["₹177.50", "3", "Bills"]
        assert page.count("<tr>") - 1 == 3
        assert page.count('class="profile-cat-row"') == 3
        assert "Pharmacy" not in page

    def test_from_only_filters_one_side(self, logged_in):
        page = logged_in.get("/profile?date_from=2026-10-19").get_data(as_text=True)
        assert _stat_values(page)[1] == "2"

    def test_to_only_filters_one_side(self, logged_in):
        page = logged_in.get("/profile?date_to=2026-10-01").get_data(as_text=True)
        assert _stat_values(page)[1] == "1"

    def test_inputs_keep_submitted_values(self, logged_in):
        page = logged_in.get(
            "/profile?date_from=2026-10-01&date_to=2026-10-05"
        ).get_data(as_text=True)
        assert 'value="2026-10-01"' in page
        assert 'value="2026-10-05"' in page

    def test_empty_range_shows_empty_state(self, logged_in):
        page = logged_in.get(
            "/profile?date_from=2027-01-01&date_to=2027-01-31"
        ).get_data(as_text=True)
        assert _stat_values(page) == ["₹0.00", "0", "—"]
        assert "No expenses in this date range." in page
        assert 'class="profile-cat-row"' not in page

    def test_unparseable_date_shows_error_and_unfiltered_data(self, logged_in):
        resp = logged_in.get("/profile?date_from=not-a-date")
        page = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "profile-filter-error" in page
        assert "₹380.24" in page

    def test_reversed_range_shows_error_and_unfiltered_data(self, logged_in):
        resp = logged_in.get("/profile?date_from=2026-02-01&date_to=2026-01-01")
        page = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "profile-filter-error" in page
        assert "₹380.24" in page

    def test_other_users_expenses_not_shown(self, logged_in):
        page = logged_in.get(
            "/profile?date_from=2026-10-10&date_to=2026-10-10"
        ).get_data(as_text=True)
        assert "Not yours" not in page
        assert "₹999.00" not in page


# ------------------------------------------------------------------ #
# Quick presets                                                       #
# ------------------------------------------------------------------ #

class TestPresets:
    def test_shift_months_clamps_to_month_end(self):
        from datetime import date

        import app as app_module

        assert app_module.shift_months(date(2026, 8, 31), 3) == date(2026, 5, 31)
        assert app_module.shift_months(date(2026, 5, 31), 3) == date(2026, 2, 28)
        assert app_module.shift_months(date(2026, 2, 10), 6) == date(2025, 8, 10)

    def test_preset_labels_are_shown(self, logged_in):
        page = logged_in.get("/profile").get_data(as_text=True)
        for label in ("All Time", "This Month", "Last 3 Months", "Last 6 Months"):
            assert label in page

    def test_all_time_active_by_default(self, logged_in):
        page = logged_in.get("/profile").get_data(as_text=True)
        assert page.count("profile-preset-active") == 1
        assert re.search(r'profile-preset-active"[^>]*>\s*All Time', page)

    def test_preset_links_carry_date_params(self, logged_in):
        page = logged_in.get("/profile").get_data(as_text=True)
        assert page.count("date_from=") >= 3

    def test_matching_range_marks_preset_active(self, logged_in):
        import calendar
        from datetime import date

        today = date.today()
        last = calendar.monthrange(today.year, today.month)[1]
        url = (
            f"/profile?date_from={today.replace(day=1).isoformat()}"
            f"&date_to={today.replace(day=last).isoformat()}"
        )
        page = logged_in.get(url).get_data(as_text=True)
        assert re.search(r'profile-preset-active"[^>]*>\s*This Month', page)
