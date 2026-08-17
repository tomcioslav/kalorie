import uuid

from calorie_tracker.models import MealPreset
from calorie_tracker.repositories import meal_presets as presets_repo
from calorie_tracker.services.meal_logging import build_items, log_meal, validate_date, validate_meal_type


class PresetNotFoundError(Exception):
    pass


def save_preset(user_id: str, name: str, item_requests: list[dict]) -> MealPreset:
    preset = MealPreset(
        user_id=user_id,
        preset_id=uuid.uuid4().hex[:10],
        name=name,
        items=build_items(item_requests),
    )
    presets_repo.put(preset)
    return preset


def list_presets(user_id: str) -> list[MealPreset]:
    return presets_repo.list_for_user(user_id)


def log_from_preset(user_id: str, preset_id: str, meal_type: str, date: str, notes: str = ""):
    date = validate_date(date)
    meal_type = validate_meal_type(meal_type)
    preset = presets_repo.get(user_id, preset_id)
    if preset is None:
        raise PresetNotFoundError(preset_id)
    item_requests = [{"ingredient_id": i.ingredient_id, "quantity_g": i.quantity_g} for i in preset.items]
    return log_meal(user_id, meal_type, item_requests, date, notes)
