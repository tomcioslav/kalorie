from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Environment-derived app config. Reads actual environment variables
    first (how this runs in production — systemd, or Docker), falling back
    to a `.env` file at the repo root for local dev (see `.env.example`) —
    missing `.env` is not an error, it's the normal case in production.

    ALLOW_ANONYMOUS_USER is deliberately NOT here: mcp_app/context.py reads
    it fresh from os.environ on every call rather than once at startup, so
    tests can toggle it per-case with monkeypatch. A cached setting here
    would break that.
    """

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    users_table: str = "calorie-tracker-users"
    ingredients_table: str = "calorie-tracker-ingredients"
    meal_entries_table: str = "calorie-tracker-meal-entries"
    meal_presets_table: str = "calorie-tracker-meal-presets"
    usda_api_key: str = "DEMO_KEY"
    aws_region: str = "eu-central-1"
    # Anchored to the repo root, exactly like `.env` above: a CWD-relative
    # default meant the app crashed at import when the working directory was
    # unwritable (systemd's default WorkingDirectory is `/`), and -- far worse
    # -- silently created a brand-new EMPTY database whenever the process was
    # started from a different directory, which looks precisely like every
    # logged meal vanishing. Override with DATABASE_PATH in real deployments.
    database_path: str = str(_REPO_ROOT / "calorie_tracker.db")
    cognito_region: str = ""
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    # NOT FASTMCP_HOST/FASTMCP_PORT: FastMCP.__init__ always passes explicit
    # host/port kwargs (its own Python-level defaults) into its internal
    # Settings object, and in pydantic-settings, explicit constructor kwargs
    # always beat environment variables — so those env vars are silently
    # ignored. These two are what main.py actually binds uvicorn to.
    uvicorn_host: str = "127.0.0.1"
    uvicorn_port: int = 8000


settings = Settings()
