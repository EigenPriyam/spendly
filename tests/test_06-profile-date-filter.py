"""
Tests for Step 6: date-range filter on GET /profile.

Spec: .claude/specs/06-profile-date-filter.md

These tests treat the spec as the correctness contract:
- No new routes; GET /profile reads optional `date_from` / `date_to` query params.
- Absent or malformed params -> fall back to the unfiltered ("All Time") view.
- `date_from > date_to` -> fall back to unfiltered AND flash
  "Start date must be before end date."
- Only one of the two params supplied -> fall back to unfiltered (no flash).
- The four quick presets (This Month / Last 3 Months / Last 6 Months / All Time)
  are rendered as links built with `url_for("profile", date_from=..., date_to=...)`,
  with "All Time" carrying no query params.
- All three data sections (summary stats, recent transactions, category
  breakdown) must respect whatever range is active.

Fixture design notes
---------------------
`database/db.py` hardcodes `DB_PATH` as a module-level global (a real file,
`spendly.db`, at the project root) rather than reading it from Flask's
`app.config`. `app.py` also calls `init_db()` / `seed_db()` once at import
time. To keep tests fully isolated from the developer's real database file we:

1. Monkeypatch `database.db.DB_PATH` to a throwaway path in the OS temp dir
   *before* `app` is imported for the first time, so the module-level
   `init_db()/seed_db()` call in app.py never touches the real `spendly.db`.
2. Re-patch `database.db.DB_PATH` to a fresh per-test file (via pytest's
   `tmp_path`) inside the `app` fixture, and call `init_db()` again, so every
   test gets its own empty database. Because `get_db()` looks up `DB_PATH` as
   a module global at call time, patching `database.db.DB_PATH` is enough --
   no need to patch anything in `database/queries.py`, which merely imports
   the `get_db` function object.
3. Expense fixtures never rely on `seed_db()`'s fixed 2026-05 seed data (which
   would only coincidentally match "this month" presets on some run dates).
   Instead, test expenses are planted at dates computed *relative to
   `date.today()` at test-run time*, so the suite is correct regardless of
   when it is actually executed.
"""

import os
import re
import tempfile
from datetime import date

import pytest

import database.db as db_module

# Redirect app.py's module-level init_db()/seed_db() call (which runs the
# instant `app` is first imported) away from the real spendly.db file.
db_module.DB_PATH = os.path.join(
    tempfile.gettempdir(), "spendly_test_import_only.db"
)

from app import app as flask_app  # noqa: E402
from database.db import init_db, create_user  # noqa: E402


# ------------------------------------------------------------------ #
# Date arithmetic helpers (independent of app.py's private helpers)   #
# ------------------------------------------------------------------ #

def _months_before_today(months_back, day=10):
    """Return a date `months_back` whole calendar months before the current
    month, on the given day-of-month (default 10, always valid)."""
    today = date.today()
    total = today.year * 12 + (today.month - 1) - months_back
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, day)


def _this_month_window():
    today = date.today()
    return date(today.year, today.month, 1).isoformat(), today.isoformat()


def _last_n_months_window(n):
    today = date.today()
    start = _months_before_today(n - 1, day=1)
    return start.isoformat(), today.isoformat()


# ------------------------------------------------------------------ #
# HTML extraction helpers (black-box parsing of rendered profile page)#
# ------------------------------------------------------------------ #

def _get_stat(html, label):
    """Pull the stat-value text following a given stat-label on the page."""
    match = re.search(
        rf'<span class="stat-label">{re.escape(label)}</span>\s*'
        rf'<span class="stat-value">([^<]*)</span>',
        html,
    )
    assert match, f"Could not locate stat '{label}' on the profile page"
    return match.group(1).strip()


def _get_transaction_rows(html):
    """Return a list of (date, description, category, amount_str) tuples for
    every row rendered in the 'Recent transactions' table."""
    return re.findall(
        r'<td>(\d{4}-\d{2}-\d{2})</td>\s*'
        r'<td>([^<]*)</td>\s*'
        r'<td><span class="category-tag">([^<]*)</span></td>\s*'
        r'<td class="align-right">([^<]*)</td>',
        html,
    )


def _get_category_rows(html):
    """Return a list of (category_name, amount_str) tuples for every row in
    the 'Category breakdown' section."""
    return re.findall(
        r'<span class="category-name">([^<]*)</span>.*?'
        r'<span class="category-amount">([^<]*)</span>',
        html,
        re.S,
    )


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_spendly.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)

    flask_app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        init_db()

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def test_user(app):
    with app.app_context():
        user_id = create_user("Ada Lovelace", "ada@example.com", "supersecret1")
    return {"id": user_id, "email": "ada@example.com", "password": "supersecret1"}


