# tests/test_jwt_auth.py
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from calorie_tracker import config
from calorie_tracker.mcp_app import jwt_auth


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
    jwt_auth._jwks_client = None  # reset the module-level cache between tests


def _issuer() -> str:
    return f"https://cognito-idp.{config.settings.cognito_region}.amazonaws.com/{config.settings.cognito_user_pool_id}"


def _make_token(private_pem, **claim_overrides):
    claims = {
        "sub": "user-abc-123",
        "iss": _issuer(),
        "client_id": "test-client-id",
        "token_use": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        **claim_overrides,
    }
    return pyjwt.encode(claims, private_pem, algorithm="RS256")


def test_verify_access_token_returns_sub_for_valid_token(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    token = _make_token(private_pem)
    assert jwt_auth.verify_access_token(token) == "user-abc-123"


def test_verify_access_token_rejects_expired_token(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    token = _make_token(private_pem, exp=int(time.time()) - 10)
    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(token)


def test_verify_access_token_rejects_wrong_issuer(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    token = _make_token(private_pem, iss="https://cognito-idp.eu-central-1.amazonaws.com/some-other-pool")
    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(token)


def test_verify_access_token_rejects_wrong_client_id(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    token = _make_token(private_pem, client_id="some-other-app")
    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(token)


def test_verify_access_token_rejects_id_token_use(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    token = _make_token(private_pem, token_use="id")
    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(token)


def test_verify_access_token_rejects_tampered_signature(keypair, monkeypatch):
    private_pem, public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(public_pem))
    token = _make_token(private_pem)
    tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(tampered)


def test_verify_access_token_rejects_cleanly_when_cognito_is_unconfigured(keypair, monkeypatch):
    """A freshly deployed instance has cognito_region/cognito_user_pool_id at
    their empty-string defaults until Terraform sets real values. That makes
    _jwks_url() an https URL with an empty hostname label, and urllib's IDNA
    encoding raises UnicodeError("label empty or too long") — which is NOT a
    PyJWTError, so it used to escape verify_access_token entirely as an
    unhandled exception with a baffling message. No fake JWKS client here on
    purpose: the failure under test IS the URL construction."""
    private_pem, _ = keypair
    monkeypatch.setattr(config.settings, "cognito_region", "")
    monkeypatch.setattr(config.settings, "cognito_user_pool_id", "")
    jwt_auth._jwks_client = None
    token = _make_token(private_pem)  # well-formed, so we get past header parsing

    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(token)


def test_verify_access_token_rejects_signature_from_a_different_key(keypair, monkeypatch):
    _, _ = keypair
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private_pem = other_private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Token signed by a key OTHER than the one our JWKS client will return.
    _, real_public_pem = keypair
    monkeypatch.setattr(jwt_auth, "_get_jwks_client", lambda: _FakeJWKSClient(real_public_pem))
    token = _make_token(other_private_pem)
    with pytest.raises(jwt_auth.TokenVerificationError):
        jwt_auth.verify_access_token(token)
