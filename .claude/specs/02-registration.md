# Spec: Registration

## Overview
This feature implements user registration for Spendly. A visitor fills out
the existing `/register` form (name, email, password) and, on submission,
gets a real account created in the `users` table with a hashed password. On
success the user is logged in immediately via a session and redirected to
their profile. This is the second step in the Spendly roadmap and is a
prerequisite for logout (Step 3), profile (Step 4), and every authenticated
route that follows, since it establishes the session mechanism those steps
rely on.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`). Already complete.

## Routes
- `GET /register` — renders the registration form (already exists; no behavior change) — public
- `POST /register` — validates input, creates the user, starts a session, redirects to `/profile` — public

## Database changes
No schema changes. The `users` table already has the required columns
(`name`, `email`, `password_hash`, `created_at`). Two helper functions are
added to `database/db.py` (see Files to change) — no new tables or columns.

## Templates
- **Create:** none
- **Modify:** `templates/register.html` — repopulate the `name` and `email`
  inputs with previously submitted values (`value="{{ name or '' }}"`, etc.)
  so a validation error doesn't clear the form.

## Files to change
- `app.py`
  - Set `app.secret_key` (required for Flask sessions).
  - Import `session`, `redirect`, `url_for`, `request` from `flask`.
  - Extend `POST /register` handling:
    - Read `name`, `email`, `password` from `request.form`.
    - Validate: all fields non-empty, email contains `@`, password is at
      least 8 characters.
    - Call `db.get_user_by_email(email)`; if a row is returned, re-render
      `register.html` with an error and the submitted `name`/`email`.
    - On validation failure, re-render `register.html` with an appropriate
      error and the submitted `name`/`email`.
    - On success, call `db.create_user(name, email, password)`, store the
      returned user id in `session["user_id"]`, and redirect to `/profile`.
- `database/db.py`
  - Add `get_user_by_email(email)` — returns the matching row or `None`,
    using a parameterized `SELECT`.
  - Add `create_user(name, email, password)` — hashes `password` with
    `werkzeug.security.generate_password_hash`, inserts the row via a
    parameterized `INSERT`, and returns the new user's id.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterized queries only — never use string formatting in SQL.
- Passwords hashed with `werkzeug.security.generate_password_hash`.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Routes stay thin: validation and flow control can live in `app.py`, but
  all SQL lives in `database/db.py`.

## Definition of done
- [ ] Visiting `/register` shows the registration form
- [ ] Submitting valid, unique details creates a new row in `users` with a
      hashed (not plaintext) password
- [ ] Submitting an already-registered email re-renders the form with an
      error and does not create a duplicate row
- [ ] Submitting a password under 8 characters re-renders the form with a
      validation error and creates no row
- [ ] On success, the browser receives a session cookie and is redirected
      to `/profile`
- [ ] Restarting the app does not lose previously registered users (data
      persists in `spendly.db`)
