import re

import pytest

from database import db, queries

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

BOB_EXPENSES = [
    (999.00, "Travel", "2026-10-05", "BobSecretTrip"),
]

ERROR_PATTERN = re.compile(r"invalid|error|must|before|not a valid", re.I)


def _insert(user_id, rows):
    conn = db.get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, *row) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        bob_id = db.create_user("Bob", "bob@example.com", "password123")
        demo_id = db.create_user("Demo User", "demo@spendly.com", "demo123")
        _insert(demo_id, DEMO_EXPENSES)
        _insert(bob_id, BOB_EXPENSES)
        flask_app.config["_TEST_DEMO_ID"] = demo_id
        flask_app.config["_TEST_BOB_ID"] = bob_id
    yield flask_app
    flask_app.config.pop("DATABASE", None)


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})


def _get(client, query=""):
    _login(client)
    return client.get("/profile" + query)


def _stat_count(page):
    return int(re.search(r'profile-stat-value">(\d+)<', page).group(1))


def _rows(page):
    return page.count("<tr>") - 1  # minus header row


def _pcts(page):
    return [int(p) for p in re.findall(r'profile-cat-pct">(\d+)%', page)]


# ---------------------------------------------------------------- unfiltered

class TestUnfiltered:
    def test_no_params_shows_all_data(self, client):
        resp = _get(client)
        page = resp.data.decode()
        assert resp.status_code == 200
        assert "₹380.24" in page
        assert _stat_count(page) == 8
        assert _rows(page) == 8
        assert "Bills" in page

    @pytest.mark.parametrize("query", [
        "?date_from=&date_to=",
        "?date_from=",
        "?date_to=",
    ])
    def test_empty_params_behave_as_unfiltered(self, client, query):
        resp = _get(client, query)
        page = resp.data.decode()
        assert resp.status_code == 200
        assert "₹380.24" in page
        assert _stat_count(page) == 8
        assert _rows(page) == 8
        assert not ERROR_PATTERN.search(
            "".join(re.findall(r'class="[^"]*error[^"]*"', page))
        ), "No error should be shown for empty params"

    def test_unfiltered_keeps_original_empty_wording_for_new_user(self, client):
        _login(client, "bob@example.com", "password123")
        page = client.get("/profile?date_from=2026-01-01&date_to=2026-01-02")
        assert "No expenses in this date range." in page.data.decode()
        # Bob with no filter: has expenses, so a user without any is needed
        with client.application.app_context():
            conn = db.get_db()
            try:
                conn.execute("DELETE FROM expenses WHERE user_id = ?",
                             (client.application.config["_TEST_BOB_ID"],))
                conn.commit()
            finally:
                conn.close()
        page = client.get("/profile").data.decode()
        assert "No expenses yet" in page
        assert "No expenses in this date range." not in page


# ------------------------------------------------------------- filtered data