@pytest.fixture
def auth_client(client, test_user):
    """A test client that is already logged in as `test_user`."""
    client.post(
        "/login",
        data={"email": test_user["email"], "password": test_user["password"]},
    )
    return client


def _insert_expense(user_id, amount, category, expense_date, description=""):
    conn = db_module.get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def bucketed_expenses(test_user):
    """Four expenses, each in a distinct time bucket relative to `today`:
    - this_month:        today                          (Food,      100.00)
    - one_month_back:    1 calendar month ago            (Transport,  50.00)
    - four_months_back:  4 calendar months ago           (Bills,      80.00)
    - eight_months_back: 8 calendar months ago           (Shopping,  300.00)

    By construction (see docstring math in _months_before_today):
    - only "this_month" falls inside the This-Month window
    - "this_month" + "one_month_back" fall inside the Last-3-Months window
    - "this_month" + "one_month_back" + "four_months_back" fall inside the
      Last-6-Months window
    - "eight_months_back" falls outside every preset except All Time
    """
    today = date.today()
    buckets = {
        "this_month": {
            "date": today.isoformat(), "category": "Food", "amount": 100.00,
        },
        "one_month_back": {
            "date": _months_before_today(1).isoformat(),
            "category": "Transport", "amount": 50.00,
        },
        "four_months_back": {
            "date": _months_before_today(4).isoformat(),
            "category": "Bills", "amount": 80.00,
        },
        "eight_months_back": {
            "date": _months_before_today(8).isoformat(),
            "category": "Shopping", "amount": 300.00,
        },
    }
    for name, bucket in buckets.items():
        _insert_expense(
            test_user["id"], bucket["amount"], bucket["category"],
            bucket["date"], description=f"{name} expense",
        )
    return buckets


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_get_profile_no_params_redirects_to_login(self, client):
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile should redirect"
        assert "/login" in response.headers["Location"], (
            "Unauthenticated /profile should redirect to /login"
        )

    def test_unauthenticated_get_profile_with_query_params_redirects_to_login(self, client):
        response = client.get(
            "/profile", query_string={"date_from": "2026-01-01", "date_to": "2026-01-31"}
        )
        assert response.status_code == 302, (
            "Unauthenticated /profile with query params should still redirect"
        )
        assert "/login" in response.headers["Location"], (
            "Auth guard must apply regardless of query params"
        )


# ------------------------------------------------------------------ #
# Unfiltered baseline (no regression vs Step 5)                       #
# ------------------------------------------------------------------ #

class TestUnfilteredBaseline:
    def test_unfiltered_profile_summary_stats_match_full_history(
        self, auth_client, bucketed_expenses
    ):
        response = auth_client.get("/profile")
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"
        assert _get_stat(html, "Top category") == "Shopping"

    def test_unfiltered_profile_lists_all_transactions_in_date_desc_order(
        self, auth_client, bucketed_expenses
    ):
        response = auth_client.get("/profile")
        html = response.data.decode()

        rows = _get_transaction_rows(html)
        assert len(rows) == 4, "All 4 seeded expenses should appear when unfiltered"

        dates = [row[0] for row in rows]
        assert dates == sorted(dates, reverse=True), (
            "Transactions must be ordered most-recent first"
        )
        assert dates[0] == bucketed_expenses["this_month"]["date"]
        assert dates[-1] == bucketed_expenses["eight_months_back"]["date"]

    def test_unfiltered_profile_shows_full_category_breakdown(
        self, auth_client, bucketed_expenses
    ):
        response = auth_client.get("/profile")
        html = response.data.decode()

        categories = {name for name, _ in _get_category_rows(html)}
        assert categories == {"Food", "Transport", "Bills", "Shopping"}

    def test_no_query_params_identical_to_explicit_empty_params(
        self, auth_client, bucketed_expenses
    ):
        """Absent date_from/date_to must behave identically to Step 5's
        original unfiltered view (no regression)."""
        plain = auth_client.get("/profile")
        explicit_blank = auth_client.get(
            "/profile", query_string={"date_from": "", "date_to": ""}
        )

        plain_html = plain.data.decode()
        blank_html = explicit_blank.data.decode()

        assert _get_stat(plain_html, "Total spent") == _get_stat(blank_html, "Total spent")
        assert _get_stat(plain_html, "Transactions") == _get_stat(blank_html, "Transactions")
        assert _get_stat(plain_html, "Top category") == _get_stat(blank_html, "Top category")
        assert _get_transaction_rows(plain_html) == _get_transaction_rows(blank_html)
        assert _get_category_rows(plain_html) == _get_category_rows(blank_html)

    def test_user_with_no_expenses_sees_zeroed_stats_not_error(self, auth_client):
        """A brand new user with zero expenses at all should see empty state,
        not a 500 or an exception."""
        response = auth_client.get("/profile")
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹0.00"
        assert _get_stat(html, "Transactions") == "0"
        assert _get_stat(html, "Top category") == "—"
        assert _get_transaction_rows(html) == []
        assert _get_category_rows(html) == []


