import uuid
from datetime import date as date_type
from datetime import datetime, timezone
from typing import get_args

from calorie_tracker.models import MealEntry, MealItem, MealType
from calorie_tracker.repositories import ingredients as ingredients_repo
from calorie_tracker.repositories import meal_entries as entries_repo

MEAL_TYPES: tuple[str, ...] = get_args(MealType)


class IngredientNotFoundError(Exception):
    pass


class InvalidDateError(ValueError):
    pass


class InvalidMealTypeError(ValueError):
    pass


def validate_date(value: str) -> str:
    """Return `value` if it is a canonical YYYY-MM-DD date, else raise.

    Dates go straight into the meal-entries sort key (DATE#{date}#ENTRY#{id}),
    so a non-canonical string ("2026-8-16", "20260816") sorts outside the range
    queries that back get_daily_summary/list_meals: the entry is written but is
    permanently invisible, silently under-reporting that day's calories. Reject
    it at write time instead. `date.fromisoformat` accepts several ISO 8601
    spellings on Python 3.11+, so we also require the canonical round-trip.
    """
    if not isinstance(value, str):
        raise InvalidDateError(f"date must be a YYYY-MM-DD string, got {value!r}")
    try:
        parsed = date_type.fromisoformat(value)
    except ValueError as exc:
        raise InvalidDateError(f"date must be in YYYY-MM-DD format, got {value!r}") from exc
    if parsed.isoformat() != value:
        raise InvalidDateError(
            f"date must be in YYYY-MM-DD format, got {value!r} (did you mean {parsed.isoformat()!r}?)"
        )
    return value


def validate_meal_type(value: str) -> str:
    """Return `value` if it is one of the allowed meal types, else raise."""
    if value not in MEAL_TYPES:
        raise InvalidMealTypeError(
            f"meal_type must be one of {', '.join(MEAL_TYPES)}; got {value!r}"
        )
    return value


def build_items(item_requests: list[dict]) -> list[MealItem]:
    items = []
    for req in item_requests:
        ingredient = ingredients_repo.get_by_id(req["ingredient_id"])
        if ingredient is None:
            raise IngredientNotFoundError(req["ingredient_id"])
        factor = req["quantity_g"] / 100.0
        items.append(
            MealItem(
                ingredient_id=ingredient.ingredient_id,
                name=ingredient.name,
                quantity_g=req["quantity_g"],
                macros=ingredient.per_100g.scaled(factor),
            )
        )
    return items


def log_meal(user_id: str, meal_type: str, item_requests: list[dict], date: str, notes: str = "") -> MealEntry:
    date = validate_date(date)
    meal_type = validate_meal_type(meal_type)
    entry = MealEntry(
        user_id=user_id,
        entry_id=uuid.uuid4().hex[:12],
        date=date,
        meal_type=meal_type,
        logged_at=datetime.now(timezone.utc).isoformat(),
        items=build_items(item_requests),
        notes=notes,
    )
    entries_repo.put(entry)
    return entry


def update_notes(user_id: str, date: str, entry_id: str, notes: str) -> MealEntry | None:
    date = validate_date(date)
    entry = entries_repo.get(user_id, date, entry_id)
    if entry is None:
        return None
    entry.notes = notes
    entries_repo.put(entry)
    return entry


def delete_entry(user_id: str, date: str, entry_id: str) -> None:
    date = validate_date(date)
    entries_repo.delete(user_id, date, entry_id)
