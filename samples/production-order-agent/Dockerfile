# syntax=docker/dockerfile:1

ARG BASE_IMAGE=ghcr.io/astral-sh/uv:0.13.5-python3.12-trixie-slim@sha256:9b8477a5f2e2f96fa99eaecb7680c1c4c9f527926430f3b630bfb2c3641f8f20
FROM ${BASE_IMAGE}

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

RUN /usr/local/bin/python -m pip uninstall --yes pip \
    && /usr/local/bin/python -c 'import ensurepip, pathlib, shutil; shutil.rmtree(pathlib.Path(ensurepip.__file__).parent)'

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
