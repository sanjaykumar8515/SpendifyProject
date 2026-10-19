# Spec: Date Filter For Profile Page

## Overview
Step 6 lets a logged-in user narrow the profile page to a date range. Step 5 wired
`/profile` to live data, but every section always covers all of the user's expenses.
This step adds an optional `from`/`to` date range, submitted as query parameters, that
scopes the summary stats, transaction history and category breakdown together. It is
a read-only GET filter, so no new tables or write routes are needed.

## Depends on
- Step 1: Database setup (`expenses.date` stored as ISO `YYYY-MM-DD` text)
- Step 3: Login / Logout (`session["user_id"]`)
- Step 4: Profile page static UI
- Step 5: Backend connection (`database/queries.py` helpers feeding `/profile`)

## Routes
No new routes. The existing `GET /profile` accepts two optional query parameters:
- `date_from` — inclusive start date, `YYYY-MM-DD`
- `date_to` — inclusive end date, `YYYY-MM-DD`

Access level stays logged-in only (unauthenticated users redirect to `login`).

Behaviour:
- Both missing or empty: unfiltered, identical to current behaviour.
- Only one supplied: open-ended range on the other side.
- Unparseable date: ignored, and an inline error message is shown. The page still
  returns 200 with unfiltered data.
- `date_from` later than `date_to`: shows an inline error and falls back to unfiltered
  data. The page still returns 200.
- Validation lives in a helper (not inline in the route body); the route only parses,
  fetches, renders.

## Database changes
No database changes. Filtering uses the existing `expenses.date` column. ISO text
dates compare correctly with `>=` / `<=`.

## Templates
- **Create:** none
- **Modify:** `templates/profile.html`
  - Add a filter `<form method="get" action="{{ url_for('profile') }}">` above the
    stats section with two `<input type="date">` fields (`date_from`, `date_to`),
    an "Apply" submit button and a "Clear" link to `url_for('profile')`.
  - Re-populate the inputs with the submitted values.
  - Render the validation error message when present.
  - Empty-state text should read "No expenses in this date range." when a filter is
    active, and keep the current wording otherwise.

## Files to change
- `app.py` — read and validate `date_from` / `date_to` in `profile()`, pass them to
  the query helpers and template
- `database/queries.py` — add optional `date_from=None, date_to=None` params to
  `get_summary_stats`, `get_recent_transactions`, `get_category_breakdown`
- `templates/profile.html` — filter form, error and empty states
- `static/css/profile.css` — styles for the filter bar
- `CLAUDE.md` — update the `/profile` row and the `queries.py` note for Step 6

## Files to create
- `tests/test_profile_date_filter.py` — pytest coverage for the cases under
  Definition of done

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — build the optional `AND date >= ?` / `AND date <= ?`
  clauses from fixed string fragments and pass the values as parameters, never
  f-string the values into SQL
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles or inline `<style>` tags; no new JS needed (native date inputs)
- Never hardcode URLs — use `url_for()`
- DB logic stays in `database/queries.py`, not in `app.py`
- New parameters default to `None` so existing callers and tests keep working
- The same range must apply to all three sections so the totals, list and breakdown
  stay consistent with each other
- Always scope by `user_id` as well — the date filter must never widen access to
  other users' expenses
- Keep the existing 10-row limit on transactions within the filtered range
- Currency stays ₹

## Definition of done
- [ ] `/profile` without query parameters renders exactly as it did after Step 5
- [ ] Logged in as demo@spendly.com, choosing a range that covers only some seed
      expenses updates total spent, transaction count, top category, the transaction
      rows and the category breakdown to match that range
- [ ] Category percentages in a filtered view still add up to 100
- [ ] Supplying only `date_from` or only `date_to` filters one side only
- [ ] A range containing no expenses shows ₹0.00, 0 transactions, an em dash for top
      category, and "No expenses in this date range."
- [ ] The date inputs keep the submitted values after Apply
- [ ] "Clear" returns to the unfiltered `/profile`
- [ ] `?date_from=not-a-date` and `?date_from=2026-02-01&date_to=2026-01-01` return
      200, show an error message and display unfiltered data
- [ ] Another user's expenses never appear in the filtered results
- [ ] Unauthenticated `GET /profile?date_from=2026-01-01` still redirects to `/login`
- [ ] `pytest` passes, including the new date filter tests
