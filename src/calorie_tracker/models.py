from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Macros:
    calories: float
    protein: float
    carbs: float
    fat: float

    def scaled(self, factor: float) -> "Macros":
        return Macros(
            calories=self.calories * factor,
            protein=self.protein * factor,
            carbs=self.carbs * factor,
            fat=self.fat * factor,
        )

    def __add__(self, other: "Macros") -> "Macros":
        return Macros(
            calories=self.calories + other.calories,
            protein=self.protein + other.protein,
            carbs=self.carbs + other.carbs,
            fat=self.fat + other.fat,
        )


ZERO_MACROS = Macros(0.0, 0.0, 0.0, 0.0)

IngredientSource = Literal["usda", "off", "custom", "llm_estimate"]
MealType = Literal["breakfast", "lunch", "dinner", "snack"]


@dataclass
class Ingredient:
    ingredient_id: str
    name: str
    source: IngredientSource
    per_100g: Macros


@dataclass
class MealItem:
    ingredient_id: str
    name: str
    quantity_g: float
    macros: Macros


@dataclass
class MealEntry:
    user_id: str
    entry_id: str
    date: str
    meal_type: MealType
    logged_at: str
    items: list[MealItem]
    notes: str = ""

    @property
    def totals(self) -> Macros:
        total = ZERO_MACROS
        for item in self.items:
            total = total + item.macros
        return total


@dataclass
class UserGoals:
    user_id: str
    daily_calories: float
    daily_protein: float | None = None
    daily_carbs: float | None = None
    daily_fat: float | None = None


@dataclass
class MealPreset:
    user_id: str
    preset_id: str
    name: str
    items: list[MealItem]
