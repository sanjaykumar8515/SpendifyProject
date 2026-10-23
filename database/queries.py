from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    try:
        member_since = datetime.strptime(row["created_at"][:10], "%Y-%m-%d").strftime("%B %Y")
    except (TypeError, ValueError):
        member_since = ""
    return {"name": row["name"], "email": row["email"], "member_since": member_since}


def _date_clause(date_from, date_to):
    clause = ""
    params = []
    if date_from:
        clause += " AND date >= ?"
        params.append(date_from)
    if date_to:
        clause += " AND date <= ?"
        params.append(date_to)
    return clause, params


# === BEGIN get_recent_transactions (subagent A) ===
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    date_sql, date_params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + date_sql +
            " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *date_params, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row["id"],
            "date": row["date"],
            "description": row["description"],
            "category": row["category"],
            "amount": round(float(row["amount"]), 2),
        }
        for row in rows
    ]
# === END get_recent_transactions ===


# === BEGIN get_summary_stats (subagent B) ===
def get_summary_stats(user_id, date_from=None, date_to=None):
    date_sql, date_params = _date_clause(date_from, date_to)
    params = (user_id, *date_params)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total_spent, COUNT(*) AS transaction_count "
            "FROM expenses WHERE user_id = ?" + date_sql,
            params,
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + date_sql +
            " GROUP BY category ORDER BY SUM(amount) DESC, category ASC"
            " LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()
    return {
        "total_spent": round(float(totals["total_spent"]), 2),
        "transaction_count": int(totals["transaction_count"]),
        "top_category": top["category"] if top else "—",
    }
# === END get_summary_stats ===


# === BEGIN get_category_breakdown (subagent C) ===
def get_category_breakdown(user_id, date_from=None, date_to=None):
    date_sql, date_params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses "
            "WHERE user_id = ?" + date_sql + " GROUP BY category",
            (user_id, *date_params),
        ).fetchall()
    finally:
        conn.close()

    categories = [(row["category"], float(row["total"] or 0)) for row in rows]
    categories.sort(key=lambda item: (-round(item[1], 2), item[0]))
    grand_total = sum(amount for _, amount in categories)

    breakdown = []
    for name, amount in categories:
        pct = int(amount * 100 / grand_total + 0.5) if grand_total > 0 else 0
        breakdown.append({"name": name, "amount": round(amount, 2), "pct": max(pct, 0)})

    if breakdown and grand_total > 0:
        remainder = 100 - sum(item["pct"] for item in breakdown)
        breakdown[0]["pct"] = max(breakdown[0]["pct"] + remainder, 0)
    return breakdown
# === END get_category_breakdown ===
