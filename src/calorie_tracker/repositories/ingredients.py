import re

from calorie_tracker.models import Ingredient, Macros
from calorie_tracker.repositories.base import get_connection


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def get_by_id(ingredient_id: str) -> Ingredient | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM ingredients WHERE ingredient_id = ? AND alias_for IS NULL",
            (ingredient_id,),
        ).fetchone()
    finally:
        conn.close()
    return _to_ingredient(row) if row else None


def find_by_name(name: str) -> Ingredient | None:
    normalized = normalize_name(name)
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM ingredients WHERE name_normalized = ? LIMIT 1",
            (normalized,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    if row["alias_for"] is not None:
        return get_by_id(row["alias_for"])
    return _to_ingredient(row)


def put_alias(query: str, ingredient_id: str) -> None:
    normalized = normalize_name(query)
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO ingredients (ingredient_id, name_normalized, alias_for)
            VALUES (?, ?, ?)
            ON CONFLICT(ingredient_id) DO UPDATE SET alias_for = excluded.alias_for
            """,
            (f"alias#{normalized}", normalized, ingredient_id),
        )
        conn.commit()
    finally:
        conn.close()


def put(ingredient: Ingredient) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO ingredients
                (ingredient_id, name, name_normalized, source,
                 calories_per_100g, protein_per_100g, carbs_per_100g, fat_per_100g)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ingredient_id) DO UPDATE SET
                name = excluded.name,
                name_normalized = excluded.name_normalized,
                source = excluded.source,
                calories_per_100g = excluded.calories_per_100g,
                protein_per_100g = excluded.protein_per_100g,
                carbs_per_100g = excluded.carbs_per_100g,
                fat_per_100g = excluded.fat_per_100g
            """,
            (
                ingredient.ingredient_id,
                ingredient.name,
                normalize_name(ingredient.name),
                ingredient.source,
                ingredient.per_100g.calories,
                ingredient.per_100g.protein,
                ingredient.per_100g.carbs,
                ingredient.per_100g.fat,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _to_ingredient(row) -> Ingredient:
    return Ingredient(
        ingredient_id=row["ingredient_id"],
        name=row["name"],
        source=row["source"],
        per_100g=Macros(
            calories=row["calories_per_100g"],
            protein=row["protein_per_100g"],
            carbs=row["carbs_per_100g"],
            fat=row["fat_per_100g"],
        ),
    )
