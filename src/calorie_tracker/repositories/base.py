import json
import sqlite3

from calorie_tracker.config import settings
from calorie_tracker.models import Macros, MealItem

# Bumped whenever SCHEMA below changes in a way an existing database cannot
# absorb via plain CREATE TABLE IF NOT EXISTS (which silently no-ops against a
# table that already exists with an older definition). See init_db().
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    daily_calories REAL NOT NULL,
    daily_protein REAL,
    daily_carbs REAL,
    daily_fat REAL
);

CREATE TABLE IF NOT EXISTS ingredients (
    ingredient_id TEXT PRIMARY KEY,
    name TEXT,
    name_normalized TEXT NOT NULL,
    source TEXT,
    alias_for TEXT,
    calories_per_100g REAL,
    protein_per_100g REAL,
    carbs_per_100g REAL,
    fat_per_100g REAL
);
CREATE INDEX IF NOT EXISTS idx_ingredients_name_normalized
    ON ingredients(name_normalized);

CREATE TABLE IF NOT EXISTS meal_entries (
    entry_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    date TEXT NOT NULL,
    meal_type TEXT NOT NULL,
    logged_at TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    items_json TEXT NOT NULL,
    PRIMARY KEY (user_id, entry_id)
);
CREATE INDEX IF NOT EXISTS idx_meal_entries_user_date
    ON meal_entries(user_id, date);

CREATE TABLE IF NOT EXISTS meal_presets (
    preset_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    items_json TEXT NOT NULL,
    PRIMARY KEY (user_id, preset_id)
);
CREATE INDEX IF NOT EXISTS idx_meal_presets_user ON meal_presets(user_id);
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the schema if it isn't there yet, and refuse to start against a
    database whose schema version this code doesn't understand.

    `CREATE TABLE IF NOT EXISTS` does nothing when a table already exists with
    a DIFFERENT (older) definition, so without a version check a stale
    on-disk schema sails through startup and only blows up later, at write
    time, with something cryptic like "ON CONFLICT clause does not match any
    PRIMARY KEY or UNIQUE constraint". The guard makes that a loud startup
    failure instead.

    SQLite reports `user_version = 0` for any database that never set it, which
    covers both a genuinely brand-new file and every database created before
    this check existed. Those two are indistinguishable and both are treated as
    "fine, bring it up to date" -- no production data exists yet. The guard's
    real job is catching drift from this point forward."""
    conn = get_connection()
    try:
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version not in (0, SCHEMA_VERSION):
            raise RuntimeError(
                f"Database schema version mismatch: {settings.database_path} reports "
                f"PRAGMA user_version = {current_version}, but this code expects "
                f"SCHEMA_VERSION = {SCHEMA_VERSION}. Refusing to start rather than "
                "running against a schema it does not understand -- the database was "
                "most likely written by a different (newer or older) version of this app."
            )
        conn.executescript(SCHEMA)
        # PRAGMA doesn't take bound parameters; SCHEMA_VERSION is our own int.
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.commit()
    finally:
        conn.close()


def serialize_items(items: list[MealItem]) -> str:
    return json.dumps(
        [
            {
                "ingredientId": i.ingredient_id,
                "name": i.name,
                "quantityG": i.quantity_g,
                "calories": i.macros.calories,
                "protein": i.macros.protein,
                "carbs": i.macros.carbs,
                "fat": i.macros.fat,
            }
            for i in items
        ]
    )


def deserialize_items(data: str) -> list[MealItem]:
    return [
        MealItem(
            ingredient_id=i["ingredientId"],
            name=i["name"],
            quantity_g=i["quantityG"],
            macros=Macros(
                calories=i["calories"],
                protein=i["protein"],
                carbs=i["carbs"],
                fat=i["fat"],
            ),
        )
        for i in json.loads(data)
    ]
