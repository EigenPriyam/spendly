# Spec: Login and Logout

## Overview
This feature completes the authentication loop for Spendly. Step 2 wired up
registration and introduced session-based auth (`app.secret_key`,
`session["user_id"]`), but existing users have no way to sign back in, and
there's no way to end a session once started. This step wires up `POST
/login` to authenticate against the `users` table and `GET /logout` to clear
the session, and updates the navbar so it reflects whether a session is
active. It unlocks Step 4 (profile), since a real "logged-in" state is
required before a profile page makes sense.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`).
- Step 2 — Registration (`app.secret_key`, `session["user_id"]` convention,
  `get_user_by_email()` helper in `database/db.py`).

## Routes
- `GET /login` — renders the sign-in form (already exists; no behavior change) — public
- `POST /login` — validates credentials, starts a session, redirects to `/profile` — public
- `GET /logout` — clears the session, redirects to the landing page (`/`) — logged-in (harmless no-op if hit while logged out)

## Database changes
No schema changes and no new `database/db.py` functions. Reuses
`get_user_by_email(email)` from Step 2 to fetch the row; password
verification uses `werkzeug.security.check_password_hash` against the
returned `password_hash`, done in `app.py` since it's a hash comparison, not
a query.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — repopulate the `email` input with
    `value="{{ email or '' }}"` so a failed login doesn't clear it (password
    left as-is, same reasoning as the registration form).
  - `templates/base.html` — the navbar `.nav-links` currently always shows
    "Sign in" / "Get started". Wrap it in a check on the session: if
    `session.user_id` is set, show links to `/profile` ("Profile") and
    `/logout` ("Logout"); otherwise show the existing "Sign in" / "Get
    started" links.

## Files to change
- `app.py`
  - Import `check_password_hash` from `werkzeug.security`.
  - Extend `/login` to accept `GET` and `POST`:
    - On `POST`, read `email`, `password` from `request.form`.
    - Look up the user via `get_user_by_email(email)`.
    - If no user is found, or `check_password_hash(user["password_hash"],
      password)` fails, re-render `login.html` with a single generic error
      — `"Invalid email or password."` — and the submitted `email`. Do not
      reveal whether the email or the password was the problem.
    - On success, set `session["user_id"] = user["id"]` and redirect to
      `/profile`.
  - Replace the `/logout` stub: clear the session (`session.clear()`) and
    redirect to `/` (landing page).
- `templates/login.html` — add the `value="{{ email or '' }}"` attribute.
- `templates/base.html` — make `.nav-links` conditional on `session.user_id`
  as described above.

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterized queries only — never use string formatting in SQL.
- Passwords verified with `werkzeug.security.check_password_hash`.
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Routes stay thin: validation and flow control can live in `app.py`, but
  all SQL lives in `database/db.py`.
- Login failures must use one generic message regardless of whether the
  email doesn't exist or the password is wrong (no user enumeration).

## Definition of done
- [ ] Visiting `/login` shows the sign-in form
- [ ] Submitting valid credentials for an existing user sets a session
      cookie and redirects to `/profile`
- [ ] Submitting an email that doesn't exist shows "Invalid email or
      password." and sets no session
- [ ] Submitting a wrong password for a real email shows the same generic
      "Invalid email or password." message and sets no session
- [ ] Navbar shows "Profile" / "Logout" when a session is active, and "Sign
      in" / "Get started" when it isn't
- [ ] Visiting `/logout` while logged in clears the session and redirects
      to the landing page, and the navbar reverts to "Sign in" / "Get
      started" afterward
