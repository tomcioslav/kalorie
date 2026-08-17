from calorie_tracker.models import UserGoals
from calorie_tracker.repositories import users as users_repo


def test_get_goals_returns_none_when_absent(sqlite_db):
    assert users_repo.get_goals("u1") is None


def test_set_then_get_goals_round_trips(sqlite_db):
    goals = UserGoals(user_id="u1", daily_calories=2000, daily_protein=120, daily_carbs=220, daily_fat=70)
    users_repo.set_goals(goals)
    assert users_repo.get_goals("u1") == goals


def test_set_goals_with_only_calories(sqlite_db):
    goals = UserGoals(user_id="u2", daily_calories=1800)
    users_repo.set_goals(goals)
    fetched = users_repo.get_goals("u2")
    assert fetched == goals
    assert fetched.daily_protein is None


def test_set_goals_twice_overwrites_not_duplicates(sqlite_db):
    users_repo.set_goals(UserGoals(user_id="u1", daily_calories=2000))
    users_repo.set_goals(UserGoals(user_id="u1", daily_calories=1800, daily_protein=100))
    fetched = users_repo.get_goals("u1")
    assert fetched.daily_calories == 1800
    assert fetched.daily_protein == 100