# ------------------------------------------------------------------ #
# Quick presets                                                       #
# ------------------------------------------------------------------ #

class TestQuickPresets:
    def test_this_month_preset_filters_all_sections_to_current_month(
        self, auth_client, bucketed_expenses
    ):
        date_from, date_to = _this_month_window()
        response = auth_client.get(
            "/profile", query_string={"date_from": date_from, "date_to": date_to}
        )
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹100.00"
        assert _get_stat(html, "Transactions") == "1"
        assert _get_stat(html, "Top category") == "Food"

        rows = _get_transaction_rows(html)
        assert len(rows) == 1
        assert rows[0][0] == bucketed_expenses["this_month"]["date"]
        assert rows[0][2] == "Food"

        categories = {name for name, _ in _get_category_rows(html)}
        assert categories == {"Food"}

    def test_last_3_months_preset_includes_current_and_prior_month_only(
        self, auth_client, bucketed_expenses
    ):
        date_from, date_to = _last_n_months_window(3)
        response = auth_client.get(
            "/profile", query_string={"date_from": date_from, "date_to": date_to}
        )
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹150.00"
        assert _get_stat(html, "Transactions") == "2"
        assert _get_stat(html, "Top category") == "Food"

        categories = {name for name, _ in _get_category_rows(html)}
        assert categories == {"Food", "Transport"}
        assert "Bills" not in categories
        assert "Shopping" not in categories

    def test_last_6_months_preset_includes_up_to_six_months_back(
        self, auth_client, bucketed_expenses
    ):
        date_from, date_to = _last_n_months_window(6)
        response = auth_client.get(
            "/profile", query_string={"date_from": date_from, "date_to": date_to}
        )
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹230.00"
        assert _get_stat(html, "Transactions") == "3"
        assert _get_stat(html, "Top category") == "Food"

        categories = {name for name, _ in _get_category_rows(html)}
        assert categories == {"Food", "Transport", "Bills"}
        assert "Shopping" not in categories, "8-months-back expense must be excluded"

    def test_all_time_preset_passes_no_query_params_and_shows_full_history(
        self, auth_client, bucketed_expenses
    ):
        response = auth_client.get("/profile")
        html = response.data.decode()

        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"
        assert len(_get_transaction_rows(html)) == 4

    def test_preset_links_rendered_with_url_for_and_expected_query_params(
        self, auth_client, bucketed_expenses, app
    ):
        response = auth_client.get("/profile")
        html = response.data.decode()

        this_month_from, this_month_to = _this_month_window()
        last3_from, last3_to = _last_n_months_window(3)
        last6_from, last6_to = _last_n_months_window(6)

        with app.test_request_context():
            from flask import url_for
            this_month_href = url_for(
                "profile", date_from=this_month_from, date_to=this_month_to
            )
            last3_href = url_for("profile", date_from=last3_from, date_to=last3_to)
            last6_href = url_for("profile", date_from=last6_from, date_to=last6_to)
            all_time_href = url_for("profile")

        assert f'href="{this_month_href}"' in html, "This Month preset link mismatch"
        assert f'href="{last3_href}"' in html, "Last 3 Months preset link mismatch"
        assert f'href="{last6_href}"' in html, "Last 6 Months preset link mismatch"
        assert f'href="{all_time_href}"' in html, (
            "All Time preset must link to /profile with no query params"
        )
        assert "date_from" not in all_time_href and "date_to" not in all_time_href


# ------------------------------------------------------------------ #
# Custom date range                                                   #
# ------------------------------------------------------------------ #

