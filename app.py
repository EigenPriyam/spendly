from datetime import datetime, date
from typing import NamedTuple

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from database.db import get_db, init_db, seed_db, get_user_by_email, create_user
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Date filter helpers                                                 #
# ------------------------------------------------------------------ #

class DateRange(NamedTuple):
    start: str
    end: str


def _parse_date_param(value):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.strftime("%Y-%m-%d")


def _shift_year_month(year, month, months_back):
    index = year * 12 + (month - 1) - months_back
    return index // 12, index % 12 + 1


def _preset_range(months):
    today = date.today()
    year, month = _shift_year_month(today.year, today.month, months - 1)
    start = date(year, month, 1)
    return DateRange(start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d"))


def resolve_date_filter(args):
    """Parse/validate date_from & date_to query args and derive the active preset."""
    date_from = _parse_date_param(args.get("date_from"))
    date_to = _parse_date_param(args.get("date_to"))

    if not (date_from and date_to):
        date_from = None
        date_to = None
    elif date_from > date_to:
        flash("Start date must be before end date.")
        date_from = None
        date_to = None

    presets = {
        "this_month": _preset_range(1),
        "last_3_months": _preset_range(3),
        "last_6_months": _preset_range(6),
    }

    if date_from is None and date_to is None:
        active_preset = "all_time"
    elif (date_from, date_to) == presets["this_month"]:
        active_preset = "this_month"
    elif (date_from, date_to) == presets["last_3_months"]:
        active_preset = "last_3_months"
    elif (date_from, date_to) == presets["last_6_months"]:
        active_preset = "last_6_months"
    else:
        active_preset = "custom"

    return date_from, date_to, presets, active_preset


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        error = None
        if not name or not email or not password:
            error = "All fields are required."
        elif "@" not in email:
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif get_user_by_email(email):
            error = "An account with this email already exists."

        if error:
            return render_template("register.html", error=error, name=name, email=email)

        user_id = create_user(name, email, password)
        session["user_id"] = user_id
        return redirect(url_for("profile"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if not user or not check_password_hash(user["password_hash"], password):
            return render_template("login.html", error="Invalid email or password.", email=email)

        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template("login.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    date_from, date_to, presets, active_preset = resolve_date_filter(request.args)

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    stats = get_summary_stats(
        user_id, date_from=date_from, date_to=date_to
    )
    transactions = get_recent_transactions(
        user_id, date_from=date_from, date_to=date_to
    )
    categories = get_category_breakdown(
        user_id, date_from=date_from, date_to=date_to
    )

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
        presets=presets,
        active_preset=active_preset,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
