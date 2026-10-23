# Spec: Edit Expense

## Overview
Step 8 lets a logged-in user correct an expense they already recorded. `/expenses/<id>/edit`
is currently a raw-string stub. This step turns it into a pre-filled form (GET) plus a
submit handler (POST) that reuses the Step 7 validation, updates the row only if it belongs
to the current user, and redirects to the profile page. Each row in the profile's
transaction history gets an "Edit" link so the feature is reachable from the UI.

## Depends on
- Step 1: Database setup (`expenses` table)
- Step 3: Login / Logout (`session["user_id"]`)
- Step 5: Backend connection (profile transaction history)
- Step 7: Add expenses (`validate_expense()`, `EXPENSE_CATEGORIES`, add form template/CSS)

## Routes
- `GET /expenses/<int:id>/edit` — render the edit form pre-filled with the expense's current values — logged-in (unauthenticated users redirect to `login`); `abort(404)` if the expense does not exist or belongs to another user
- `POST /expenses/<int:id>/edit` — validate and update the expense; on success redirect to `profile`; on validation error re-render the form with the message, submitted values preserved, status 400 — logged-in; `abort(404)` if missing or not owned by the user

The existing route function `edit_expense` is extended to accept `GET` and `POST`. It reuses
`validate_expense()` from Step 7 (no duplicated validation). Ownership failures return 404
(not 403) so other users' expense ids are not revealed.

## Database changes
No schema changes. Add two helpers to `database/db.py`:
- `get_expense(expense_id, user_id)` — parameterized `SELECT ... WHERE id = ? AND user_id = ?`; returns the row or `None`
- `update_expense(expense_id, user_id, amount, category, expense_date, description)` — parameterized `UPDATE ... WHERE id = ? AND user_id = ?`; returns `True` if a row was updated (`rowcount > 0`), else `False`

In `database/queries.py`, `get_recent_transactions()` must also select and return `id` so the
profile template can build edit links.

## Templates
- **Create:** none — the edit page reuses `templates/add_expense.html`
- **Modify:** `templates/add_expense.html` — accept an optional `expense_id`; when set, show "Edit Expense" heading/submit label ("Save changes") and post to `url_for('edit_expense', id=expense_id)`; otherwise behave exactly as the add form. Cancel link stays `url_for('profile')`
- **Modify:** `templates/profile.html` — add an Actions column with an "Edit" link per transaction row using `url_for('edit_expense', id=t.id)`

## Files to change
- `app.py` — extend `edit_expense` to GET/POST; import `get_expense`, `update_expense`, `abort`; pass `id` through the transaction dicts in `profile()`
- `database/db.py` — add `get_expense()` and `update_expense()`
- `database/queries.py` — include `id` in `get_recent_transactions()` results
- `templates/add_expense.html` — dual add/edit mode
- `templates/profile.html` — Edit link column
- `static/css/profile.css` — style the Edit link / actions column (CSS variables only)
- `CLAUDE.md` — mark `/expenses/<id>/edit` Implemented (Step 8) for GET and POST, and list `get_expense()` / `update_expense()` among `db.py` helpers

## Files to create
- `tests/test_edit_expense.py` — pytest coverage for the Definition of done

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic only in `database/db.py`; the route fetches/validates, renders, done
- Use `url_for()` for every link and form action
- Always take `user_id` from `session`, never from the form (no mass assignment); every SELECT/UPDATE of an expense must filter on both `id` and `user_id`
- Reuse `validate_expense()`; do not copy its rules
- Use `abort(404)` for missing/foreign expenses, not raw strings
- Do not implement the delete stub (Step 9); do not change the port (5001)

## Definition of done
- [ ] Visiting `/expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting the edit URL for your own expense shows the form pre-filled with its amount, category, date and description
- [ ] Visiting the edit URL for a nonexistent id returns 404
- [ ] Visiting the edit URL for another user's expense returns 404, and a POST to it changes nothing
- [ ] Submitting valid changes redirects to `/profile`, where the updated values appear in transaction history
- [ ] Total spent and category breakdown on `/profile` reflect the edited amount/category
- [ ] Invalid amount, category, date, or a description over 200 characters shows an error, returns 400, and leaves the stored row unchanged
- [ ] After a validation error the submitted values are still in the form and it still posts to the edit URL
- [ ] A forged POST with `user_id` does not change the stored owner
- [ ] Each transaction row on `/profile` has an Edit link that opens that expense's edit page
- [ ] `/expenses/add` still works unchanged (heading, action, and submit label)
- [ ] `pytest` passes, including the new `tests/test_edit_expense.py`
