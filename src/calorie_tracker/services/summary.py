from dataclasses import dataclass

from calorie_tracker.models import MealEntry, UserGoals, ZERO_MACROS, Macros
from calorie_tracker.repositories import meal_entries as entries_repo
from calorie_tracker.repositories import users as users_repo
from calorie_tracker.services.meal_logging import validate_date


@dataclass
class DailySummary:
    date: str
    entries: list[MealEntry]
    total: Macros
    goals: UserGoals | None
    remaining_calories: float | None
    remaining_protein: float | None
    remaining_carbs: float | None
    remaining_fat: float | None


def get_daily_summary(user_id: str, date: str) -> DailySummary:
    # A malformed date would quietly return an empty day rather than an error.
    date = validate_date(date)
    entries = entries_repo.query_day(user_id, date)
    total = ZERO_MACROS
    for entry in entries:
        total = total + entry.totals

    goals = users_repo.get_goals(user_id)
    remaining_calories = remaining_protein = remaining_carbs = remaining_fat = None
    if goals is not None:
        remaining_calories = goals.daily_calories - total.calories
        if goals.daily_protein is not None:
            remaining_protein = goals.daily_protein - total.protein
        if goals.daily_carbs is not None:
            remaining_carbs = goals.daily_carbs - total.carbs
        if goals.daily_fat is not None:
            remaining_fat = goals.daily_fat - total.fat

    return DailySummary(
        date=date,
        entries=entries,
        total=total,
        goals=goals,
        remaining_calories=remaining_calories,
        remaining_protein=remaining_protein,
        remaining_carbs=remaining_carbs,
        remaining_fat=remaining_fat,
    )


def list_meals(user_id: str, start_date: str, end_date: str) -> list[MealEntry]:
    return entries_repo.query_range(user_id, validate_date(start_date), validate_date(end_date))
