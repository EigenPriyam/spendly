from datetime import datetime

from database.db import get_db


def _date_range_clause(date_from, date_to):
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", [date_from, date_to]
    return "", []


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()

    if not row:
        return None

    created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created_at.strftime("%B %Y"),
    }


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    try:
        date_filter_sql, extra_params = _date_range_clause(date_from, date_to)
        params = [user_id, *extra_params]

        totals_row = conn.execute(
            f"""
            SELECT
                COALESCE(SUM(amount), 0) AS total_spent,
                COUNT(*) AS transaction_count
            FROM expenses
            WHERE user_id = ?{date_filter_sql}
            """,
            params,
        ).fetchone()

        total_spent = float(totals_row["total_spent"])
        transaction_count = int(totals_row["transaction_count"])

        if transaction_count == 0:
            return {
                "total_spent": 0,
                "transaction_count": 0,
                "top_category": "—",
            }

        top_category_row = conn.execute(
            f"""
            SELECT category, SUM(amount) AS category_total
            FROM expenses
            WHERE user_id = ?{date_filter_sql}
            GROUP BY category
            ORDER BY category_total DESC
            LIMIT 1
            """,
            params,
        ).fetchone()

        top_category = top_category_row["category"] if top_category_row else "—"

        return {
            "total_spent": total_spent,
            "transaction_count": transaction_count,
            "top_category": top_category,
        }
    finally:
        conn.close()


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    date_filter_sql, extra_params = _date_range_clause(date_from, date_to)
    params = [user_id, *extra_params, limit]

    rows = conn.execute(
        f"""
        SELECT date, description, category, amount
        FROM expenses
        WHERE user_id = ?{date_filter_sql}
        ORDER BY date DESC, id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    date_filter_sql, extra_params = _date_range_clause(date_from, date_to)
    params = [user_id, *extra_params]

    rows = conn.execute(
        f"""
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?{date_filter_sql}
        GROUP BY category
        ORDER BY total DESC
        """,
        params,
    ).fetchall()
    conn.close()

    if not rows:
        return []

    grand_total = sum(row["total"] for row in rows)

    breakdown = []
    for row in rows:
        amount = float(row["total"])
        raw_pct = (amount / grand_total) * 100
        breakdown.append({
            "name": row["category"],
            "amount": amount,
            "pct": int(raw_pct),
        })

    remainder = 100 - sum(item["pct"] for item in breakdown)
    breakdown[0]["pct"] += remainder

    return breakdown


def create_expense(user_id, amount, category, date, description):
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, date, description),
    )
    conn.commit()
    expense_id = cursor.lastrowid
    conn.close()
    return expense_id
