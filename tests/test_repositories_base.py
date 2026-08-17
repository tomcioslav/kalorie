import sqlite3

import pytest

from calorie_tracker import config
from calorie_tracker.models import Macros, MealItem
from calorie_tracker.repositories.base import (
    SCHEMA_VERSION,
    deserialize_items,
    get_connection,
    init_db,
    serialize_items,
)


def test_init_db_creates_all_four_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database_path", str(tmp_path / "t.db"))
    init_db()
    conn = get_connection()
    try:
        names = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()
    assert {"users", "ingredients", "meal_entries", "meal_presets"} <= names


def test_init_db_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database_path", str(tmp_path / "t.db"))
    init_db()
    init_db()  # must not raise


def test_init_db_stamps_the_schema_version_on_a_fresh_file(tmp_path, monkeypatch):
    """A genuinely new file reports user_version 0; init_db() must accept it
    and stamp it, so later runs can tell a known schema from a drifted one."""
    db_path = tmp_path / "t.db"
    monkeypatch.setattr(config.settings, "database_path", str(db_path))
    init_db()

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()


def test_init_db_is_idempotent_against_an_already_stamped_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database_path", str(tmp_path / "t.db"))
    init_db()
    init_db()  # version already == SCHEMA_VERSION: still a no-op, still no raise

    conn = sqlite3.connect(tmp_path / "t.db")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    finally:
        conn.close()


def test_init_db_refuses_a_database_with_an_unknown_schema_version(tmp_path, monkeypatch):
    """Without this guard, CREATE TABLE IF NOT EXISTS silently no-ops against
    an out-of-date table definition and the mismatch only surfaces much later,
    at write time, as "ON CONFLICT clause does not match any PRIMARY KEY or
    UNIQUE constraint". Fail loudly at startup instead."""
    db_path = tmp_path / "future.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA user_version = 99")
        conn.commit()
    finally:
        conn.close()
    monkeypatch.setattr(config.settings, "database_path", str(db_path))

    with pytest.raises(RuntimeError) as excinfo:
        init_db()

    message = str(excinfo.value)
    assert "99" in message
    assert str(SCHEMA_VERSION) in message
    assert "version" in message.lower()


def test_serialize_deserialize_items_round_trips():
    items = [
        MealItem("usda#1", "egg", 50.0, Macros(70, 6, 0.5, 5)),
        MealItem("usda#2", "toast", 30.0, Macros(80, 3, 15, 1)),
    ]
    assert deserialize_items(serialize_items(items)) == items


def test_get_connection_uses_row_factory(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database_path", str(tmp_path / "t.db"))
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (user_id, daily_calories) VALUES ('u1', 2000)"
        )
        row = conn.execute("SELECT * FROM users WHERE user_id = 'u1'").fetchone()
        assert row["user_id"] == "u1"
        assert row["daily_calories"] == 2000
    finally:
        conn.close()
