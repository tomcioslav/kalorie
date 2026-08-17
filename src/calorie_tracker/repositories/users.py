from calorie_tracker.models import UserGoals
from calorie_tracker.repositories.base import get_connection


def get_goals(user_id: str) -> UserGoals | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return UserGoals(
        user_id=row["user_id"],
        daily_calories=row["daily_calories"],
        daily_protein=row["daily_protein"],
        daily_carbs=row["daily_carbs"],
        daily_fat=row["daily_fat"],
    )


def set_goals(goals: UserGoals) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (user_id, daily_calories, daily_protein, daily_carbs, daily_fat)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                daily_calories = excluded.daily_calories,
                daily_protein = excluded.daily_protein,
                daily_carbs = excluded.daily_carbs,
                daily_fat = excluded.daily_fat
            """,
            (goals.user_id, goals.daily_calories, goals.daily_protein, goals.daily_carbs, goals.daily_fat),
        )
        conn.commit()
    finally:
        conn.close()
