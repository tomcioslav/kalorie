import httpx

from calorie_tracker.models import Ingredient, Macros

BASE_URL = "https://search.openfoodfacts.org"


def search(query: str, limit: int = 5) -> list[Ingredient]:
    resp = httpx.get(
        f"{BASE_URL}/search",
        params={"q": query, "page_size": limit, "langs": "en,pl"},
        timeout=10.0,
    )
    resp.raise_for_status()
    results = []
    for hit in resp.json().get("hits", []):
        nutriments = hit.get("nutriments", {})
        if nutriments.get("energy-kcal_100g") is None:
            continue
        code = hit.get("code") or hit.get("_id", "")
        results.append(
            Ingredient(
                ingredient_id=f"off#{code}",
                name=hit.get("product_name", query),
                source="off",
                per_100g=Macros(
                    calories=nutriments.get("energy-kcal_100g", 0.0),
                    protein=nutriments.get("proteins_100g", 0.0),
                    carbs=nutriments.get("carbohydrates_100g", 0.0),
                    fat=nutriments.get("fat_100g", 0.0),
                ),
            )
        )
    return results
