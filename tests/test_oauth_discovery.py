import pytest

from calorie_tracker import config
from calorie_tracker.mcp_app import oauth_discovery


@pytest.fixture(autouse=True)
def public_url_and_cognito_settings(monkeypatch):
    monkeypatch.setattr(config.settings, "public_mcp_url", "https://52-14-201-9.sslip.io/mcp")
    monkeypatch.setattr(config.settings, "cognito_region", "eu-central-1")
    monkeypatch.setattr(config.settings, "cognito_user_pool_id", "eu-central-1_TestPool")


def test_metadata_url_derives_origin_and_appends_well_known_path():
    assert (
        oauth_discovery.metadata_url()
        == "https://52-14-201-9.sslip.io/.well-known/oauth-protected-resource"
    )


def test_metadata_url_ignores_query_or_fragment_if_present(monkeypatch):
    monkeypatch.setattr(config.settings, "public_mcp_url", "https://example.com/mcp?x=1")
    assert oauth_discovery.metadata_url() == "https://example.com/.well-known/oauth-protected-resource"


def test_metadata_document_shape():
    doc = oauth_discovery.metadata_document()
    assert doc == {
        "resource": "https://52-14-201-9.sslip.io/mcp",
        "authorization_servers": ["https://cognito-idp.eu-central-1.amazonaws.com/eu-central-1_TestPool"],
    }


async def test_router_serves_the_well_known_path_without_touching_wrapped_app():
    calls = []

    async def inner_app(scope, receive, send):
        calls.append(scope)

    router = oauth_discovery.OAuthDiscoveryRouter(
        inner_app,
        oauth_discovery.WELL_KNOWN_PATH,
        lambda: {"resource": "x", "authorization_servers": ["y"]},
    )

    sent = []

    async def send(message):
        sent.append(message)

    await router({"type": "http", "path": oauth_discovery.WELL_KNOWN_PATH}, None, send)

    assert calls == [], "the wrapped app must never be called for the well-known path"
    assert sent[0]["status"] == 200
    import json
    assert json.loads(sent[1]["body"]) == {"resource": "x", "authorization_servers": ["y"]}


async def test_router_forwards_other_http_paths_to_the_wrapped_app():
    calls = []

    async def inner_app(scope, receive, send):
        calls.append(scope["path"])

    router = oauth_discovery.OAuthDiscoveryRouter(inner_app, oauth_discovery.WELL_KNOWN_PATH, lambda: {})
    await router({"type": "http", "path": "/mcp"}, None, None)

    assert calls == ["/mcp"]


async def test_router_forwards_non_http_scopes_unchanged():
    """The whole point: the ASGI `lifespan` scope must reach the wrapped
    app exactly as before, or the mounted session manager never starts."""
    calls = []

    async def inner_app(scope, receive, send):
        calls.append(scope["type"])

    router = oauth_discovery.OAuthDiscoveryRouter(inner_app, oauth_discovery.WELL_KNOWN_PATH, lambda: {})
    await router({"type": "lifespan"}, None, None)

    assert calls == ["lifespan"]
