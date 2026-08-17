from calorie_tracker.models import MealPreset
from calorie_tracker.repositories.base import deserialize_items, get_connection, serialize_items


def put(preset: MealPreset) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO meal_presets (preset_id, user_id, name, items_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, preset_id) DO UPDATE SET
                name = excluded.name,
                items_json = excluded.items_json
            """,
            (preset.preset_id, preset.user_id, preset.name, serialize_items(preset.items)),
        )
        conn.commit()
    finally:
        conn.close()


def get(user_id: str, preset_id: str) -> MealPreset | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM meal_presets WHERE user_id = ? AND preset_id = ?",
            (user_id, preset_id),
        ).fetchone()
    finally:
        conn.close()
    return _to_preset(row) if row else None


def list_for_user(user_id: str) -> list[MealPreset]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM meal_presets WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        conn.close()
    return [_to_preset(row) for row in rows]


def _to_preset(row) -> MealPreset:
    return MealPreset(
        user_id=row["user_id"],
        preset_id=row["preset_id"],
        name=row["name"],
        items=deserialize_items(row["items_json"]),
    )
