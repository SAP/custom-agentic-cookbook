# syntax=docker/dockerfile:1

ARG UV_VERSION=0.11.21
ARG PYTHON_VERSION=3.12
FROM ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-trixie-slim

RUN groupadd --system --gid 10001 appgroup \
    && useradd --system --gid 10001 --uid 10001 --shell /usr/sbin/nologin \
        --no-create-home appuser

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --all-extras --no-install-project

COPY --chown=10001:10001 src ./src

ENV HOST="0.0.0.0" \
    PORT="8000" \
    URL="http://localhost:8000" \
    MCP_HOST="0.0.0.0" \
    MCP_PORT="8090" \
    MCP_SERVER_URL="http://localhost:8090/sse" \
    DATA_MODE="mock" \
    LLM_PROVIDER="mock"

EXPOSE 8000 8090

USER 10001:10001

CMD ["python", "-m", "production_order_agent"]
