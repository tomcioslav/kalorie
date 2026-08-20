# src/calorie_tracker/mcp_app/jwt_auth.py
from jwt import PyJWKClient, decode as jwt_decode

from calorie_tracker.config import settings


class TokenVerificationError(Exception):
    pass


_jwks_client: PyJWKClient | None = None


def _jwks_url() -> str:
    return (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )


def issuer_url() -> str:
    return f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/{settings.cognito_user_pool_id}"


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_jwks_url())
    return _jwks_client


def verify_access_token(token: str) -> str:
    """Returns the verified 'sub' claim. Raises TokenVerificationError on
    any failure — bad signature, expired, wrong issuer/client, wrong token
    type, or a missing/malformed sub claim."""
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        claims = jwt_decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer_url(),
        )
    except Exception as exc:
        # Deliberately broader than PyJWTError. With Cognito unconfigured
        # (cognito_region/cognito_user_pool_id still at their empty defaults,
        # i.e. a fresh deployment before Terraform sets real values),
        # _jwks_url() has an empty hostname label and urllib's IDNA encoding
        # raises UnicodeError("label empty or too long") -- not a PyJWTError,
        # so it used to escape uncaught with a thoroughly misleading message.
        # Anything that goes wrong while establishing the caller's identity is
        # a verification failure. (Exception, not BaseException: KeyboardInterrupt
        # and SystemExit still propagate.)
        raise TokenVerificationError(str(exc) or type(exc).__name__) from exc

    # Cognito access tokens carry `client_id`, not the more common `aud`
    # claim (which ID tokens use instead) — checked explicitly here.
    if claims.get("client_id") != settings.cognito_app_client_id:
        raise TokenVerificationError("token issued for a different client")
    if claims.get("token_use") != "access":
        raise TokenVerificationError("not an access token")

    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise TokenVerificationError("missing sub claim")
    return sub
