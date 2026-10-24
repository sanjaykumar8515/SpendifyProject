# Spec: Delete Expenses

## Overview
Step 9 lets a logged-in user remove an expense they recorded by mistake. `/expenses/<id>/delete`
is currently a raw-string stub. This step turns it into a real delete handler that removes the
row only if it belongs to the current user and then redirects to the profile page. Because
deleting is a state change, it is performed with `POST` (a link-triggered `GET` could be fired by
prefetchers or cross-site images). Each row in the profile's transaction history gets a "Delete"
button next to "Edit" so the feature is reachable from the UI, guarded by a vanilla-JS confirm
prompt. This completes the add / edit / delete expense roadmap.

## Depends on
- Step 1: Database setup (`expenses` table)
- Step 3: Login / Logout (`session["user_id"]`)
- Step 5: Backend connection (profile transaction history, `id` in transaction rows)
- Step 8: Edit expense (Actions column, `get_expense()` ownership pattern, 404-on-foreign-id convention)

## Routes
- `POST /expenses/<int:id>/delete` — delete the expense and redirect to `profile` — logged-in (unauthenticated users redirect to `login`); `abort(404)` if the expense does not exist or belongs to another user

The existing stub `delete_expense` is changed from `GET` to `POST` only. `GET /expenses/<id>/delete`
therefore returns 405 and never deletes anything. Ownership failures return 404 (not 403) so other
users' expense ids are not revealed.

## Database changes
No schema changes. Add one helper to `database/db.py`:
- `delete_expense(expense_id, user_id)` — parameterized `DELETE FROM expenses WHERE id = ? AND user_id = ?`; commits; returns `True` if a row was deleted (`rowcount > 0`), else `False`

## Templates
- **Create:** none
- **Modify:** `templates/profile.html` — in the Actions cell of each transaction row, add a small `<form method="post" action="{{ url_for('delete_expense', id=t.id) }}">` with a "Delete" submit button (carries a `data-confirm` attribute with the prompt text)

## Files to change
- `app.py` — import `delete_expense` from `database.db`; change the `delete_expense` route to `methods=["POST"]`, require login, call the DB helper, `abort(404)` when it returns `False`, redirect to `profile`. Route function name collides with the imported helper, so import the helper under an alias (e.g. `from database.db import delete_expense as remove_expense`) or rename the route function while keeping the endpoint name `delete_expense` (`@app.route(..., endpoint="delete_expense")`)
- `database/db.py` — add `delete_expense()`
- `templates/profile.html` — Delete form/button per row
- `static/js/main.js` — vanilla JS: on submit of any form with `data-confirm`, call `window.confirm()` and cancel the submit if declined
- `static/css/profile.css` — style the Delete button and inline form so it sits beside the Edit link (CSS variables only)
- `CLAUDE.md` — mark `POST /expenses/<id>/delete` Implemented (Step 9) in the routes table, and list `delete_expense()` among the `db.py` helpers

## Files to create
- `tests/test_delete_expense.py` — pytest coverage for the Definition of done

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (no auth changes in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic only in `database/db.py`; the route checks login, calls the helper, redirects, done
- Use `url_for()` for every link and form action
- Deletion must be `POST` only — never delete on `GET`
- Always take `user_id` from `session`, never from the form; the `DELETE` must filter on both `id` and `user_id`
- Use `abort(404)` for missing/foreign expenses, not raw strings
- Vanilla JS only — no frameworks, no npm packages
- The page must still work with JS disabled (the form posts without the confirm prompt)
- Do not implement any other stub route; do not change the port (5001)

## Definition of done
- [ ] Each transaction row on `/profile` shows a Delete button beside the Edit link
- [ ] Clicking Delete shows a confirm prompt; cancelling leaves the expense in place
- [ ] Confirming redirects to `/profile` and the expense no longer appears in transaction history
- [ ] Total spent, transaction count and category breakdown on `/profile` reflect the removal
- [ ] `POST /expenses/<id>/delete` while logged out redirects to `/login` and deletes nothing
- [ ] `GET /expenses/<id>/delete` returns 405 and deletes nothing
- [ ] `POST` to the delete URL for a nonexistent id returns 404
- [ ] `POST` to the delete URL for another user's expense returns 404 and that expense still exists
- [ ] Deleting one expense does not affect the user's other expenses or other users' expenses
- [ ] Deleting the same expense twice returns 404 the second time
- [ ] The edit page (`/expenses/<id>/edit`) for a deleted expense returns 404
- [ ] `/expenses/add` and `/expenses/<id>/edit` still work unchanged
- [ ] `pytest` passes, including the new `tests/test_delete_expense.py`
