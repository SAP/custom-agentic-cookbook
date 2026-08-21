# Minimal Python A2A v1.0 sample

> **Status:** Experimental, local-only reference. This sample is supporting
> evidence for the Cookbook's local-agent milestone; it does not replace the
> supported scaffold flow in [`recipes/01-scaffold-agent`](../../recipes/01-scaffold-agent/).

This credential-free sample exposes a Hello World agent through A2A v1.0. It
demonstrates the smallest useful server shape: an Agent Card, an in-memory task
store, and a synchronous `SendMessage` request that returns an artifact.

The sample intentionally excludes an LLM, business tools, authentication,
persistence, streaming, push notifications, containers, and deployment assets.
It is not a production agent.

## Prerequisites

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- `curl` and `jq` for the manual smoke test

## Run locally

From this directory:

```bash
uv sync --frozen
uv run python -m app
```

The server listens on `http://127.0.0.1:8000`. Set `HOST`, `PORT`, or `URL` to
override the bind address, port, or public URL advertised by the Agent Card.

## Verify it works

In another terminal, fetch the Agent Card:

```bash
curl -s http://127.0.0.1:8000/.well-known/agent-card.json | jq .name
```

Expected result:

```text
"Hello World Agent"
```

Then send a real A2A message:

```bash
curl -s -X POST http://127.0.0.1:8000/ \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "messageId": "msg-1",
        "role": "ROLE_USER",
        "parts": [{"text": "hi"}]
      }
    }
  }' | jq
```

The response should contain a completed task with a `Hello, World!` artifact.

## Run the tests

```bash
uv run --group dev pytest
```
