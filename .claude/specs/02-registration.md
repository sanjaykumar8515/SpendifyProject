# Spec: Registration

## Overview
Turn the existing `GET /register` page into a working sign-up flow. A visitor submits name, email and password; the app validates the input, stores the user with a hashed password in the `users` table, and redirects to the login page. This is Step 2 of the Spendly roadmap: it builds on the database setup from Step 1 and produces the accounts that login (Step 3) will authenticate against.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()` in `database/db.py`)

## Routes
- `GET /register` — render the registration form (already implemented, unchanged) — public
- `POST /register` — validate the form, create the user, redirect to `login` on success; re-render `register.html` with an `error` message and HTTP 400 on validation failure or duplicate email — public

`app.py` change: the existing `register` view accepts `methods=["GET", "POST"]`.

## Database changes
No schema changes. The `users` table already has `name`, `email` (UNIQUE NOT NULL), `password_hash` and `created_at`.

Note: SQLite's UNIQUE constraint is case-sensitive (the column has no `COLLATE NOCASE`). Case-insensitive uniqueness therefore relies on every write lowercasing the email. Confirm that any seed data from Step 1 is already lowercase.

New helpers in `database/db.py`:
- `get_user_by_email(email)` — returns the matching `sqlite3.Row` or `None`
- `create_user(name, email, password)` — hashes the password with `werkzeug.security.generate_password_hash`, inserts the row with a parameterised query, returns the new user id; raises `sqlite3.IntegrityError` if the email already exists (the UNIQUE constraint is the source of truth, so a race cannot create duplicates)
- Both helpers close their connection before returning

Configurable database path (needed for test isolation):
- `get_db()` reads the database path from `current_app.config["DATABASE"]`, defaulting to the existing path when unset. Tests point it at a temporary file.

## Templates
- **Create:** none
- **Modify:** `templates/register.html`
  - Change `action="/register"` to `action="{{ url_for('register') }}"` (no hardcoded URLs)
  - Render `{{ error }}` in an error block above the form when set, styled with CSS variables only (add the block if it does not already exist)
  - Repopulate `name` and `email` inputs from the submitted values after an error (never repopulate the password)
  - Add `minlength="8"` to the password input to match the placeholder
  - Add `maxlength="100"` to the name input and `maxlength="254"` to the email input; use `type="email"` on the email input

## Files to change
- `app.py` — accept POST on `/register`; call the db helpers; catch `IntegrityError`; render errors; redirect on success
- `database/db.py` — add `get_user_by_email()` and `create_user()`; make the database path configurable
- `templates/register.html` — form action, error block, value repopulation, `minlength` / `maxlength` / `type="email"`
- `CLAUDE.md` — update the routes table (`POST /register`) and the note listing which db helpers exist

## Files to create
- `tests/test_registration.py` — tests for the registration flow, using a pytest fixture that sets `DATABASE` to a temp file and calls `init_db()`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py`, never inline in the route
- Route function stays thin: read form, validate, call helper, render or redirect
- Use `url_for()` for every internal link and redirect
- Use `abort()` only for unexpected HTTP errors; validation failures and duplicate emails re-render the form with `error` and status 400 (this flow has no `abort()` calls)
- Normalise input: strip whitespace from name and email, lowercase the email before lookup and storage. Never strip or otherwise alter the password.
- Validate in this order and show only the first failure:
  1. Name required (a whitespace-only name counts as empty); at most 100 characters
  2. Email required, contains `@` with text on both sides; at most 254 characters
  3. Password at least 8 characters
  4. Email not already registered
- Duplicate email message: "An account with that email already exists". This deliberately reveals that the email is registered, an accepted trade-off for a sign-up form.
- Duplicate handling: check with `get_user_by_email()` first, and also catch `sqlite3.IntegrityError` from `create_user()` and treat it the same way, so a race returns the error page rather than a 500
- Do not add sessions, `secret_key`, `flash()`, or auto-login — that belongs to Step 3
- Do not implement any other stub route (`/logout`, `/profile`, expenses)

## Known gaps (deferred to Step 3)
- No success message after redirect: `flash()` needs a `secret_key`, which belongs to Step 3
- No CSRF protection on the form, for the same reason

## Definition of done
- [ ] `GET /register` still renders the form with status 200
- [ ] Submitting a valid name, email and password creates a row in `users` and redirects (302) to `url_for('login')`
- [ ] The stored email is lowercased and stripped
- [ ] The stored `password_hash` is not the plaintext password and verifies with `check_password_hash`
- [ ] Submitting an email that already exists (any letter case) re-renders the form with an error and does not create a second row
- [ ] A race-style duplicate (simulated by calling `create_user` directly before posting) yields the error page with status 400, not a 500
- [ ] Submitting a password shorter than 8 characters shows an error and creates no user
- [ ] Submitting an empty or whitespace-only name, or an invalid email, shows an error and creates no user
- [ ] After an error, the name and email fields keep their values and the password field is empty
- [ ] The form posts via `url_for('register')`; no hardcoded `/register` remains in the template
- [ ] Tests run against a temporary database, never the real one
- [ ] `pytest` passes, including the new `tests/test_registration.py`
- [ ] The app still starts on port 5001
