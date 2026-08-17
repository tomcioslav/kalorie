import logging
from unittest.mock import patch

import httpx
import pytest

from calorie_tracker.models import Ingredient, Macros
from calorie_tracker.services import ingredient_resolution


def test_resolve_returns_cached_ingredient_without_calling_apis():
    cached = Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5))
    with (
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.find_by_name", return_value=cached),
        patch("calorie_tracker.services.ingredient_resolution.usda.search") as usda_search,
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search") as off_search,
    ):
        result = ingredient_resolution.resolve("egg")
    assert result == [cached]
    usda_search.assert_not_called()
    off_search.assert_not_called()


def test_resolve_falls_back_to_usda_and_caches_results():
    found = Ingredient("usda#2", "chicken breast", "usda", Macros(165, 31, 0, 3.6))
    with (
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.find_by_name", return_value=None),
        patch("calorie_tracker.services.ingredient_resolution.usda.search", return_value=[found]),
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search") as off_search,
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put") as put_mock,
    ):
        result = ingredient_resolution.resolve("chicken breast")
    assert result == [found]
    off_search.assert_not_called()
    put_mock.assert_called_once_with(found)


def test_resolve_falls_back_to_off_when_usda_has_nothing():
    found = Ingredient("off#3", "obscure branded snack", "off", Macros(500, 5, 60, 25))
    with (
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.find_by_name", return_value=None),
        patch("calorie_tracker.services.ingredient_resolution.usda.search", return_value=[]),
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search", return_value=[found]),
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put") as put_mock,
    ):
        result = ingredient_resolution.resolve("obscure branded snack")
    assert result == [found]
    put_mock.assert_called_once_with(found)


def test_create_custom_normalizes_to_per_100g():
    with patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put") as put_mock:
        ingredient = ingredient_resolution.create_custom(
            name="Homemade pasta bowl", serving_grams=350, calories=550, protein=20, carbs=70, fat=18
        )
    assert ingredient.source == "custom"
    assert ingredient.per_100g.calories == pytest.approx(157.142857, rel=1e-4)
    assert ingredient.per_100g.protein == pytest.approx(5.714286, rel=1e-4)
    put_mock.assert_called_once_with(ingredient)


def test_create_custom_rejects_non_positive_serving():
    with pytest.raises(ValueError):
        ingredient_resolution.create_custom("x", 0, 100, 1, 1, 1)


def test_create_custom_tags_llm_estimate_source():
    with patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put"):
        ingredient = ingredient_resolution.create_custom(
            "Guessed dish", 200, 300, 10, 30, 10, source="llm_estimate"
        )
    assert ingredient.source == "llm_estimate"


def test_resolve_falls_back_to_off_when_usda_raises():
    """A USDA outage / DEMO_KEY rate limit must not disable ingredient search."""
    found = Ingredient("off#9", "kefir", "off", Macros(60, 3.3, 4.5, 3.2))
    with (
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.find_by_name", return_value=None),
        patch(
            "calorie_tracker.services.ingredient_resolution.usda.search",
            side_effect=httpx.HTTPStatusError("429 Too Many Requests", request=None, response=None),
        ),
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search", return_value=[found]),
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put") as put_mock,
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put_alias"),
    ):
        result = ingredient_resolution.resolve("kefir")
    assert result == [found]
    put_mock.assert_called_once_with(found)


def test_resolve_logs_when_usda_fails(caplog):
    found = Ingredient("off#9", "kefir", "off", Macros(60, 3.3, 4.5, 3.2))
    with (
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.find_by_name", return_value=None),
        patch(
            "calorie_tracker.services.ingredient_resolution.usda.search",
            side_effect=httpx.ConnectTimeout("timed out"),
        ),
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search", return_value=[found]),
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put"),
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put_alias"),
        caplog.at_level(logging.WARNING),
    ):
        ingredient_resolution.resolve("kefir")
    assert "USDA search failed" in caplog.text


def test_resolve_propagates_when_both_sources_fail():
    """A total outage still surfaces as an error rather than an empty result."""
    with (
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.find_by_name", return_value=None),
        patch("calorie_tracker.services.ingredient_resolution.usda.search", side_effect=httpx.ConnectTimeout("x")),
        patch(
            "calorie_tracker.services.ingredient_resolution.open_food_facts.search",
            side_effect=httpx.ConnectTimeout("x"),
        ),
    ):
        with pytest.raises(httpx.ConnectTimeout):
            ingredient_resolution.resolve("kefir")


def test_second_resolve_of_same_query_hits_cache_and_skips_apis(sqlite_db):
    """The query string, not just the source's name for the food, is cached."""
    found = Ingredient("usda#123", "Egg, whole, raw, fresh", "usda", Macros(143, 12.6, 0.7, 9.5))
    with (
        patch("calorie_tracker.services.ingredient_resolution.usda.search", return_value=[found]) as usda_search,
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search") as off_search,
    ):
        first = ingredient_resolution.resolve("egg")
        assert first == [found]
        assert usda_search.call_count == 1

        second = ingredient_resolution.resolve("egg")

    assert second == [found]
    assert second[0].ingredient_id == "usda#123"
    usda_search.assert_called_once()
    off_search.assert_not_called()


def test_resolve_cache_hit_is_case_insensitive_on_the_query(sqlite_db):
    found = Ingredient("off#77", "Skyr Naturalny 0%", "off", Macros(60, 11, 4, 0.2))
    with (
        patch("calorie_tracker.services.ingredient_resolution.usda.search", return_value=[]),
        patch("calorie_tracker.services.ingredient_resolution.open_food_facts.search", return_value=[found]) as off,
    ):
        ingredient_resolution.resolve("  SKYR  naturalny ")
        again = ingredient_resolution.resolve("skyr naturalny")
    assert again == [found]
    off.assert_called_once()


def test_resolve_does_not_write_alias_when_query_matches_the_name(sqlite_db):
    found = Ingredient("usda#5", "kefir", "usda", Macros(60, 3.3, 4.5, 3.2))
    with (
        patch("calorie_tracker.services.ingredient_resolution.usda.search", return_value=[found]),
        patch("calorie_tracker.services.ingredient_resolution.ingredients_repo.put_alias") as alias_mock,
    ):
        ingredient_resolution.resolve("Kefir")
    alias_mock.assert_not_called()
