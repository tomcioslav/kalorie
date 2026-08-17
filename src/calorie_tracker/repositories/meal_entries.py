from calorie_tracker.models import MealEntry
from calorie_tracker.repositories.base import deserialize_items, get_connection, serialize_items


def put(entry: MealEntry) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO meal_entries
                (entry_id, user_id, date, meal_type, logged_at, notes, items_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, entry_id) DO UPDATE SET
                date = excluded.date,
                meal_type = excluded.meal_type,
                logged_at = excluded.logged_at,
                notes = excluded.notes,
                items_json = excluded.items_json
            """,
            (
                entry.entry_id, entry.user_id, entry.date, entry.meal_type,
                entry.logged_at, entry.notes, serialize_items(entry.items),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get(user_id: str, date: str, entry_id: str) -> MealEntry | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM meal_entries WHERE user_id = ? AND date = ? AND entry_id = ?",
            (user_id, date, entry_id),
        ).fetchone()
    finally:
        conn.close()
    return _to_entry(row) if row else None


def delete(user_id: str, date: str, entry_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM meal_entries WHERE user_id = ? AND date = ? AND entry_id = ?",
            (user_id, date, entry_id),
        )
        conn.commit()
    finally:
        conn.close()


def query_range(user_id: str, start_date: str, end_date: str) -> list[MealEntry]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM meal_entries WHERE user_id = ? AND date BETWEEN ? AND ? ORDER BY date, entry_id",
            (user_id, start_date, end_date),
        ).fetchall()
    finally:
        conn.close()
    return [_to_entry(row) for row in rows]


def query_day(user_id: str, date: str) -> list[MealEntry]:
    return query_range(user_id, date, date)


def _to_entry(row) -> MealEntry:
    return MealEntry(
        user_id=row["user_id"],
        entry_id=row["entry_id"],
        date=row["date"],
        meal_type=row["meal_type"],
        logged_at=row["logged_at"],
        notes=row["notes"],
        items=deserialize_items(row["items_json"]),
    )
