# Spec: Add Expenses

## Overview
Step 7 lets a logged-in user record a new expense. Until now the only expenses are the
seeded demo rows, and `/expenses/add` is a raw-string stub. This step turns it into a
real form (GET) plus a submit handler (POST) that validates input, inserts a row into
`expenses` for the current user, and redirects to the profile page, where the new
expense shows up in the summary stats, transaction history and category breakdown.

## Depends on
- Step 1: Database setup (`expenses` table)
- Step 3: Login / Logout (`session["user_id"]`)
- Step 5: Backend connection (profile page reads live expense data)
- Step 6: Date filter (profile keeps working with new rows; dates stored as ISO text)

## Routes
- `GET /expenses/add` — render the add-expense form — logged-in (unauthenticated users redirect to `login`)
- `POST /expenses/add` — validate and create the expense; on success redirect to `profile`; on validation error re-render the form with the message, submitted values preserved, status 400 — logged-in

The existing route function `add_expense` is extended to accept `GET` and `POST`.
Validation lives in a helper (like `validate_registration`), not inline in the route.

Validation rules:
- `amount` — required, parses as a number, greater than 0, at most 2 decimal places, max 1,000,000
- `category` — required, must be one of: Food, Transport, Bills, Health, Entertainment, Shopping, Other
- `date` — required, `YYYY-MM-DD`, a real calendar date (future dates allowed)
- `description` — optional, stripped, max 200 characters

## Database changes
No database changes. The existing `expenses` table already has `user_id`, `amount`,
`category`, `date`, `description`. Add one helper to `database/db.py`:
- `create_expense(user_id, amount, category, date, description)` — parameterized
  INSERT, returns the new row id.

## Templates
- **Create:** `templates/add_expense.html` — form with amount, category `<select>`, date `<input type="date">` (defaults to today), description; submit button and a cancel link to `url_for('profile')`; error banner when `error` is set
- **Modify:** `templates/profile.html` — add an "Add Expense" link to `url_for('add_expense')`; if the profile page already has an add link, point it at the route via `url_for`
- **Modify:** `templates/base.html` — only if the nav needs an "Add Expense" link for logged-in users (keep `url_for`)

## Files to change
- `app.py` — extend `add_expense` to GET/POST, add validation helper and category list
- `database/db.py` — add `create_expense()`
- `templates/profile.html` — link to the add form
- `CLAUDE.md` — update the `/expenses/add` row to Implemented (Step 7) and list `create_expense()` among `db.py` helpers

## Files to create
- `templates/add_expense.html`
- `static/css/add_expense.css` — page-specific styles (loaded via a base.html block, no inline `<style>`)
- `tests/test_add_expense.py` — pytest coverage for the Definition of done

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
- Always take `user_id` from `session`, never from the form (no mass assignment)
- Store `amount` as a float rounded to 2 decimals; reject NaN/inf
- Use `abort()` for HTTP errors, not raw strings; do not implement the edit/delete stubs
- Do not change the port (5001)

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows the form with date defaulting to today and all 7 categories
- [ ] Submitting a valid expense redirects to `/profile` and the new row appears in recent transactions
- [ ] Total spent and the category breakdown on `/profile` reflect the new expense
- [ ] The expense is saved under the logged-in user's id and not visible to other users
- [ ] Empty, zero, negative, non-numeric, or >2-decimal amount shows an error and returns 400 with no row inserted
- [ ] Invalid category or invalid date shows an error and returns 400 with no row inserted
- [ ] Description over 200 characters shows an error; empty description is accepted
- [ ] After a validation error the submitted values are still in the form
- [ ] Forged POST with a `user_id` field does not affect the stored owner
- [ ] `pytest` passes, including the new `tests/test_add_expense.py`
