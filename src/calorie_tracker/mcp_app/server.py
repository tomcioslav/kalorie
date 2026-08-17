# src/calorie_tracker/mcp_app/server.py
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from calorie_tracker.mcp_app.context import get_current_user_id
from calorie_tracker.models import Ingredient, MealEntry, MealPreset, UserGoals
from calorie_tracker.repositories import users as users_repo
from calorie_tracker.services import ingredient_resolution, meal_logging, presets, summary

# json_response=True: API Gateway buffers Lambda responses (no SSE streaming),
# so the transport must reply with plain JSON, not an event stream.
#
# transport_security: FastMCP auto-enables DNS-rebinding protection whenever
# `host` is left at its default 127.0.0.1, which restricts the Host header to
# 127.0.0.1/localhost/[::1]. Behind API Gateway the Host header is
# "<api-id>.execute-api.<region>.amazonaws.com", so every real request would be
# rejected with 421 "Invalid Host header". DNS-rebinding protection guards
# browser-reachable localhost servers; this server is only reachable through API
# Gateway, where a Cognito JWT authorizer already gates every request, so we opt
# out explicitly rather than maintaining a Host allowlist per deployed stage.
mcp = FastMCP(
    "calorie-tracker",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _ingredient_dict(i: Ingredient) -> dict:
    return {
        "ingredient_id": i.ingredient_id,
        "name": i.name,
        "source": i.source,
        "calories_per_100g": i.per_100g.calories,
        "protein_per_100g": i.per_100g.protein,
        "carbs_per_100g": i.per_100g.carbs,
        "fat_per_100g": i.per_100g.fat,
    }


def _entry_dict(e: MealEntry) -> dict:
    return {
        "entry_id": e.entry_id,
        "date": e.date,
        "meal_type": e.meal_type,
        "logged_at": e.logged_at,
        "notes": e.notes,
        "items": [
            {"ingredient_id": i.ingredient_id, "name": i.name, "quantity_g": i.quantity_g,
             "calories": i.macros.calories, "protein": i.macros.protein,
             "carbs": i.macros.carbs, "fat": i.macros.fat}
            for i in e.items
        ],
        "totals": {
            "calories": e.totals.calories, "protein": e.totals.protein,
            "carbs": e.totals.carbs, "fat": e.totals.fat,
        },
    }


def _preset_dict(p: MealPreset) -> dict:
    return {
        "preset_id": p.preset_id,
        "name": p.name,
        "items": [
            {"ingredient_id": i.ingredient_id, "name": i.name, "quantity_g": i.quantity_g}
            for i in p.items
        ],
    }


@mcp.tool()
def search_ingredient(query: str) -> list[dict]:
    """Search for a food ingredient by name (English works best for USDA;
    Polish also works via Open Food Facts). Checks the local cache first,
    then USDA FoodData Central, then Open Food Facts. Returns candidates
    with macros per 100g — convert quantities to grams yourself before
    calling log_meal."""
    return [_ingredient_dict(i) for i in ingredient_resolution.resolve(query)]


@mcp.tool()
def create_custom_ingredient(
    name: str, serving_grams: float, calories: float, protein: float, carbs: float, fat: float,
    is_estimate: bool = False,
) -> dict:
    """Register a food search_ingredient couldn't find — a homemade dish, or
    your own best nutritional estimate. Give the macros for the stated
    serving_grams amount; they'll be normalized to per-100g and cached for
    reuse. Set is_estimate=True when these are your estimate rather than a
    known reference, so it gets flagged back to the user."""
    source = "llm_estimate" if is_estimate else "custom"
    ingredient = ingredient_resolution.create_custom(name, serving_grams, calories, protein, carbs, fat, source)
    return _ingredient_dict(ingredient)


@mcp.tool()
def log_meal(meal_type: str, items: list[dict], date: str, notes: str = "") -> dict:
    """Log a meal. items: list of {"ingredient_id": str, "quantity_g": float}
    from search_ingredient/create_custom_ingredient results. date: YYYY-MM-DD."""
    entry = meal_logging.log_meal(get_current_user_id(), meal_type, items, date, notes)
    return _entry_dict(entry)


@mcp.tool()
def update_meal_notes(date: str, entry_id: str, notes: str) -> dict | None:
    """Update the notes on a previously logged meal entry."""
    entry = meal_logging.update_notes(get_current_user_id(), date, entry_id, notes)
    return _entry_dict(entry) if entry else None


@mcp.tool()
def delete_meal_entry(date: str, entry_id: str) -> dict:
    """Delete a previously logged meal entry."""
    meal_logging.delete_entry(get_current_user_id(), date, entry_id)
    return {"deleted": True, "entry_id": entry_id}


@mcp.tool()
def get_daily_summary(date: str) -> dict:
    """Get all meals logged on a date plus totals and remaining calories/macros
    against the user's goals (if set). date: YYYY-MM-DD."""
    s = summary.get_daily_summary(get_current_user_id(), date)
    return {
        "date": s.date,
        "entries": [_entry_dict(e) for e in s.entries],
        "total": {"calories": s.total.calories, "protein": s.total.protein, "carbs": s.total.carbs, "fat": s.total.fat},
        "goals": (
            {"calories": s.goals.daily_calories, "protein": s.goals.daily_protein,
             "carbs": s.goals.daily_carbs, "fat": s.goals.daily_fat}
            if s.goals else None
        ),
        "remaining": {
            "calories": s.remaining_calories, "protein": s.remaining_protein,
            "carbs": s.remaining_carbs, "fat": s.remaining_fat,
        },
    }


@mcp.tool()
def list_meals(start_date: str, end_date: str) -> list[dict]:
    """List all logged meals between start_date and end_date (inclusive, YYYY-MM-DD)."""
    return [_entry_dict(e) for e in summary.list_meals(get_current_user_id(), start_date, end_date)]


@mcp.tool()
def set_daily_goals(calories: float, protein: float | None = None, carbs: float | None = None, fat: float | None = None) -> dict:
    """Set (or replace) the user's daily calorie/macro goals."""
    goals = UserGoals(user_id=get_current_user_id(), daily_calories=calories, daily_protein=protein, daily_carbs=carbs, daily_fat=fat)
    users_repo.set_goals(goals)
    return {"calories": goals.daily_calories, "protein": goals.daily_protein, "carbs": goals.daily_carbs, "fat": goals.daily_fat}


@mcp.tool()
def save_meal_preset(name: str, items: list[dict]) -> dict:
    """Save a reusable named meal (e.g. "usual breakfast") for quick re-logging later."""
    preset = presets.save_preset(get_current_user_id(), name, items)
    return _preset_dict(preset)


@mcp.tool()
def list_meal_presets() -> list[dict]:
    """List this user's saved meal presets."""
    return [_preset_dict(p) for p in presets.list_presets(get_current_user_id())]


@mcp.tool()
def log_preset_meal(preset_id: str, meal_type: str, date: str, notes: str = "") -> dict:
    """Log a meal from a previously saved preset."""
    entry = presets.log_from_preset(get_current_user_id(), preset_id, meal_type, date, notes)
    return _entry_dict(entry)
