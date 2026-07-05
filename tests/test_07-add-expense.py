"""
Tests for Step 7: Add Expense (GET/POST /expenses/add).

Spec: .claude/specs/07-add-expense.md

These tests treat the spec as the correctness contract -- they were written
without reading add_expense()'s implementation logic. What is asserted:

- `/expenses/add` (GET and POST) is logged-in only; unauthenticated requests
  redirect to `/login` and never write to the DB.
- GET renders a blank form with `amount`, `category` (a fixed-set select),
  `date`, and `description` fields.
- POST with valid amount/category/date/description inserts exactly one new
  row into `expenses` for the current session user and redirects to
  `/profile`.
- `category` is constrained to: Food, Transport, Bills, Health,
  Entertainment, Shopping, Other -- anything else is a validation error.
- A non-numeric or non-positive (zero/negative) amount is a validation
  error, not a crash, and does not insert a row.
- A malformed date is a validation error, not a crash, and does not insert
  a row.
- Empty amount/category/date (individually) is a validation error and never
  inserts a partial row.
- `description` is optional -- blank description still succeeds.
- On a validation error the form is redisplayed with the user's previously
  entered values still present (the raw submitted values reappear in the
  response body) rather than being cleared.

Fixture design notes
---------------------
Mirrors `tests/test_06-profile-date-filter.py`'s isolation strategy:
`database/db.py` hardcodes `DB_PATH` as a module-level global pointing at a
real `spendly.db` file, and `app.py` calls `init_db()/seed_db()` at import
time. To keep these tests fully isolated from the developer's real database:

1. Monkeypatch `database.db.DB_PATH` to a throwaway path *before* `app` is
   imported for the first time, so the module-level init/seed call never
   touches the real `spendly.db`.
2. Re-patch `database.db.DB_PATH` to a fresh per-test file (via `tmp_path`)
   inside the `app` fixture and call `init_db()` again, so every test gets
   its own empty database.
"""

import os
import re
import tempfile

import pytest

import database.db as db_module

# Redirect app.py's module-level init_db()/seed_db() call (which runs the
# instant `app` is first imported) away from the real spendly.db file.
db_module.DB_PATH = os.path.join(
    tempfile.gettempdir(), "spendly_test_import_only_07.db"
)

from app import app as flask_app  # noqa: E402
from database.db import init_db, create_user  # noqa: E402


EXPENSE_CATEGORIES = [
    "Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other",
]


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
def other_user(app):
    with app.app_context():
        user_id = create_user("Bob Builder", "bob@example.com", "supersecret2")
    return {"id": user_id, "email": "bob@example.com", "password": "supersecret2"}


@pytest.fixture
def auth_client(client, test_user):
    """A test client that is already logged in as `test_user`."""
    client.post(
        "/login",
        data={"email": test_user["email"], "password": test_user["password"]},
    )
    return client


# ------------------------------------------------------------------ #
# DB helpers (direct, parameterised -- no reliance on app internals)  #
# ------------------------------------------------------------------ #

