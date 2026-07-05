# Spec: Add Expense

## Overview
Step 7 replaces the `/expenses/add` placeholder stub with a real form that lets
a logged-in user record a new expense. This is the first write-capable feature
in the app beyond registration: it inserts directly into the `expenses` table
that Steps 5 and 6 already read from, so newly added expenses immediately show
up in the profile's summary stats, recent transactions, and category
breakdown.

## Depends on
- Step 1: Database setup (`expenses` table must exist)
- Step 3: Login/session handling (`session["user_id"]` must be set)
- Step 4/5: Profile page and its query helpers (the user is redirected back
  there after a successful add)

## Routes
- `GET /expenses/add` — render a blank add-expense form — logged-in only
- `POST /expenses/add` — validate the submitted expense and insert it,
  redirect to `/profile` on success or redisplay the form with errors —
  logged-in only

Both methods share the existing `/expenses/add` route (`add_expense()` in
`app.py`), following the same GET/POST pattern already used by
`register()`/`login()`. If `session.get("user_id")` is missing, redirect to
`/login` (same guard as `profile()`).

## Database changes
No database changes. The `expenses` table already has the columns needed
(`user_id`, `amount`, `category`, `date`, `description`).

## Templates
- **Create:** `templates/add_expense.html` — form page, extends `base.html`,
  follows the same `auth-section`/`form-group`/`btn-submit` structure as
  `register.html` (adapted to a non-auth context)
- **Modify:** `templates/profile.html` — add an "Add Expense" link/button
  (e.g. near the recent-transactions section) pointing to
  `{{ url_for('add_expense') }}`

## Files to change
- `app.py`
  - Implement `add_expense()`:
    - Guard: redirect to `login` if no `session["user_id"]`
    - On `POST`: read `amount`, `category`, `date`, `description` from
      `request.form`; validate; on error, re-render `add_expense.html` with
      the error and previously entered values (mirrors the `register()`
      pattern); on success, call the new `create_expense` helper, flash a
      success message, and redirect to `profile`
    - On `GET`: render a blank `add_expense.html`
- `database/queries.py`
  - Add `create_expense(user_id, amount, category, date, description)`:
    parameterised `INSERT INTO expenses (...) VALUES (?, ?, ?, ?, ?)`, returns
    the new row id
- `templates/profile.html` — add the "Add Expense" link (see Templates)
- `static/css/style.css` — add any styles needed for the add-expense form,
  reusing existing `auth-*`/`form-*`/`btn-submit` classes/tokens where
  possible; only add new CSS variables/classes if the existing auth-form
  styles don't fit

## Files to create
- `templates/add_expense.html`

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only via `get_db()`
- Parameterised queries only — never string-format form values into SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline styles
- `category` must be a `<select>` constrained to the fixed set already used
  in seed data: Food, Transport, Bills, Health, Entertainment, Shopping, Other
- `amount` must parse as a positive number (`float(amount) > 0`); non-numeric
  or non-positive values are a validation error, not a crash
- `date` must be a valid `YYYY-MM-DD` string (`datetime.strptime(value,
  "%Y-%m-%d")`); invalid dates are a validation error, not a crash
- `description` is optional free text
- All validation happens in `app.py` before calling `create_expense` — the
  query helper assumes already-valid input
- On any validation error, redisplay `add_expense.html` with the error
  message and the user's previously entered values (do not clear the form)
- On success, use `flash()` for the success message and
  `redirect(url_for("profile"))` — never a hardcoded URL string

## Definition of done
- [ ] Visiting `/expenses/add` while logged out redirects to `/login`
- [ ] Visiting `/expenses/add` while logged in shows a blank form with amount,
  category (select), date, and description fields
- [ ] Submitting the form with a valid amount, category, date, and
  description inserts a new row into `expenses` for the current user and
  redirects to `/profile`
- [ ] The newly added expense immediately appears in the profile's recent
  transactions list, summary stats, and category breakdown
- [ ] Submitting a non-numeric or negative amount redisplays the form with an
  error and the previously entered values, without crashing
- [ ] Submitting a malformed date redisplays the form with an error and the
  previously entered values, without crashing
- [ ] Submitting with an empty amount, category, or date shows a validation
  error rather than inserting a partial row
- [ ] Description can be left blank and the expense still saves successfully
- [ ] The profile page has a visible "Add Expense" link/button that navigates
  to `/expenses/add`
- [ ] All amounts continue to display the ₹ symbol on the profile page after
  adding a new expense
