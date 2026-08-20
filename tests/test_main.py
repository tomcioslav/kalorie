import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient

from calorie_tracker import config
from calorie_tracker.mcp_app import jwt_auth
from calorie_tracker.mcp_app.context import ALLOW_ANONYMOUS_ENV_VAR
from calorie_tracker.mcp_app.main import app
from calorie_tracker.models import Ingredient, Macros
from calorie_tracker.repositories import ingredients as ingredients_repo
from calorie_tracker.repositories import meal_entries as entries_repo

MCP_HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


@pytest.fixture
def keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_pem):
        self._public_pem = public_pem

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_pem)


@pytest.fixture(autouse=True)
def cognito_settings(monkeypatch):
    monkeypatch.setattr(config.settings, "cognito_region", "eu-central-1")
    monkeypatch.setattr(config.settings, "cognito_user_pool_id", "eu-central-1_TestPool")
    monkeypatch.setattr(config.settings, "cognito_app_client_id", "test-client-id")
    jwt_auth._jwks_client = None


def _issuer() -> str:
    return f"https://cognito-idp.{config.settings.cognito_region}.amazonaws.com/{config.settings.cognito_user_pool_id}"


def _token(private_pem, sub="cognito-sub-abc", **overrides) -> str:
    claims = {
        "sub": sub, "iss": _issuer(), "client_id": "test-client-id",
        "token_use": "access", "iat": int(time.time()), "exp": int(time.time()) + 3600,
        **overrides,
    }
    return pyjwt.encode(claims, private_pem, algorithm="RS256")


def rpc(client: TestClient, payload: dict, token: str | None = None) -> dict:
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.post("/mcp", json=payload, headers=headers)
    return response


TOOLS_LIST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}


@pytest.fixture(scope="module")
def client():
    """`app` (imported from `calorie_tracker.mcp_app.main`) is a
    module-level singleton, and its embedded MCP `StreamableHTTPSessionManager`
    forbids entering its ASGI lifespan (`.run()`) more than once for the life
    of that object — by design, matching production, where uvicorn enters the
    lifespan exactly once and holds it open for the life of the process (see
    main.py's docstring). Discovered empirically: the brief's literal
    per-test `with TestClient(app) as client:` blocks each independently
    start/stop the lifespan, and the second such block anywhere in the same
    pytest process hits `RuntimeError: StreamableHTTPSessionManager .run()
    can only be called once per instance.` This fixture instead opens the
    lifespan exactly once, module-wide, and every test that needs a live
    session shares the resulting client — which is a closer match to the
    real deployment (one lifespan, many requests) than one lifespan per test
    would have been anyway."""
    with TestClient(app) as c:
        yield c


def test_tools_list_returns_all_eleven_tools(client):
    response = rpc(client, TOOLS_LIST)
    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    names = sorted(t["name"] for t in tools)
    assert names == sorted(
        [
            "search_ingredient", "create_custom_ingredient", "log_meal",
            "update_meal_notes", "delete_meal_entry", "get_daily_summary",
            "list_meals", "set_daily_goals", "save_meal_preset",
            "list_meal_presets", "log_preset_meal",
        ]
    )


def test_three_sequential_requests_all_succeed(client):
    """A plain persistent process has never had Lambda's warm-invocation
    lifespan-replay problem, but this locks that in as a regression test."""
    for i in range(1, 4):
        response = rpc(client, {"jsonrpc": "2.0", "id": i, "method": "tools/list"})
        assert response.status_code == 200
        assert len(response.json()["result"]["tools"]) == 11


def test_tool_call_writes_under_the_verified_sub(client, sqlite_db, keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))

    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    token = _token(private_pem, sub="cognito-sub-abc")

    response = rpc(
        client,
        {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {
                "name": "log_meal",
                "arguments": {
                    "meal_type": "breakfast",
                    "items": [{"ingredient_id": "usda#1", "quantity_g": 100}],
                    "date": "2026-08-16",
                },
            },
        },
        token=token,
    )
    assert response.status_code == 200
    body = response.json()["result"]
    assert body["isError"] is False, body

    stored = entries_repo.query_day("cognito-sub-abc", "2026-08-16")
    assert len(stored) == 1
    assert entries_repo.query_day("local-dev-user", "2026-08-16") == []


def test_two_users_stay_separated(client, sqlite_db, keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))

    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    call = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {
            "name": "log_meal",
            "arguments": {
                "meal_type": "lunch",
                "items": [{"ingredient_id": "usda#1", "quantity_g": 100}],
                "date": "2026-08-16",
            },
        },
    }
    rpc(client, call, token=_token(private_pem, sub="user-a"))
    rpc(client, call, token=_token(private_pem, sub="user-b"))

    assert len(entries_repo.query_day("user-a", "2026-08-16")) == 1
    assert len(entries_repo.query_day("user-b", "2026-08-16")) == 1


