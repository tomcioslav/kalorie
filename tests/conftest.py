import pytest

from calorie_tracker import config
from calorie_tracker.mcp_app.context import ALLOW_ANONYMOUS_ENV_VAR
from calorie_tracker.repositories.base import init_db


@pytest.fixture(autouse=True)
def allow_anonymous_user(monkeypatch):
    """Tests run without a real Cognito-issued JWT, so opt in to the
    anonymous user the same way local dev does. Tests that exercise the
    fail-closed path delete this again via monkeypatch."""
    monkeypatch.setenv(ALLOW_ANONYMOUS_ENV_VAR, "1")


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config.settings, "database_path", str(tmp_path / "test.db"))
    init_db()
