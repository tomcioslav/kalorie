import pytest

from calorie_tracker.models import Ingredient, Macros, UserGoals
from calorie_tracker.repositories import ingredients as ingredients_repo
from calorie_tracker.repositories import users as users_repo
from calorie_tracker.services import meal_logging, presets, summary


def _seed_egg(sqlite_db):
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))


def test_log_meal_computes_totals_from_ingredient(sqlite_db):
    _seed_egg(sqlite_db)
    entry = meal_logging.log_meal(
        user_id="u1",
        meal_type="breakfast",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 100}],
        date="2026-08-16",
    )
    assert entry.items[0].macros.calories == pytest.approx(143)
    assert entry.totals.calories == pytest.approx(143)


def test_log_meal_raises_for_unknown_ingredient(sqlite_db):
    with pytest.raises(meal_logging.IngredientNotFoundError):
        meal_logging.log_meal(
            user_id="u1",
            meal_type="breakfast",
            item_requests=[{"ingredient_id": "usda#missing", "quantity_g": 50}],
            date="2026-08-16",
        )


def test_delete_entry_removes_it(sqlite_db):
    _seed_egg(sqlite_db)
    entry = meal_logging.log_meal(
        user_id="u1", meal_type="breakfast",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 50}], date="2026-08-16",
    )
    meal_logging.delete_entry("u1", "2026-08-16", entry.entry_id)
    from calorie_tracker.repositories import meal_entries as entries_repo
    assert entries_repo.get("u1", "2026-08-16", entry.entry_id) is None


def test_update_notes_changes_only_notes(sqlite_db):
    _seed_egg(sqlite_db)
    entry = meal_logging.log_meal(
        user_id="u1", meal_type="breakfast",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 50}], date="2026-08-16",
    )
    updated = meal_logging.update_notes("u1", "2026-08-16", entry.entry_id, "actually 2 eggs worth")
    assert updated.notes == "actually 2 eggs worth"
    assert updated.items == entry.items


def test_get_daily_summary_computes_remaining_against_goals(sqlite_db):
    _seed_egg(sqlite_db)
    users_repo.set_goals(UserGoals(user_id="u1", daily_calories=2000, daily_protein=100))
    meal_logging.log_meal(
        user_id="u1", meal_type="breakfast",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 100}], date="2026-08-16",
    )
    result = summary.get_daily_summary("u1", "2026-08-16")
    assert result.total.calories == pytest.approx(143)
    assert result.remaining_calories == pytest.approx(2000 - 143)
    assert result.remaining_protein == pytest.approx(100 - 12.6)
    assert result.remaining_carbs is None


def test_get_daily_summary_without_goals_has_no_remaining(sqlite_db):
    result = summary.get_daily_summary("u1", "2026-08-16")
    assert result.goals is None
    assert result.remaining_calories is None


def test_list_meals_returns_entries_in_range(sqlite_db):
    _seed_egg(sqlite_db)
    meal_logging.log_meal(
        user_id="u1", meal_type="breakfast",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 50}], date="2026-08-15",
    )
    meal_logging.log_meal(
        user_id="u1", meal_type="dinner",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 50}], date="2026-08-16",
    )
    result = summary.list_meals("u1", "2026-08-15", "2026-08-16")
    assert len(result) == 2


def test_save_and_log_preset(sqlite_db):
    _seed_egg(sqlite_db)
    preset = presets.save_preset(
        user_id="u1", name="Usual breakfast",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 100}],
    )
    assert preset.name == "Usual breakfast"
    listed = presets.list_presets("u1")
    assert listed == [preset]

    entry = presets.log_from_preset("u1", preset.preset_id, meal_type="breakfast", date="2026-08-16")
    assert entry.totals.calories == pytest.approx(143)
    assert entry.meal_type == "breakfast"


def test_log_from_preset_raises_when_missing(sqlite_db):
    with pytest.raises(presets.PresetNotFoundError):
        presets.log_from_preset("u1", "missing", meal_type="breakfast", date="2026-08-16")


def test_log_meal_rejects_unpadded_date(sqlite_db):
    """'2026-8-16' would sort outside the DATE# range queries and vanish."""
    _seed_egg(sqlite_db)
    with pytest.raises(meal_logging.InvalidDateError):
        meal_logging.log_meal(
            user_id="u1", meal_type="breakfast",
            item_requests=[{"ingredient_id": "usda#1", "quantity_g": 100}], date="2026-8-16",
        )
    assert summary.list_meals("u1", "2026-01-01", "2026-12-31") == []


@pytest.mark.parametrize("bad_date", ["2026-8-16", "20260816", "16/08/2026", "tomorrow", "2026-13-01", ""])
def test_validate_date_rejects_non_canonical_dates(bad_date):
    with pytest.raises(meal_logging.InvalidDateError):
        meal_logging.validate_date(bad_date)


def test_validate_date_accepts_canonical_date():
    assert meal_logging.validate_date("2026-08-16") == "2026-08-16"


@pytest.mark.parametrize("meal_type", ["breakfast", "lunch", "dinner", "snack"])
def test_validate_meal_type_accepts_allowed_values(meal_type):
    assert meal_logging.validate_meal_type(meal_type) == meal_type


@pytest.mark.parametrize("bad", ["brunch", "Breakfast", "", "supper"])
def test_log_meal_rejects_unknown_meal_type(sqlite_db, bad):
    _seed_egg(sqlite_db)
    with pytest.raises(meal_logging.InvalidMealTypeError):
        meal_logging.log_meal(
            user_id="u1", meal_type=bad,
            item_requests=[{"ingredient_id": "usda#1", "quantity_g": 100}], date="2026-08-16",
        )


def test_valid_meal_still_logs_and_is_visible_in_summary(sqlite_db):
    _seed_egg(sqlite_db)
    meal_logging.log_meal(
        user_id="u1", meal_type="snack",
        item_requests=[{"ingredient_id": "usda#1", "quantity_g": 100}], date="2026-08-16",
    )
    assert len(summary.get_daily_summary("u1", "2026-08-16").entries) == 1


def test_summary_and_list_reject_malformed_dates(sqlite_db):
    with pytest.raises(meal_logging.InvalidDateError):
        summary.get_daily_summary("u1", "2026-8-16")
    with pytest.raises(meal_logging.InvalidDateError):
        summary.list_meals("u1", "2026-08-01", "2026-8-31")


def test_update_and_delete_reject_malformed_dates(sqlite_db):
    with pytest.raises(meal_logging.InvalidDateError):
        meal_logging.update_notes("u1", "2026-8-16", "abc", "note")
    with pytest.raises(meal_logging.InvalidDateError):
        meal_logging.delete_entry("u1", "20260816", "abc")


def test_log_preset_meal_rejects_bad_meal_type(sqlite_db):
    _seed_egg(sqlite_db)
    preset = presets.save_preset("u1", "usual", [{"ingredient_id": "usda#1", "quantity_g": 100}])
    with pytest.raises(meal_logging.InvalidMealTypeError):
        presets.log_from_preset("u1", preset.preset_id, "brunch", "2026-08-16")