class TestFilteredRange:
    def test_both_bounds_update_all_sections(self, client):
        # 2026-10-03..2026-10-08 -> bus pass 45 + electricity 120 + pharmacy 30
        resp = _get(client, "?date_from=2026-10-03&date_to=2026-10-08")
        page = resp.data.decode()
        assert resp.status_code == 200
        assert "₹195.00" in page
        assert _stat_count(page) == 3
        assert _rows(page) == 3
        assert "Electricity bill" in page and "Pharmacy" in page
        assert "Monthly bus pass" in page
        for absent in ("Lunch at cafe", "Movie tickets", "New shoes",
                       "Miscellaneous", "Groceries"):
            assert absent not in page, f"{absent} is outside the range"
        assert page.count('class="profile-cat-row"') == 3
        assert "₹380.24" not in page

    def test_top_category_matches_range(self, client):
        page = _get(client, "?date_from=2026-10-03&date_to=2026-10-08").data.decode()
        # Bills (120) is the top category in this range
        top = re.search(r"Top Category.*?profile-stat-value\">([^<]+)<",
                        page, re.S | re.I)
        assert top is not None, "Top category stat should be rendered"
        assert top.group(1).strip() == "Bills"

    def test_bounds_are_inclusive(self, client):
        page = _get(client, "?date_from=2026-10-05&date_to=2026-10-05").data.decode()
        assert _stat_count(page) == 1
        assert "Electricity bill" in page
        assert "₹120.00" in page

    def test_inclusive_edges_with_adjacent_days(self, client):
        page = _get(client, "?date_from=2026-10-01&date_to=2026-10-03").data.decode()
        assert _stat_count(page) == 2
        assert "Lunch at cafe" in page and "Monthly bus pass" in page
        assert "₹57.50" in page

    def test_only_date_from(self, client):
        # 89.99 + 15.00 + 42.75
        page = _get(client, "?date_from=2026-10-15").data.decode()
        assert "₹147.74" in page
        assert _stat_count(page) == 3
        assert "New shoes" in page and "Groceries" in page
        assert "Pharmacy" not in page and "Lunch at cafe" not in page

    def test_only_date_to(self, client):
        # 12.50 + 45.00
        page = _get(client, "?date_to=2026-10-03").data.decode()
        assert "₹57.50" in page
        assert _stat_count(page) == 2
        assert "Lunch at cafe" in page and "Monthly bus pass" in page
        assert "Groceries" not in page

    def test_filtered_percentages_sum_to_100(self, client):
        for query in ("?date_from=2026-10-03&date_to=2026-10-15",
                      "?date_from=2026-10-08",
                      "?date_to=2026-10-11"):
            page = _get(client, query).data.decode()
            pcts = _pcts(page)
            assert pcts, f"Expected a breakdown for {query}"
            assert sum(pcts) == 100, f"{query}: percentages {pcts} != 100"

    def test_same_range_consistent_across_sections(self, client):
        page = _get(client, "?date_from=2026-10-11&date_to=2026-10-19").data.decode()
        # Movie 25 + shoes 89.99 + misc 15 = 129.99
        assert "₹129.99" in page
        assert _stat_count(page) == 3
        assert _rows(page) == 3
        assert page.count('class="profile-cat-row"') == 3

    def test_filtered_rows_newest_first(self, client):
        page = _get(client, "?date_from=2026-10-03&date_to=2026-10-08").data.decode()
        order = ["Pharmacy", "Electricity bill", "Monthly bus pass"]
        positions = [page.index(d) for d in order]
        assert positions == sorted(positions)

    def test_transaction_limit_of_10_kept_within_range(self, client, app):
        with app.app_context():
            _insert(app.config["_TEST_DEMO_ID"],
                    [(1.00, "Food", f"2026-11-{d:02d}", f"Bulk{d:02d}")
                     for d in range(1, 13)])
        page = _get(client, "?date_from=2026-11-01&date_to=2026-11-30").data.decode()
        assert _rows(page) == 10
        assert _stat_count(page) == 12, "Count stat covers the whole range"
        assert "₹12.00" in page


# ---------------------------------------------------------------- empty range

class TestEmptyRange:
    def test_empty_range_shows_zero_state(self, client):
        resp = _get(client, "?date_from=2025-01-01&date_to=2025-01-31")
        page = resp.data.decode()
        assert resp.status_code == 200
        assert "₹0.00" in page
        assert _stat_count(page) == 0
        assert "—" in page
        assert "No expenses in this date range." in page
        assert 'class="profile-cat-row"' not in page
        assert "Groceries" not in page

    def test_empty_range_after_all_data(self, client):
        page = _get(client, "?date_from=2030-01-01").data.decode()
        assert "No expenses in this date range." in page
        assert "₹0.00" in page


# --------------------------------------------------------------- form / UI

class TestFilterForm:
    def test_form_present_with_expected_fields(self, client):
        page = _get(client).data.decode()
        assert re.search(r'<form[^>]*method="get"[^>]*action="/profile"', page, re.I) \
            or re.search(r'<form[^>]*action="/profile"[^>]*method="get"', page, re.I), \
            "GET filter form posting to /profile expected"
        assert re.search(r'<input[^>]*type="date"[^>]*name="date_from"', page) \
            or re.search(r'<input[^>]*name="date_from"[^>]*type="date"', page)
        assert re.search(r'<input[^>]*type="date"[^>]*name="date_to"', page) \
            or re.search(r'<input[^>]*name="date_to"[^>]*type="date"', page)
        assert "Apply" in page
        assert "Clear" in page

    def test_clear_link_points_to_unfiltered_profile(self, client):
        page = _get(client, "?date_from=2026-10-03").data.decode()
        assert re.search(r'<a[^>]*href="/profile"[^>]*>\s*Clear', page), \
            "Clear link should go to plain /profile"

    def test_inputs_repopulated_with_submitted_values(self, client):
        page = _get(client, "?date_from=2026-10-03&date_to=2026-10-08").data.decode()
        assert 'value="2026-10-03"' in page
        assert 'value="2026-10-08"' in page

    def test_inputs_not_prefilled_when_unfiltered(self, client):
        page = _get(client).data.decode()
        assert 'value="2026-' not in page

    def test_following_clear_returns_all_data(self, client):
        _login(client)
        client.get("/profile?date_from=2026-10-03&date_to=2026-10-08")
        page = client.get("/profile").data.decode()
        assert "₹380.24" in page and _stat_count(page) == 8


# ------------------------------------------------------------ invalid input

