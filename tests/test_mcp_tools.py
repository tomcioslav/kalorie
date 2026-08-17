# tests/test_mcp_tools.py
import pytest

from calorie_tracker.mcp_app import context, server
from calorie_tracker.models import Ingredient, Macros
from calorie_tracker.repositories import ingredients as ingredients_repo


@pytest.fixture(autouse=True)
def as_user(sqlite_db):
    token = context.current_user_id.set("test-user")
    yield
    context.current_user_id.reset(token)


def test_search_ingredient_returns_cached_hit_as_dict():
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    results = server.search_ingredient("egg")
    assert results[0]["ingredient_id"] == "usda#1"
    assert results[0]["calories_per_100g"] == 143


def test_create_custom_ingredient_returns_new_id():
    result = server.create_custom_ingredient(
        name="Homemade soup", serving_grams=300, calories=200, protein=8, carbs=20, fat=6
    )
    assert result["source"] == "custom"
    assert ingredients_repo.get_by_id(result["ingredient_id"]) is not None


def test_log_meal_and_get_daily_summary_round_trip():
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    entry = server.log_meal(
        meal_type="breakfast", items=[{"ingredient_id": "usda#1", "quantity_g": 100}], date="2026-08-16"
    )
    assert entry["totals"]["calories"] == pytest.approx(143)

    summary = server.get_daily_summary("2026-08-16")
    assert summary["total"]["calories"] == pytest.approx(143)
    assert len(summary["entries"]) == 1

    deleted = server.delete_meal_entry("2026-08-16", entry["entry_id"])
    assert deleted["deleted"] is True
    summary_after = server.get_daily_summary("2026-08-16")
    assert summary_after["total"]["calories"] == 0


def test_set_daily_goals_then_summary_shows_remaining():
    server.set_daily_goals(calories=2000, protein=100)
    summary = server.get_daily_summary("2026-08-16")
    assert summary["remaining"]["calories"] == 2000


def test_save_list_and_log_preset():
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    preset = server.save_meal_preset(name="Usual breakfast", items=[{"ingredient_id": "usda#1", "quantity_g": 100}])
    listed = server.list_meal_presets()
    assert any(p["preset_id"] == preset["preset_id"] for p in listed)

    entry = server.log_preset_meal(preset_id=preset["preset_id"], meal_type="breakfast", date="2026-08-16")
    assert entry["totals"]["calories"] == pytest.approx(143)


def test_list_meals_returns_range():
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    server.log_meal(meal_type="breakfast", items=[{"ingredient_id": "usda#1", "quantity_g": 50}], date="2026-08-15")
    server.log_meal(meal_type="dinner", items=[{"ingredient_id": "usda#1", "quantity_g": 50}], date="2026-08-16")
    result = server.list_meals("2026-08-15", "2026-08-16")
    assert len(result) == 2
