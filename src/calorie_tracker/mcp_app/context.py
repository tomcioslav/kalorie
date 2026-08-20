# src/calorie_tracker/mcp_app/context.py
import json
import os
from contextvars import ContextVar

from calorie_tracker.mcp_app import oauth_discovery
from calorie_tracker.mcp_app.jwt_auth import TokenVerificationError, verify_access_token

ANONYMOUS_USER_ID = "local-dev-user"
ALLOW_ANONYMOUS_ENV_VAR = "ALLOW_ANONYMOUS_USER"
_TRUTHY = {"1", "true", "yes", "on"}

# No default: an unset value means "we do not know who is calling", which must
# fail closed rather than silently resolving to a shared bucket of data.
current_user_id: ContextVar[str | None] = ContextVar("current_user_id", default=None)


class MissingUserIdentityError(RuntimeError):
    """Raised when a request carries no usable caller identity.

    This app holds two people's personal health data, so an unidentified or
    unverifiable request must be rejected rather than being folded into one
    shared pseudo-user. Set ALLOW_ANONYMOUS_USER=1 for local dev/tests to opt
    in to the anonymous fallback instead.
    """


def anonymous_user_allowed() -> bool:
    """True only when ALLOW_ANONYMOUS_USER is explicitly set to a truthy value."""
    return os.environ.get(ALLOW_ANONYMOUS_ENV_VAR, "").strip().lower() in _TRUTHY


def get_current_user_id() -> str:
    """The caller's verified Cognito 'sub', or the local-dev fallback if
    explicitly enabled."""
    user_id = current_user_id.get()
    if user_id:
        return user_id
    if anonymous_user_allowed():
        return ANONYMOUS_USER_ID
    raise MissingUserIdentityError(
        "No authenticated user on this request. Expected a verified Cognito "
        f"access token; set {ALLOW_ANONYMOUS_ENV_VAR}=1 to allow the "
        "anonymous local-dev user instead."
    )


def _extract_bearer_token(scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            text = value.decode("latin-1")
            if text.lower().startswith("bearer "):
                return text[7:].strip()
    return None


def _header_safe(text: str) -> str:
    """Flatten a message into something legal inside a WWW-Authenticate
    quoted-string: no embedded quotes/backslashes, no newlines, ASCII only
    (header values are byte strings, and PyJWT's messages are not guaranteed
    to be header-clean)."""
    collapsed = " ".join(text.split())
    unquoted = collapsed.replace("\\", " ").replace('"', "'")
    return unquoted.encode("ascii", "replace").decode("ascii")


async def _send_auth_error(send, description: str, resource_metadata_url: str) -> None:
    """Send a 401 with a WWW-Authenticate challenge, straight to the ASGI
    `send` callable.

    Shape follows the MCP SDK's own RequireAuthMiddleware._send_auth_error
    (mcp/server/auth/middleware/bearer_auth.py) because that is what MCP
    clients are written against: `mcp/client/auth/oauth2.py` only attempts a
    token refresh / re-auth when it sees status 401, and
    `mcp/client/auth/utils.py`'s extract_resource_metadata_from_www_auth
    bails out on anything else. Letting MissingUserIdentityError escape as an
    unhandled ASGI exception produced a 500 instead, which got none of that
    handling -- so an ordinary hourly token expiry left the connector wedged
    until a human intervened.

    `resource_metadata` is equally required, not decorative: per
    https://claude.com/docs/connectors/building/authentication, Claude will
    not even attempt the OAuth flow without it -- it's how Claude discovers
    which authorization server (Cognito) to send the user to."""
    www_authenticate = (
        f'Bearer error="invalid_token", error_description="{_header_safe(description)}", '
        f'resource_metadata="{_header_safe(resource_metadata_url)}"'
    )
    body_bytes = json.dumps(
        {"error": "invalid_token", "error_description": description}
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body_bytes)).encode()),
                (b"www-authenticate", www_authenticate.encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body_bytes})


class UserContextMiddleware:
    """Verifies the request's bearer JWT against Cognito's public keys and
    exposes the resulting user id to MCP tools via current_user_id.

    A present-but-invalid token (bad signature, expired, wrong pool/client)
    is always rejected, regardless of ALLOW_ANONYMOUS_USER — that flag only
    covers the "no token at all" case for local dev, not "something is
    actively wrong with this token."""

    def __init__(self, app):
        self.app = app

    def _resolve_user_id(self, scope) -> str:
        """Who is calling? Raises MissingUserIdentityError when that cannot be
        established -- __call__ turns that into a 401 response."""
        token = _extract_bearer_token(scope)
        if token is None:
            if not anonymous_user_allowed():
                raise MissingUserIdentityError(
                    "Request has no bearer token; refusing to serve it as the "
                    f"shared anonymous user. Set {ALLOW_ANONYMOUS_ENV_VAR}=1 for local dev."
                )
            return ANONYMOUS_USER_ID
        try:
            return verify_access_token(token)
        except TokenVerificationError as exc:
            raise MissingUserIdentityError(f"Invalid bearer token: {exc}") from exc

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            user_id = self._resolve_user_id(scope)
        except MissingUserIdentityError as exc:
            # Answer the request ourselves with a real 401 challenge instead of
            # letting this propagate into an unhandled-exception 500 -- see
            # _send_auth_error for why the status code specifically matters to
            # MCP clients. The inner app is never invoked.
            await _send_auth_error(send, str(exc), oauth_discovery.metadata_url())
            return

        token_reset = current_user_id.set(user_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_user_id.reset(token_reset)
