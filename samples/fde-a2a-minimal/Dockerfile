# syntax=docker/dockerfile:1

ARG UV_VERSION=0.11.12
ARG PYTHON_VERSION=3.12
FROM ghcr.io/astral-sh/uv:${UV_VERSION}-python${PYTHON_VERSION}-trixie-slim

RUN groupadd --system --gid 999 appgroup \
    && useradd --system --gid 999 --uid 999 --shell /usr/sbin/nologin \
        --create-home appuser

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

COPY --chown=999:999 app ./app

ENV HOST="0.0.0.0" \
    PORT="8000" \
    URL="http://localhost:8000" \
    PYTHONDONTWRITEBYTECODE="1"

EXPOSE 8000

USER 999:999

CMD ["python", "-m", "app"]
