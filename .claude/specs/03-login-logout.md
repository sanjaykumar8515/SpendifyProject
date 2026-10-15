# Spec: Login and Logout

## Overview
Turn the existing `GET /login` page into a working sign-in flow and replace the `/logout` stub. A visitor submits email and password; the app verifies them against the hashed password in `users`, stores the user id in a Flask session, and redirects. Logout clears the session. This is Step 3 of the Spendly roadmap: it authenticates the accounts created in Step 2 and introduces the session that later steps (profile, expenses) rely on for access control. It also brings in the `secret_key`, `flash()` and CSRF groundwork deferred from Step 2.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`)
- Step 2 — Registration (`get_user_by_email()`, `create_user()`, hashed passwords, lowercase emails)

## Routes
- `GET /login` — render the login form (already implemented); redirect to `landing` if already logged in — public
- `POST /login` — normalise email, verify credentials, set `session["user_id"]`, redirect to `landing`; re-render `login.html` with `error` and HTTP 400 on failure — public
- `GET /logout` — clear the session, redirect to `landing` — public (safe to call when logged out)

`app.py` changes: `login` accepts `methods=["GET", "POST"]`; `logout` stops returning a raw string. Redirect target after login is `landing` because `/profile` is still a Step 4 stub.

## Database changes
No database changes. `get_user_by_email()` already exists; no new helper is required. Password verification uses `werkzeug.security.check_password_hash` against `password_hash`. Seed user `demo@spendly.com` is already lowercase.

## Templates
- **Create:** none
- **Modify:** `templates/login.html`
  - Change `action="/login"` to `action="{{ url_for('login') }}"`
  - Repopulate the `email` input from the submitted value after an error (never repopulate the password)
  - Keep the existing `error` block
- **Modify:** `templates/base.html`
  - Navbar: when `session.user_id` is set, show a "Sign out" link (`url_for('logout')`) instead of "Sign in" / "Get started"; otherwise keep the current links
  - Show flashed messages (if any) above `{% block content %}` using CSS-variable styling

## Files to change
- `app.py` — set `app.secret_key`; accept POST on `/login`; implement `/logout`; wrap session handling
- `templates/login.html` — form action, email repopulation
- `templates/base.html` — conditional nav links, flash message block
- `static/css/style.css` — styles for the flash message block (CSS variables only)
- `CLAUDE.md` — update routes table (`POST /login`, `GET /logout` implemented) and note that sessions now exist

## Files to create
- `tests/test_login_logout.py` — tests for login/logout using a temp-DB fixture (same pattern as `tests/test_registration.py`)

## New dependencies
No new dependencies. Flask's built-in `session` and `flash` are used.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (verify with `check_password_hash`; never compare plaintext)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py`, never inline in the route
- Route functions stay thin: read form, look up user, verify, set session, redirect or render
- Use `url_for()` for every internal link and redirect
- `secret_key` is read from the `SECRET_KEY` environment variable with a clearly-named development fallback; tests may override via `app.config`
- Normalise input: strip and lowercase the email; never alter the password
- Use one generic failure message for unknown email and wrong password: "Invalid email or password" — do not reveal which was wrong
- Failure re-renders `login.html` with status 400 (no `abort()` for credential errors)
- Store only `user_id` in the session; clear the whole session on logout (`session.clear()`) and on login before setting `user_id` (prevents session fixation)
- Do not implement `/profile`, expense routes, or any login-required decorator beyond what these routes need — that belongs to later steps
- Do not change the port (5001)

## Definition of done
- [ ] `GET /login` renders the form with status 200 when logged out
- [ ] Logging in as `demo@spendly.com` / `demo123` redirects (302) to `url_for('landing')` and sets `session["user_id"]` to that user's id
- [ ] Email is matched case-insensitively and with surrounding whitespace ignored
- [ ] A wrong password shows "Invalid email or password" with status 400 and no session is set
- [ ] An unknown email shows the same message and status
- [ ] After a failed login the email field keeps its value and the password field is empty
- [ ] The form posts via `url_for('login')`; no hardcoded `/login` remains in the template
- [ ] `GET /login` while logged in redirects to `landing`
- [ ] `GET /logout` clears the session and redirects (302) to `url_for('landing')`; calling it while logged out also works
- [ ] The navbar shows "Sign out" when logged in and "Sign in" / "Get started" when logged out
- [ ] `/logout` no longer returns a raw string
- [ ] Tests run against a temporary database, never the real one
- [ ] `pytest` passes, including `tests/test_login_logout.py` and the existing registration tests
- [ ] The app still starts on port 5001
