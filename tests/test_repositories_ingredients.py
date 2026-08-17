from calorie_tracker.models import Ingredient, Macros
from calorie_tracker.repositories import ingredients as ingredients_repo


def test_get_by_id_returns_none_when_absent(sqlite_db):
    assert ingredients_repo.get_by_id("usda#999") is None


def test_put_then_get_by_id_round_trips(sqlite_db):
    ing = Ingredient("usda#123", "Egg, whole, raw", "usda", Macros(143, 12.6, 0.7, 9.5))
    ingredients_repo.put(ing)
    assert ingredients_repo.get_by_id("usda#123") == ing


def test_find_by_name_is_case_and_whitespace_insensitive(sqlite_db):
    ing = Ingredient("usda#123", "  Egg, Whole, RAW  ", "usda", Macros(143, 12.6, 0.7, 9.5))
    ingredients_repo.put(ing)
    found = ingredients_repo.find_by_name("egg, whole, raw")
    assert found is not None
    assert found.ingredient_id == "usda#123"


def test_find_by_name_returns_none_when_no_match(sqlite_db):
    assert ingredients_repo.find_by_name("nonexistent food") is None


def test_put_alias_makes_ingredient_findable_by_query(sqlite_db):
    real = Ingredient("usda#123", "Egg, whole, raw, fresh", "usda", Macros(143, 12.6, 0.7, 9.5))
    ingredients_repo.put(real)
    ingredients_repo.put_alias("egg", "usda#123")

    found = ingredients_repo.find_by_name("egg")
    assert found == real
    # The alias row itself is never returned as a first-class ingredient
    assert ingredients_repo.get_by_id("alias#egg") is None