def _all_expenses():
    conn = db_module.get_db()
    rows = conn.execute("SELECT * FROM expenses").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _expenses_for_user(user_id):
    conn = db_module.get_db()
    rows = conn.execute(
        "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _valid_payload(**overrides):
    payload = {
        "amount": "45.50",
        "category": "Food",
        "date": "2026-06-15",
        "description": "Groceries",
    }
    payload.update(overrides)
    return payload


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_add_expense_while_logged_out_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302, "Unauthenticated GET should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_add_expense_while_logged_out_redirects_to_login(self, client):
        response = client.post("/expenses/add", data=_valid_payload())
        assert response.status_code == 302, "Unauthenticated POST should redirect"
        assert "/login" in response.headers["Location"]

    def test_post_add_expense_while_logged_out_does_not_insert(self, client):
        client.post("/expenses/add", data=_valid_payload())
        assert _all_expenses() == [], (
            "No expense should be inserted for an unauthenticated request"
        )


# ------------------------------------------------------------------ #
# GET renders the form                                                #
# ------------------------------------------------------------------ #

class TestGetForm:
    def test_get_add_expense_while_logged_in_returns_200(self, auth_client):
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200

    def test_get_add_expense_form_has_expected_fields(self, auth_client):
        response = auth_client.get("/expenses/add")
        html = response.data.decode()

        assert 'name="amount"' in html, "Form must have an amount field"
        assert 'name="category"' in html, "Form must have a category field"
        assert 'name="date"' in html, "Form must have a date field"
        assert 'name="description"' in html, "Form must have a description field"

    @pytest.mark.parametrize("category", EXPENSE_CATEGORIES)
    def test_get_add_expense_form_category_select_offers_each_fixed_category(
        self, auth_client, category
    ):
        response = auth_client.get("/expenses/add")
        html = response.data.decode()

        assert re.search(rf'>\s*{re.escape(category)}\s*<', html), (
            f"Category select should offer '{category}' as an option"
        )


# ------------------------------------------------------------------ #
# Successful submission                                               #
# ------------------------------------------------------------------ #

class TestSuccessfulAdd:
    def test_post_valid_expense_redirects_to_profile(self, auth_client):
        response = auth_client.post("/expenses/add", data=_valid_payload())
        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

    def test_post_valid_expense_inserts_row_with_correct_fields(
        self, auth_client, test_user
    ):
        auth_client.post(
            "/expenses/add",
            data=_valid_payload(
                amount="45.50", category="Food", date="2026-06-15",
                description="Groceries",
            ),
        )
        rows = _expenses_for_user(test_user["id"])
        assert len(rows) == 1, "Exactly one expense should be inserted"

        row = rows[0]
        assert row["user_id"] == test_user["id"]
        assert float(row["amount"]) == 45.50
        assert row["category"] == "Food"
        assert row["date"] == "2026-06-15"
        assert row["description"] == "Groceries"

    def test_post_valid_expense_only_creates_one_new_row(self, auth_client):
        before = len(_all_expenses())
        auth_client.post("/expenses/add", data=_valid_payload())
        after = len(_all_expenses())
        assert after == before + 1

    @pytest.mark.parametrize("category", EXPENSE_CATEGORIES)
    def test_post_accepts_every_fixed_category(self, auth_client, test_user, category):
        auth_client.post(
            "/expenses/add", data=_valid_payload(category=category)
        )
        rows = _expenses_for_user(test_user["id"])
        assert len(rows) == 1
        assert rows[0]["category"] == category

    def test_post_blank_description_still_succeeds_and_saves(
        self, auth_client, test_user
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(description="")
        )
        assert response.status_code == 302, "Blank description must not block success"
        assert "/profile" in response.headers["Location"]

        rows = _expenses_for_user(test_user["id"])
        assert len(rows) == 1
        assert rows[0]["amount"] == 45.50
        assert rows[0]["category"] == "Food"
        assert rows[0]["date"] == "2026-06-15"

    def test_new_expense_belongs_to_current_session_user_only(
        self, auth_client, test_user, other_user
    ):
        auth_client.post("/expenses/add", data=_valid_payload())

        assert len(_expenses_for_user(test_user["id"])) == 1
        assert _expenses_for_user(other_user["id"]) == [], (
            "The expense must be attributed to the logged-in user, not another user"
        )


# ------------------------------------------------------------------ #
# Category validation                                                 #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    @pytest.mark.parametrize(
        "bad_category", ["Rent", "food", "", "Groceries", "<script>alert(1)</script>"]
    )
    def test_post_invalid_category_does_not_insert(
        self, auth_client, test_user, bad_category
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(category=bad_category)
        )
        assert response.status_code == 200, (
            "An invalid category should redisplay the form, not redirect"
        )
        assert _expenses_for_user(test_user["id"]) == []

    def test_post_invalid_category_does_not_crash(self, auth_client):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(category="NotARealCategory")
        )
        assert response.status_code == 200