class TestCustomDateRange:
    def test_custom_valid_range_filters_all_three_sections(
        self, auth_client, bucketed_expenses
    ):
        # Window covering exactly the "four_months_back" bucket: it starts at
        # the Last-6-Months boundary and ends at the Last-3-Months boundary,
        # excluding "one_month_back", "this_month" and "eight_months_back".
        date_from = _months_before_today(5, day=1).isoformat()
        date_to = _months_before_today(2, day=1).isoformat()

        response = auth_client.get(
            "/profile", query_string={"date_from": date_from, "date_to": date_to}
        )
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹80.00"
        assert _get_stat(html, "Transactions") == "1"
        assert _get_stat(html, "Top category") == "Bills"

        rows = _get_transaction_rows(html)
        assert len(rows) == 1
        assert rows[0][0] == bucketed_expenses["four_months_back"]["date"]
        assert rows[0][2] == "Bills"

        categories = _get_category_rows(html)
        assert categories == [("Bills", "₹80.00")]

    def test_custom_range_boundaries_are_inclusive(self, auth_client, bucketed_expenses):
        exact_date = bucketed_expenses["this_month"]["date"]
        response = auth_client.get(
            "/profile", query_string={"date_from": exact_date, "date_to": exact_date}
        )
        html = response.data.decode()

        assert _get_stat(html, "Total spent") == "₹100.00"
        assert _get_stat(html, "Transactions") == "1"
        rows = _get_transaction_rows(html)
        assert len(rows) == 1
        assert rows[0][0] == exact_date

    def test_custom_range_amounts_always_show_rupee_symbol(
        self, auth_client, bucketed_expenses
    ):
        date_from, date_to = _last_n_months_window(6)
        response = auth_client.get(
            "/profile", query_string={"date_from": date_from, "date_to": date_to}
        )
        html = response.data.decode()

        assert _get_stat(html, "Total spent").startswith("₹")
        for _name, amount in _get_category_rows(html):
            assert amount.startswith("₹"), "Category amounts must show the rupee symbol"
        for row in _get_transaction_rows(html):
            assert row[3].startswith("₹"), "Transaction amounts must show the rupee symbol"


# ------------------------------------------------------------------ #
# Validation                                                          #
# ------------------------------------------------------------------ #

class TestValidation:
    def test_date_from_after_date_to_falls_back_and_flashes_message(
        self, auth_client, bucketed_expenses
    ):
        date_from = date.today().isoformat()
        date_to = bucketed_expenses["eight_months_back"]["date"]  # earlier than date_from

        response = auth_client.get(
            "/profile", query_string={"date_from": date_from, "date_to": date_to}
        )
        html = response.data.decode()

        assert response.status_code == 200, "Invalid range must not error out"
        assert "Start date must be before end date." in html, (
            "Expected a flashed validation message"
        )
        # Falls back to the full unfiltered view.
        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"

    @pytest.mark.parametrize(
        "bad_date_from",
        ["not-a-date", "2026/01/31", "", "0000-00-00", "31-01-2026"],
    )
    def test_malformed_date_from_falls_back_without_crashing(
        self, auth_client, bucketed_expenses, bad_date_from
    ):
        response = auth_client.get(
            "/profile",
            query_string={"date_from": bad_date_from, "date_to": "2026-01-31"},
        )
        html = response.data.decode()

        assert response.status_code == 200, (
            f"Malformed date_from={bad_date_from!r} must not raise a 500"
        )
        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"
        assert "Start date must be before end date." not in html

    @pytest.mark.parametrize(
        "bad_date_to",
        ["not-a-date", "2026/01/31", "", "0000-00-00"],
    )
    def test_malformed_date_to_falls_back_without_crashing(
        self, auth_client, bucketed_expenses, bad_date_to
    ):
        response = auth_client.get(
            "/profile",
            query_string={"date_from": "2026-01-01", "date_to": bad_date_to},
        )
        html = response.data.decode()

        assert response.status_code == 200, (
            f"Malformed date_to={bad_date_to!r} must not raise a 500"
        )
        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"

    def test_only_date_from_supplied_falls_back_to_unfiltered(
        self, auth_client, bucketed_expenses
    ):
        response = auth_client.get(
            "/profile", query_string={"date_from": date.today().isoformat()}
        )
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"
        assert "Start date must be before end date." not in html, (
            "A single supplied param should silently fall back, no flash expected"
        )

    def test_only_date_to_supplied_falls_back_to_unfiltered(
        self, auth_client, bucketed_expenses
    ):
        response = auth_client.get(
            "/profile", query_string={"date_to": date.today().isoformat()}
        )
        html = response.data.decode()

        assert response.status_code == 200
        assert _get_stat(html, "Total spent") == "₹530.00"
        assert _get_stat(html, "Transactions") == "4"
        assert "Start date must be before end date." not in html


# ------------------------------------------------------------------ #
# No results in range                                                 #
# ------------------------------------------------------------------ #

class TestNoResultsInRange:
    def test_range_with_no_matching_expenses_shows_zeroed_stats_and_empty_lists(
        self, auth_client, bucketed_expenses
    ):
        # Far in the past -- no seeded expense falls anywhere near this window.
        response = auth_client.get(
            "/profile",
            query_string={"date_from": "2000-01-01", "date_to": "2000-01-31"},
        )
        html = response.data.decode()

        assert response.status_code == 200, (
            "An empty result set must render normally, not error"
        )
        assert _get_stat(html, "Total spent") == "₹0.00"
        assert _get_stat(html, "Transactions") == "0"
        assert _get_stat(html, "Top category") == "—"
        assert _get_transaction_rows(html) == []
        assert _get_category_rows(html) == []
