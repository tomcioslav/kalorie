"""The MCP server's ASGI app and its dev/production runner.

No Lambda anymore, so no Mangum and no per-invocation session-manager
rebuild (see git history for that workaround, if curious) — this is the
plain, SDK-recommended shape: build the app once, run it with uvicorn.
Under uvicorn the ASGI lifespan runs exactly once for the life of the
process, which is exactly what `mcp.streamable_http_app()`'s cached
session manager expects.

Usage: python -m calorie_tracker.mcp_app.main
Then point the MCP inspector (`npx @modelcontextprotocol/inspector`) or a
manual client at http://127.0.0.1:8000/mcp
"""

import uvicorn

from calorie_tracker.config import settings
from calorie_tracker.mcp_app.context import UserContextMiddleware
from calorie_tracker.mcp_app.server import mcp
from calorie_tracker.repositories.base import init_db

# A freshly deployed instance starts with no SQLite file at all, so every
# repository call would fail with "no such table" until something creates
# the schema. init_db() is idempotent (CREATE TABLE IF NOT EXISTS), so it's
# safe to call unconditionally on every import of this module -- this is
# what makes both local dev (`python -m calorie_tracker.mcp_app.main`) and
# however the eventual deployment invokes this module always have a working
# schema before serving any request.
init_db()

app = UserContextMiddleware(mcp.streamable_http_app())

if __name__ == "__main__":
    uvicorn.run(app, host=settings.uvicorn_host, port=settings.uvicorn_port)
