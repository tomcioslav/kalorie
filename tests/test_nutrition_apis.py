import re

from calorie_tracker.nutrition_apis import usda, open_food_facts


def test_usda_search_parses_matching_nutrients(httpx_mock):
    httpx_mock.add_response(
        url=re.compile("https://api.nal.usda.gov/fdc/v1/foods/search.*"),
        json={
            "foods": [
                {
                    "fdcId": 173424,
                    "description": "Egg, whole, raw, fresh",
                    "foodNutrients": [
                        {"nutrientId": 1008, "value": 143.0},
                        {"nutrientId": 1003, "value": 12.6},
                        {"nutrientId": 1005, "value": 0.72},
                        {"nutrientId": 1004, "value": 9.51},
                        {"nutrientId": 1093, "value": 142.0},
                    ],
                }
            ]
        },
    )
    results = usda.search("egg")
    assert len(results) == 1
    r = results[0]
    assert r.ingredient_id == "usda#173424"
    assert r.source == "usda"
    assert r.per_100g.calories == 143.0
    assert r.per_100g.protein == 12.6
    assert r.per_100g.carbs == 0.72
    assert r.per_100g.fat == 9.51


def test_usda_search_skips_foods_with_no_energy_value(httpx_mock):
    httpx_mock.add_response(
        url=re.compile("https://api.nal.usda.gov/fdc/v1/foods/search.*"),
        json={"foods": [{"fdcId": 1, "description": "Water", "foodNutrients": []}]},
    )
    assert usda.search("water") == []


def test_off_search_parses_matching_nutriments(httpx_mock):
    httpx_mock.add_response(
        url=re.compile("https://search.openfoodfacts.org/search.*"),
        json={
            "hits": [
                {
                    "code": "5000112548167",
                    "product_name": "Cheddar cheese",
                    "nutriments": {
                        "energy-kcal_100g": 404,
                        "proteins_100g": 25.0,
                        "carbohydrates_100g": 0.1,
                        "fat_100g": 34.0,
                    },
                }
            ]
        },
    )
    results = open_food_facts.search("cheddar cheese")
    assert len(results) == 1
    r = results[0]
    assert r.ingredient_id == "off#5000112548167"
    assert r.source == "off"
    assert r.per_100g.calories == 404
    assert r.per_100g.fat == 34.0


def test_off_search_skips_hits_without_calories(httpx_mock):
    httpx_mock.add_response(
        url=re.compile("https://search.openfoodfacts.org/search.*"),
        json={"hits": [{"code": "1", "product_name": "Mystery item", "nutriments": {}}]},
    )
    assert open_food_facts.search("mystery") == []


def test_usda_search_skips_foods_with_null_energy_value(httpx_mock):
    httpx_mock.add_response(
        url=re.compile("https://api.nal.usda.gov/fdc/v1/foods/search.*"),
        json={
            "foods": [
                {
                    "fdcId": 999,
                    "description": "Unknown food",
                    "foodNutrients": [{"nutrientId": 1008, "value": None}],
                }
            ]
        },
    )
    assert usda.search("unknown") == []


def test_off_search_skips_hits_with_null_calories(httpx_mock):
    httpx_mock.add_response(
        url=re.compile("https://search.openfoodfacts.org/search.*"),
        json={
            "hits": [
                {
                    "code": "999",
                    "product_name": "Invalid product",
                    "nutriments": {"energy-kcal_100g": None},
                }
            ]
        },
    )
    assert open_food_facts.search("invalid") == []
