# Spec: Profile

## Overview
This feature replaces the `/profile` stub (`return "Profile page — coming in
Step 4"`) with a real page. Step 3 completed the authentication loop and
made `session.user_id` a reliable signal of who is logged in; this step is
the first place that session is used to look up and display a real user
record. The page is read-only for now — just the logged-in user's account
details pulled from the `users` table — since editing isn't in scope until
a later step. It also establishes the "logged-in area must redirect
logged-out visitors" pattern that later expense routes (Steps 7-9) will
reuse.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`).
- Step 3 — Login and Logout (`session["user_id"]` is set on login and
  cleared on logout; navbar already links to `/profile`).

## Routes
- `GET /profile` — renders the logged-in user's account details; redirects
  to `/login` if no session is active — logged-in

## Database changes
No schema changes. One new function in `database/db.py`:
- `get_user_by_id(user_id)` — `SELECT * FROM users WHERE id = ?`, returns a
  single row (mirrors the existing `get_user_by_email` shape).

## Templates
- **Create:** `templates/profile.html` — displays the user's name, email,
  and member-since date (`created_at`), styled with the existing
  `auth-card`-style pattern from `register.html`/`login.html` so it's
  visually consistent with the rest of the auth flow.
- **Modify:** none.

## Files to change
- `app.py`
  - Import `get_user_by_id` from `database.db`.
  - Replace the `/profile` stub:
    - If `session.get("user_id")` is falsy, redirect to `url_for("login")`.
    - Otherwise call `get_user_by_id(session["user_id"])` and render
      `profile.html` with the user row.
- `database/db.py` — add `get_user_by_id(user_id)`.

## Files to create
- `templates/profile.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs.
- Parameterized queries only — never use string formatting in SQL.
- Passwords hashed with werkzeug (unaffected by this step — no password
  handling here).
- Use CSS variables — never hardcode hex values.
- All templates extend `base.html`.
- Routes stay thin: the redirect check lives in `app.py`, all SQL lives in
  `database/db.py`.
- Do not render `password_hash` anywhere in the template.

## Definition of done
- [ ] Visiting `/profile` while logged out redirects to `/login`
- [ ] Visiting `/profile` while logged in shows the demo user's name,
      email, and member-since date
- [ ] The page renders inside `base.html` (navbar/footer present) and shows
      "Profile" / "Logout" in the nav
- [ ] No password hash or other sensitive field appears in the rendered
      HTML
- [ ] `pytest` still passes with no regressions
