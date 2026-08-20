"""RFC 9728 OAuth protected-resource metadata -- how Claude discovers that
Cognito is this server's authorization server. Required, not optional:
Claude's remote-connector OAuth flow refuses to proceed without (a) a 401
response whose WWW-Authenticate header carries a resource_metadata pointer,
and (b) that URL actually serving this document. See
https://claude.com/docs/connectors/building/authentication.

The dispatcher below is deliberately hand-written rather than composed via
Starlette's Router/Mount -- verified directly (not assumed) that nesting the
existing UserContextMiddleware-wrapped app under a Mount silently breaks its
ASGI lifespan propagation, so mcp.streamable_http_app()'s session manager
never starts and every /mcp request fails. This class instead forwards
every scope it doesn't specifically handle -- including "lifespan" --
unchanged to the wrapped app, the same pattern UserContextMiddleware
itself already uses.
"""

import json
from urllib.parse import urlsplit, urlunsplit

from calorie_tracker.config import settings
from calorie_tracker.mcp_app.jwt_auth import issuer_url

WELL_KNOWN_PATH = "/.well-known/oauth-protected-resource"


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def metadata_url() -> str:
    """Where the metadata document itself lives -- same host as the MCP
    endpoint, at the well-known path."""
    return f"{_origin(settings.public_mcp_url)}{WELL_KNOWN_PATH}"


def metadata_document() -> dict:
    """The RFC 9728 document. `resource` must be the exact, full URL a user
    enters in Claude as the connector address (including the /mcp path) --
    not just the origin."""
    return {
        "resource": settings.public_mcp_url,
        "authorization_servers": [issuer_url()],
    }


class OAuthDiscoveryRouter:
    """Serves the metadata document at `well_known_path` (no auth required
    -- it's how a client discovers the authorization server in the first
    place). Forwards every other request, and every non-"http" ASGI scope
    (lifespan included), to the wrapped app unchanged.

    `build_metadata_document` is a zero-argument callable (e.g.
    `metadata_document`) invoked fresh on every matching request, not a
    pre-built dict -- so the served document always reflects current
    settings rather than whatever was in effect when this router was
    constructed."""

    def __init__(self, app, well_known_path: str, build_metadata_document):
        self.app = app
        self.well_known_path = well_known_path
        self.build_metadata_document = build_metadata_document

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == self.well_known_path:
            body = json.dumps(self.build_metadata_document()).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)
