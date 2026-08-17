import httpx

from calorie_tracker import config
from calorie_tracker.models import Ingredient, Macros

BASE_URL = "https://api.nal.usda.gov/fdc/v1"
NUTRIENT_ID_CALORIES = 1008
NUTRIENT_ID_PROTEIN = 1003
NUTRIENT_ID_CARBS = 1005
NUTRIENT_ID_FAT = 1004


def search(query: str, limit: int = 5) -> list[Ingredient]:
    resp = httpx.get(
        f"{BASE_URL}/foods/search",
        params={
            "api_key": config.settings.usda_api_key,
            "query": query,
            "dataType": "Foundation,SR Legacy",
            "pageSize": limit,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    results = []
    for food in resp.json().get("foods", []):
        macros = _extract_macros(food.get("foodNutrients", []))
        if macros is None:
            continue
        results.append(
            Ingredient(
                ingredient_id=f"usda#{food['fdcId']}",
                name=food.get("description", query),
                source="usda",
                per_100g=macros,
            )
        )
    return results


def _extract_macros(nutrients: list[dict]) -> Macros | None:
    values = {n["nutrientId"]: n.get("value", 0.0) for n in nutrients if "nutrientId" in n and n.get("value") is not None}
    if NUTRIENT_ID_CALORIES not in values:
        return None
    return Macros(
        calories=values.get(NUTRIENT_ID_CALORIES, 0.0),
        protein=values.get(NUTRIENT_ID_PROTEIN, 0.0),
        carbs=values.get(NUTRIENT_ID_CARBS, 0.0),
        fat=values.get(NUTRIENT_ID_FAT, 0.0),
    )