# ------------------------------------------------------------------ #
# Amount validation                                                   #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    @pytest.mark.parametrize(
        "bad_amount", ["abc", "twenty", "12.5.6", "$50", "12,50", "NaN"]
    )
    def test_post_non_numeric_amount_does_not_insert_and_does_not_crash(
        self, auth_client, test_user, bad_amount
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(amount=bad_amount)
        )
        assert response.status_code == 200, (
            f"Non-numeric amount {bad_amount!r} must redisplay the form, not crash"
        )
        assert _expenses_for_user(test_user["id"]) == []

    @pytest.mark.parametrize("bad_amount", ["0", "-1", "-100.50", "0.0"])
    def test_post_non_positive_amount_does_not_insert(
        self, auth_client, test_user, bad_amount
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(amount=bad_amount)
        )
        assert response.status_code == 200
        assert _expenses_for_user(test_user["id"]) == [], (
            f"Zero/negative amount {bad_amount!r} must not be inserted"
        )

    def test_post_valid_positive_decimal_amount_succeeds(self, auth_client, test_user):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(amount="0.01")
        )
        assert response.status_code == 302
        rows = _expenses_for_user(test_user["id"])
        assert len(rows) == 1
        assert float(rows[0]["amount"]) == 0.01


# ------------------------------------------------------------------ #
# Date validation                                                     #
# ------------------------------------------------------------------ #

class TestDateValidation:
    @pytest.mark.parametrize(
        "bad_date",
        ["not-a-date", "2026/06/15", "15-06-2026", "2026-13-01", "2026-02-30", "2026-06"],
    )
    def test_post_malformed_date_does_not_insert_and_does_not_crash(
        self, auth_client, test_user, bad_date
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(date=bad_date)
        )
        assert response.status_code == 200, (
            f"Malformed date {bad_date!r} must redisplay the form, not crash"
        )
        assert _expenses_for_user(test_user["id"]) == []

    def test_post_valid_iso_date_succeeds(self, auth_client, test_user):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(date="2026-01-05")
        )
        assert response.status_code == 302
        rows = _expenses_for_user(test_user["id"])
        assert len(rows) == 1
        assert rows[0]["date"] == "2026-01-05"


# ------------------------------------------------------------------ #
# Required-field validation                                           #
# ------------------------------------------------------------------ #

class TestRequiredFields:
    def test_post_empty_amount_shows_error_and_does_not_insert(
        self, auth_client, test_user
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(amount="")
        )
        assert response.status_code == 200
        assert _expenses_for_user(test_user["id"]) == []

    def test_post_empty_category_shows_error_and_does_not_insert(
        self, auth_client, test_user
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(category="")
        )
        assert response.status_code == 200
        assert _expenses_for_user(test_user["id"]) == []

    def test_post_empty_date_shows_error_and_does_not_insert(
        self, auth_client, test_user
    ):
        response = auth_client.post(
            "/expenses/add", data=_valid_payload(date="")
        )
        assert response.status_code == 200
        assert _expenses_for_user(test_user["id"]) == []

    def test_post_missing_amount_category_and_date_together_does_not_insert(
        self, auth_client, test_user
    ):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "", "category": "", "date": "", "description": "x"},
        )
        assert response.status_code == 200
        assert _expenses_for_user(test_user["id"]) == [], (
            "No partial row should ever be created"
        )


# ------------------------------------------------------------------ #
# Form redisplay preserves previously entered values on error         #
# ------------------------------------------------------------------ #

class TestErrorRedisplayPreservesInput:
    def test_invalid_amount_error_redisplays_previously_entered_values(
        self, auth_client
    ):
        response = auth_client.post(
            "/expenses/add",
            data=_valid_payload(
                amount="not-a-number", category="Transport",
                date="2026-06-15", description="Taxi fare",
            ),
        )
        html = response.data.decode()

        assert "not-a-number" in html, "Previously entered amount should be preserved"
        assert "Taxi fare" in html, "Previously entered description should be preserved"

    def test_invalid_date_error_redisplays_previously_entered_values(
        self, auth_client
    ):
        response = auth_client.post(
            "/expenses/add",
            data=_valid_payload(
                amount="99.99", category="Bills",
                date="not-a-real-date", description="Water bill",
            ),
        )
        html = response.data.decode()

        assert "99.99" in html, "Previously entered amount should be preserved"
        assert "Water bill" in html, "Previously entered description should be preserved"

    def test_validation_error_does_not_return_a_server_error(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data=_valid_payload(amount="not-a-number", date="also-not-a-date"),
        )
        assert response.status_code < 500, "Validation errors must never crash the app"
