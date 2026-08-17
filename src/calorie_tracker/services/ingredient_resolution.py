import logging
import uuid

from calorie_tracker.models import Ingredient, Macros
from calorie_tracker.nutrition_apis import open_food_facts, usda
from calorie_tracker.repositories import ingredients as ingredients_repo

logger = logging.getLogger(__name__)


def _search_usda(query: str) -> list[Ingredient]:
    """USDA results, or an empty list if USDA is unreachable/rate-limited.

    A USDA failure (network error, timeout, or the 429 the shared DEMO_KEY hits
    quickly) must not take the whole tool down when Open Food Facts could still
    answer, so we degrade to the fallback instead of propagating.
    """
    try:
        return usda.search(query)
    except Exception:
        logger.warning(
            "USDA search failed for %r; falling back to Open Food Facts", query, exc_info=True
        )
        return []


def resolve(query: str) -> list[Ingredient]:
    cached = ingredients_repo.find_by_name(query)
    if cached is not None:
        return [cached]

    results = _search_usda(query)
    if not results:
        results = open_food_facts.search(query)

    for ingredient in results:
        ingredients_repo.put(ingredient)

    # Cache the query string itself, not just the source's name for the food, so
    # the next identical search is served locally instead of hitting the API again.
    if results:
        best = results[0]
        if ingredients_repo.normalize_name(query) != ingredients_repo.normalize_name(best.name):
            ingredients_repo.put_alias(query, best.ingredient_id)
    return results


def create_custom(
    name: str,
    serving_grams: float,
    calories: float,
    protein: float,
    carbs: float,
    fat: float,
    source: str = "custom",
) -> Ingredient:
    if serving_grams <= 0:
        raise ValueError("serving_grams must be positive")
    factor = 100.0 / serving_grams
    per_100g = Macros(calories, protein, carbs, fat).scaled(factor)
    ingredient = Ingredient(
        ingredient_id=f"{source}#{uuid.uuid4().hex[:10]}",
        name=name,
        source=source,
        per_100g=per_100g,
    )
    ingredients_repo.put(ingredient)
    return ingredient
