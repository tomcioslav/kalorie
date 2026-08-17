# Local-testing image only. The real deployment target (AWS Lightsail) runs
# this as a plain systemd + uvicorn process, not a container — this exists
# purely so you can run/poke at the app without a local Python setup.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Install dependencies first, separately from the source, so editing app
# code doesn't invalidate this (slow) layer on rebuild.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY src/ ./src/
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"
# The default host (127.0.0.1) is unreachable from outside the container;
# 0.0.0.0 is what makes docker's port mapping actually work. (Not
# FASTMCP_HOST -- that env var is silently ignored, see main.py.)
ENV UVICORN_HOST=0.0.0.0

EXPOSE 8000

CMD ["python", "-m", "calorie_tracker.mcp_app.main"]
