import json
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from calorie_tracker import config
from calorie_tracker.mcp_app import context, jwt_auth
from calorie_tracker.mcp_app.context import (
    ALLOW_ANONYMOUS_ENV_VAR,
    MissingUserIdentityError,
    UserContextMiddleware,
    current_user_id,
    get_current_user_id,
)
from calorie_tracker.mcp_app.jwt_auth import TokenVerificationError


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


def _make_token(private_pem, sub="user-abc-123", **overrides):
    claims = {
        "sub": sub, "iss": _issuer(), "client_id": "test-client-id",
        "token_use": "access", "iat": int(time.time()), "exp": int(time.time()) + 3600,
        **overrides,
    }
    return pyjwt.encode(claims, private_pem, algorithm="RS256")


def _scope_with_bearer(token: str | None) -> dict:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return {"type": "http", "headers": headers}


def _recording_send():
    """An ASGI `send` that just records what the middleware emits, so the
    rejection tests can inspect the actual response messages. The middleware
    no longer raises on an unidentifiable request — it answers it with a 401
    itself — so there is nothing for pytest.raises to catch any more."""
    messages: list[dict] = []

    async def send(message):
        messages.append(message)

    return messages, send


def _assert_401_challenge(messages: list[dict]) -> None:
    assert [m["type"] for m in messages] == ["http.response.start", "http.response.body"]
    start, body = messages
    assert start["status"] == 401
    headers = {name.decode().lower(): value.decode() for name, value in start["headers"]}
    assert headers["www-authenticate"].startswith('Bearer error="invalid_token"')
    assert "error_description=" in headers["www-authenticate"]
    assert headers["content-type"] == "application/json"
    assert json.loads(body["body"])["error"] == "invalid_token"


async def test_middleware_sets_user_id_from_valid_token(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    captured = {}

    async def inner_app(scope, receive, send):
        captured["user_id"] = get_current_user_id()

    middleware = UserContextMiddleware(inner_app)
    await middleware(_scope_with_bearer(_make_token(private_pem)), None, None)
    assert captured["user_id"] == "user-abc-123"


async def test_middleware_defaults_when_no_token_and_anonymous_allowed(monkeypatch):
    monkeypatch.setenv(ALLOW_ANONYMOUS_ENV_VAR, "1")
    captured = {}

    async def inner_app(scope, receive, send):
        captured["user_id"] = get_current_user_id()

    middleware = UserContextMiddleware(inner_app)
    await middleware(_scope_with_bearer(None), None, None)
    assert captured["user_id"] == "local-dev-user"


async def test_middleware_rejects_missing_token_when_anonymous_not_allowed(monkeypatch):
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)
    called = []

    async def inner_app(scope, receive, send):
        called.append(True)

    middleware = UserContextMiddleware(inner_app)
    messages, send = _recording_send()
    await middleware(_scope_with_bearer(None), None, send)

    _assert_401_challenge(messages)
    assert called == [], "request must not reach the tools without an identity"


async def test_middleware_rejects_invalid_token_even_when_anonymous_allowed(keypair, monkeypatch):
    """Deliberate strengthening over the old Lambda-era behavior: the old
    middleware only ever saw claims API Gateway had ALREADY signature-checked,
    so a malformed sub claim there just meant an odd-shaped-but-pre-validated
    claims dict, and fell back to anonymous when allowed. Now our own code
    does the signature check, so an invalid token can mean genuinely
    forged/tampered/expired -- that must always fail regardless of
    ALLOW_ANONYMOUS_USER, which exists for the no-token-presented case, not
    the bad-token-presented case."""
    monkeypatch.setenv(ALLOW_ANONYMOUS_ENV_VAR, "1")
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))

    async def inner_app(scope, receive, send):  # pragma: no cover - must not run
        raise AssertionError("inner app should not be reached")

    middleware = UserContextMiddleware(inner_app)
    expired = _make_token(private_pem, exp=int(time.time()) - 10)
    messages, send = _recording_send()
    await middleware(_scope_with_bearer(expired), None, send)

    _assert_401_challenge(messages)


def test_get_current_user_id_fails_closed_without_context(monkeypatch):
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)
    token = current_user_id.set(None)
    try:
        with pytest.raises(MissingUserIdentityError):
            get_current_user_id()
    finally:
        current_user_id.reset(token)


def test_get_current_user_id_returns_dev_user_when_flag_set(monkeypatch):
    monkeypatch.setenv(ALLOW_ANONYMOUS_ENV_VAR, "1")
    token = current_user_id.set(None)
    try:
        assert get_current_user_id() == "local-dev-user"
    finally:
        current_user_id.reset(token)


async def test_401_challenge_header_survives_a_hostile_error_message(monkeypatch):
    """The error_description lands inside a WWW-Authenticate quoted-string,
    and its text comes from PyJWT/urllib, not from us — embedded quotes or
    newlines would produce a malformed (or header-splitting) response."""
    monkeypatch.delenv(ALLOW_ANONYMOUS_ENV_VAR, raising=False)

    def _boom(token):
        raise TokenVerificationError('bad "quoted" key\r\nX-Injected: yes — ünicode')

    monkeypatch.setattr(context, "verify_access_token", _boom)

    async def inner_app(scope, receive, send):  # pragma: no cover - must not run
        raise AssertionError("inner app should not be reached")

    messages, send = _recording_send()
    await UserContextMiddleware(inner_app)(_scope_with_bearer("whatever"), None, send)

    _assert_401_challenge(messages)
    header = dict(messages[0]["headers"])[b"www-authenticate"].decode()
    assert "\r" not in header and "\n" not in header
    assert header.count('"') == 4, header  # exactly the two quoted values
    header.encode("ascii")  # must be byte-safe as a header value


async def test_middleware_passes_through_non_http_scopes_unchanged():
    calls = []

    async def inner_app(scope, receive, send):
        calls.append(scope["type"])

    middleware = UserContextMiddleware(inner_app)
    await middleware({"type": "lifespan"}, None, None)
    assert calls == ["lifespan"]
