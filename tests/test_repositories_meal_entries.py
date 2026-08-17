from calorie_tracker.models import MealEntry, MealItem, Macros
from calorie_tracker.repositories import meal_entries as entries_repo


def _entry(entry_id: str, date: str) -> MealEntry:
    return MealEntry(
        user_id="u1",
        entry_id=entry_id,
        date=date,
        meal_type="breakfast",
        logged_at=f"{date}T08:00:00+00:00",
        items=[MealItem("usda#1", "egg", 50, Macros(70, 6, 0.5, 5))],
    )


def test_put_then_get_round_trips(sqlite_db):
    entry = _entry("e1", "2026-08-16")
    entries_repo.put(entry)
    assert entries_repo.get("u1", "2026-08-16", "e1") == entry


def test_get_returns_none_when_absent(sqlite_db):
    assert entries_repo.get("u1", "2026-08-16", "missing") is None


def test_delete_removes_entry(sqlite_db):
    entries_repo.put(_entry("e1", "2026-08-16"))
    entries_repo.delete("u1", "2026-08-16", "e1")
    assert entries_repo.get("u1", "2026-08-16", "e1") is None


def test_query_day_returns_only_that_days_entries(sqlite_db):
    entries_repo.put(_entry("e1", "2026-08-16"))
    entries_repo.put(_entry("e2", "2026-08-16"))
    entries_repo.put(_entry("e3", "2026-08-17"))
    day_entries = entries_repo.query_day("u1", "2026-08-16")
    assert {e.entry_id for e in day_entries} == {"e1", "e2"}


def test_query_range_includes_boundaries_and_excludes_outside(sqlite_db):
    entries_repo.put(_entry("e1", "2026-08-14"))
    entries_repo.put(_entry("e2", "2026-08-15"))
    entries_repo.put(_entry("e3", "2026-08-16"))
    entries_repo.put(_entry("e4", "2026-08-17"))
    result = entries_repo.query_range("u1", "2026-08-15", "2026-08-16")
    assert {e.entry_id for e in result} == {"e2", "e3"}


def test_query_scoped_to_user(sqlite_db):
    entries_repo.put(_entry("e1", "2026-08-16"))
    other = MealEntry(
        user_id="u2", entry_id="e2", date="2026-08-16", meal_type="lunch",
        logged_at="2026-08-16T12:00:00+00:00",
        items=[MealItem("usda#1", "egg", 50, Macros(70, 6, 0.5, 5))],
    )
    entries_repo.put(other)
    assert {e.entry_id for e in entries_repo.query_day("u1", "2026-08-16")} == {"e1"}


def test_two_users_can_share_the_same_entry_id_without_clobbering(sqlite_db):
    mine = MealEntry(
        user_id="u1", entry_id="shared-id", date="2026-08-16", meal_type="breakfast",
        logged_at="2026-08-16T08:00:00+00:00",
        items=[MealItem("usda#1", "egg", 50, Macros(70, 6, 0.5, 5))],
    )
    theirs = MealEntry(
        user_id="u2", entry_id="shared-id", date="2026-08-16", meal_type="dinner",
        logged_at="2026-08-16T19:00:00+00:00",
        items=[MealItem("usda#2", "rice", 150, Macros(200, 4, 44, 0.5))],
    )
    entries_repo.put(mine)
    entries_repo.put(theirs)
    assert entries_repo.get("u1", "2026-08-16", "shared-id") == mine
    assert entries_repo.get("u2", "2026-08-16", "shared-id") == theirs