LOG_MEAL_CALL = {
    "jsonrpc": "2.0", "id": 4, "method": "tools/call",
    "params": {
        "name": "log_meal",
        "arguments": {
            "meal_type": "dinner",
            "items": [{"ingredient_id": "usda#1", "quantity_g": 100}],
            "date": "2026-08-16",
        },
    },
}


def test_request_without_token_fails_closed(monkeypatch, sqlite_db):
    """Deliberately does NOT enter `with TestClient(...) as client:` —
    `UserContextMiddleware` answers a tokenless request with a 401 itself,
    before ever delegating to the inner MCP app, so this codepath never
    touches the session-managed app and never needs its lifespan running;
    entering it here would hit the same "run() called twice" guard the
    `client` fixture above works around. `raise_server_exceptions` is left at
    its default True on purpose: nothing should escape the middleware as an
    exception any more, so a regression surfaces as a loud traceback rather
    than quietly becoming a 500 response."""
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))

    response = rpc(TestClient(app), LOG_MEAL_CALL)

    # 401, not 500: `mcp/client/auth/oauth2.py` only refreshes an expired
    # token when it sees a 401, so a 500 here leaves a real MCP client wedged
    # until a human intervenes.
    assert response.status_code == 401
    assert "www-authenticate" in response.headers
    assert response.headers["www-authenticate"].startswith("Bearer ")
    assert entries_repo.query_day("local-dev-user", "2026-08-16") == []


@pytest.mark.parametrize("bad_token", ["expired", "wrong_issuer", "garbage"])
def test_request_with_invalid_token_returns_401(
    monkeypatch, sqlite_db, keypair, bad_token
):
    """The expiry case is the one that actually happens in production, roughly
    hourly: Cognito access tokens are short-lived, and the client's recovery
    path is keyed entirely off the 401 status code."""
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))

    tokens = {
        "expired": lambda: _token(private_pem, exp=int(time.time()) - 10),
        "wrong_issuer": lambda: _token(
            private_pem, iss="https://cognito-idp.eu-central-1.amazonaws.com/other-pool"
        ),
        "garbage": lambda: "not-even-a-jwt",
    }
    response = rpc(TestClient(app), LOG_MEAL_CALL, token=tokens[bad_token]())

    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith('Bearer error="invalid_token"')
    assert response.json()["error"] == "invalid_token"
    assert entries_repo.query_day("local-dev-user", "2026-08-16") == []


def test_invalid_token_returns_401_even_when_anonymous_is_allowed(
    monkeypatch, sqlite_db, keypair
):
    """ALLOW_ANONYMOUS_USER covers "no token presented", never "this token is
    bad" — and the rejection still has to be a 401, not a 500."""
    monkeypatch.setenv(ALLOW_ANONYMOUS_ENV_VAR, "1")
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))

    expired = _token(private_pem, exp=int(time.time()) - 10)
    response = rpc(TestClient(app), LOG_MEAL_CALL, token=expired)

    assert response.status_code == 401
    assert "www-authenticate" in response.headers
    assert entries_repo.query_day("local-dev-user", "2026-08-16") == []


def test_invalid_date_is_a_tool_error_not_a_silent_write(client, sqlite_db, keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))

    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))
    token = _token(private_pem, sub="cognito-sub-abc")

    response = rpc(
        client,
        {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {
                "name": "log_meal",
                "arguments": {
                    "meal_type": "breakfast",
                    "items": [{"ingredient_id": "usda#1", "quantity_g": 100}],
                    "date": "2026-8-16",
                },
            },
        },
        token=token,
    )
    body = response.json()["result"]
    assert body["isError"] is True
    assert entries_repo.query_day("cognito-sub-abc", "2026-8-16") == []


def test_well_known_endpoint_returns_metadata_without_any_token(client, monkeypatch):
    # Prove the endpoint is reachable with no token AND with anonymous access
    # turned off -- otherwise this test would pass even if the discovery
    # router were (incorrectly) nested inside the auth middleware, since the
    # rest of this file's autouse fixtures leave ALLOW_ANONYMOUS_USER set,
    # which would let a tokenless request through either way.
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)
    response = client.get("/.well-known/oauth-protected-resource")
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == config.settings.public_mcp_url
    assert body["authorization_servers"] == [
        f"https://cognito-idp.{config.settings.cognito_region}.amazonaws.com/{config.settings.cognito_user_pool_id}"
    ]


def test_401_response_includes_resource_metadata_pointer(monkeypatch, sqlite_db):
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)
    ingredients_repo.put(Ingredient("usda#1", "egg", "usda", Macros(143, 12.6, 0.7, 9.5)))

    response = rpc(TestClient(app), LOG_MEAL_CALL)

    assert response.status_code == 401
    www_auth = response.headers["www-authenticate"]
    assert 'resource_metadata="' in www_auth
    from calorie_tracker.mcp_app import oauth_discovery
    assert oauth_discovery.metadata_url() in www_auth