class TestInvalidInput:
    @pytest.mark.parametrize("query", [
        "?date_from=not-a-date",
        "?date_to=not-a-date",
        "?date_from=2026-02-01&date_to=2026-01-01",
        "?date_from=2026-13-45",
        "?date_from=10/03/2026",
        "?date_from=2026-10-03&date_to=garbage",
    ])
    def test_invalid_returns_200_unfiltered_with_error(self, client, query):
        resp = _get(client, query)
        page = resp.data.decode()
        assert resp.status_code == 200
        assert "₹380.24" in page, f"{query}: data must be unfiltered"
        assert _stat_count(page) == 8
        assert _rows(page) == 8
        assert "No expenses in this date range." not in page
        assert ERROR_PATTERN.search(page), f"{query}: expected an inline error"

    def test_valid_input_shows_no_error_element(self, client):
        page = _get(client, "?date_from=2026-10-03&date_to=2026-10-08").data.decode()
        assert not re.search(r'class="[^"]*error[^"]*"', page), \
            "No error markup expected for valid input"

    def test_from_equal_to_to_is_valid(self, client):
        page = _get(client, "?date_from=2026-10-05&date_to=2026-10-05").data.decode()
        assert _stat_count(page) == 1

    def test_reversed_range_does_not_apply_partial_filter(self, client):
        page = _get(client, "?date_from=2026-10-20&date_to=2026-10-02").data.decode()
        assert _stat_count(page) == 8

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE expenses; --",
        "2026-10-01' OR '1'='1",
        "%27%20OR%201%3D1--",
    ])
    def test_sql_injection_attempts_are_harmless(self, client, app, payload):
        resp = _get(client, "?date_from=" + payload)
        assert resp.status_code == 200
        page = resp.data.decode()
        assert "BobSecretTrip" not in page
        assert _stat_count(page) == 8
        with app.app_context():
            conn = db.get_db()
            try:
                n = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
            finally:
                conn.close()
        assert n == len(DEMO_EXPENSES) + len(BOB_EXPENSES), "expenses table intact"


# ------------------------------------------------------------ access control

class TestAccess:
    @pytest.mark.parametrize("query", [
        "?date_from=2026-01-01",
        "?date_from=2026-01-01&date_to=2026-12-31",
        "?date_from=bad",
    ])
    def test_unauthenticated_redirects_to_login(self, client, query):
        resp = client.get("/profile" + query)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/login")

    def test_other_users_expenses_never_in_filtered_results(self, client):
        # Bob's 999.00 expense falls on 2026-10-05, inside this range.
        page = _get(client, "?date_from=2026-10-01&date_to=2026-10-31").data.decode()
        assert "BobSecretTrip" not in page
        assert "₹999.00" not in page
        assert "₹380.24" in page
        assert _stat_count(page) == 8

    def test_other_user_sees_only_own_filtered_data(self, client):
        _login(client, "bob@example.com", "password123")
        page = client.get("/profile?date_from=2026-10-01&date_to=2026-10-31").data.decode()
        assert "BobSecretTrip" in page
        assert "₹999.00" in page
        assert _stat_count(page) == 1
        assert "Electricity bill" not in page

    def test_filter_does_not_widen_access_without_user_rows(self, client):
        _login(client, "bob@example.com", "password123")
        page = client.get("/profile?date_from=2026-10-06&date_to=2026-10-31").data.decode()
        assert "No expenses in this date range." in page
        assert "Groceries" not in page and "Pharmacy" not in page


# ------------------------------------------------- query helper contract

class TestQueryHelpers:
    def test_helpers_default_params_unfiltered(self, app):
        uid = app.config["_TEST_DEMO_ID"]
        with app.app_context():
            stats = queries.get_summary_stats(uid)
            txns = queries.get_recent_transactions(uid)
            cats = queries.get_category_breakdown(uid)
        assert stats is not None
        assert len(txns) == 8
        assert len(cats) == 7

    def test_helpers_accept_date_keywords_and_scope_by_user(self, app):
        uid = app.config["_TEST_DEMO_ID"]
        with app.app_context():
            txns = queries.get_recent_transactions(
                uid, date_from="2026-10-03", date_to="2026-10-08")
            cats = queries.get_category_breakdown(
                uid, date_from="2026-10-03", date_to="2026-10-08")
            stats = queries.get_summary_stats(
                uid, date_from="2026-10-03", date_to="2026-10-08")
        assert len(txns) == 3
        assert len(cats) == 3
        assert "195" in str(stats)

    def test_helpers_filter_only_one_side(self, app):
        uid = app.config["_TEST_DEMO_ID"]
        with app.app_context():
            after = queries.get_recent_transactions(uid, date_from="2026-10-19")
            before = queries.get_recent_transactions(uid, date_to="2026-10-01")
        assert len(after) == 2
        assert len(before) == 1
