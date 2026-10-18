import pytest

from database import db, queries


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "seed.db"))
    import app as app_module

    flask_app = app_module.app
    flask_app.config.update(TESTING=True, DATABASE=str(tmp_path / "test.db"))
    with flask_app.app_context():
        db.init_db()
        yield flask_app
    flask_app.config.pop("DATABASE", None)


def _add_expenses(user_id, rows):
    """rows: iterable of (amount, category, iso_date, description)."""
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
def empty_user(app):
    return db.create_user("Empty", "empty@example.com", "password123")


@pytest.fixture
def other_user(app):
    """A second user with expenses, used to check per-user isolation."""
    user_id = db.create_user("Other", "other@example.com", "password123")
    _add_expenses(user_id, [(999.0, "Other", "2026-01-01", "Not yours")])
    return user_id


@pytest.fixture
def user_with_expenses(app):
    user_id = db.create_user("Alice", "alice@example.com", "password123")
    _add_expenses(user_id, [
        (12.50, "Food", "2026-10-01", "Lunch at cafe"),
        (45.00, "Transport", "2026-10-03", "Monthly bus pass"),
        (120.00, "Bills", "2026-10-05", "Electricity bill"),
        (42.75, "Food", "2026-10-24", "Groceries"),
    ])
    return user_id


class TestGetUserById:
    def test_valid_user(self, user_with_expenses):
        user = queries.get_user_by_id(user_with_expenses)
        assert user["name"] == "Alice"
        assert user["email"] == "alice@example.com"
        assert len(user["member_since"].split()) == 2  # "Month YYYY"

    def test_missing_user(self, app):
        assert queries.get_user_by_id(9999) is None


# === BEGIN TestGetRecentTransactions (subagent A) ===
class TestGetRecentTransactions:
    def test_newest_first(self, user_with_expenses):
        rows = queries.get_recent_transactions(user_with_expenses)
        assert [r["date"] for r in rows] == [
            "2026-10-24", "2026-10-05", "2026-10-03", "2026-10-01"
        ]

    def test_same_date_tie_broken_by_id_desc(self, empty_user):
        _add_expenses(empty_user, [
            (1.0, "Food", "2026-10-10", "first"),
            (2.0, "Food", "2026-10-10", "second"),
        ])
        rows = queries.get_recent_transactions(empty_user)
        assert [r["description"] for r in rows] == ["second", "first"]

    def test_key_set_and_types(self, user_with_expenses):
        row = queries.get_recent_transactions(user_with_expenses)[0]
        assert set(row) == {"date", "description", "category", "amount"}
        assert isinstance(row["amount"], float)
        assert row["amount"] == 42.75

    def test_limit_respected(self, user_with_expenses):
        rows = queries.get_recent_transactions(user_with_expenses, limit=2)
        assert len(rows) == 2
        assert rows[0]["description"] == "Groceries"

    def test_empty_user_returns_empty_list(self, empty_user):
        assert queries.get_recent_transactions(empty_user) == []

    def test_other_users_rows_excluded(self, user_with_expenses, other_user):
        rows = queries.get_recent_transactions(user_with_expenses)
        assert all(r["description"] != "Not yours" for r in rows)
        assert len(rows) == 4
# === END TestGetRecentTransactions ===


# === BEGIN TestGetSummaryStats (subagent B) ===
class TestGetSummaryStats:
    def test_correct_values(self, user_with_expenses):
        stats = queries.get_summary_stats(user_with_expenses)
        assert stats["total_spent"] == pytest.approx(220.25)
        assert stats["transaction_count"] == 4
        assert stats["top_category"] == "Bills"

    def test_empty_user(self, empty_user):
        assert queries.get_summary_stats(empty_user) == {
            "total_spent": 0,
            "transaction_count": 0,
            "top_category": "—",
        }

    def test_tie_break_is_alphabetical(self, empty_user):
        _add_expenses(empty_user, [
            (50.0, "Zebra", "2026-10-01", "z"),
            (50.0, "Alpha", "2026-10-02", "a"),
            (50.0, "Middle", "2026-10-03", "m"),
        ])
        assert queries.get_summary_stats(empty_user)["top_category"] == "Alpha"

    def test_other_users_data_excluded(self, user_with_expenses, other_user):
        stats = queries.get_summary_stats(user_with_expenses)
        assert stats["total_spent"] == pytest.approx(220.25)
        assert stats["transaction_count"] == 4
        assert stats["top_category"] != "Other"
# === END TestGetSummaryStats ===


# === BEGIN TestGetCategoryBreakdown (subagent C) ===
class TestGetCategoryBreakdown:
    def test_ordered_by_amount_desc_and_aggregated(self, user_with_expenses):
        result = queries.get_category_breakdown(user_with_expenses)
        assert [c["name"] for c in result] == ["Bills", "Food", "Transport"]
        food = next(c for c in result if c["name"] == "Food")
        assert food["amount"] == 55.25

    def test_pct_are_ints_summing_to_100(self, user_with_expenses):
        result = queries.get_category_breakdown(user_with_expenses)
        assert all(isinstance(c["pct"], int) for c in result)
        assert all(isinstance(c["amount"], float) for c in result)
        assert sum(c["pct"] for c in result) == 100

    def test_three_equal_categories_sum_to_100(self, app, empty_user):
        _add_expenses(empty_user, [
            (10.0, "A", "2026-10-01", ""),
            (10.0, "B", "2026-10-02", ""),
            (10.0, "C", "2026-10-03", ""),
        ])
        result = queries.get_category_breakdown(empty_user)
        assert [c["name"] for c in result] == ["A", "B", "C"]
        assert sorted(c["pct"] for c in result) == [33, 33, 34]
        assert sum(c["pct"] for c in result) == 100

    def test_empty_user_returns_empty_list(self, empty_user):
        assert queries.get_category_breakdown(empty_user) == []

    def test_other_user_excluded(self, user_with_expenses, other_user):
        result = queries.get_category_breakdown(user_with_expenses)
        assert "Other" not in [c["name"] for c in result]
        assert sum(c["amount"] for c in result) == pytest.approx(220.25)
# === END TestGetCategoryBreakdown ===
