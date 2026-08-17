from calorie_tracker.models import Macros, ZERO_MACROS, MealEntry, MealItem


def test_macros_scaled():
    m = Macros(calories=200, protein=10, carbs=20, fat=5)
    scaled = m.scaled(0.5)
    assert scaled == Macros(calories=100, protein=5, carbs=10, fat=2.5)


def test_macros_add():
    a = Macros(calories=100, protein=5, carbs=10, fat=2)
    b = Macros(calories=50, protein=2, carbs=5, fat=1)
    assert a + b == Macros(calories=150, protein=7, carbs=15, fat=3)


def test_zero_macros_is_additive_identity():
    m = Macros(calories=10, protein=1, carbs=2, fat=3)
    assert ZERO_MACROS + m == m


def test_meal_entry_totals_sums_items():
    entry = MealEntry(
        user_id="u1",
        entry_id="e1",
        date="2026-08-16",
        meal_type="breakfast",
        logged_at="2026-08-16T08:00:00+00:00",
        items=[
            MealItem("i1", "egg", 50, Macros(70, 6, 0.5, 5)),
            MealItem("i2", "toast", 30, Macros(80, 3, 15, 1)),
        ],
    )
    assert entry.totals == Macros(150, 9, 15.5, 6)
