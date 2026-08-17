from calorie_tracker.models import MealPreset, MealItem, Macros
from calorie_tracker.repositories import meal_presets as presets_repo


def _preset(preset_id: str, name: str, user_id: str = "u1") -> MealPreset:
    return MealPreset(
        user_id=user_id,
        preset_id=preset_id,
        name=name,
        items=[MealItem("usda#1", "egg", 50, Macros(70, 6, 0.5, 5))],
    )


def test_put_then_get_round_trips(sqlite_db):
    preset = _preset("p1", "Usual breakfast")
    presets_repo.put(preset)
    assert presets_repo.get("u1", "p1") == preset


def test_get_returns_none_when_absent(sqlite_db):
    assert presets_repo.get("u1", "missing") is None


def test_list_for_user_returns_only_that_users_presets(sqlite_db):
    presets_repo.put(_preset("p1", "Usual breakfast"))
    presets_repo.put(_preset("p2", "Usual lunch"))
    presets_repo.put(_preset("p3", "Other", user_id="u2"))
    result = presets_repo.list_for_user("u1")
    assert {p.preset_id for p in result} == {"p1", "p2"}


def test_two_users_can_share_the_same_preset_id_without_clobbering(sqlite_db):
    mine = _preset("shared-id", "My breakfast", user_id="u1")
    theirs = _preset("shared-id", "Their lunch", user_id="u2")
    presets_repo.put(mine)
    presets_repo.put(theirs)
    assert presets_repo.get("u1", "shared-id") == mine
    assert presets_repo.get("u2", "shared-id") == theirs
