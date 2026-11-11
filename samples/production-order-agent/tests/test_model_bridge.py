from __future__ import annotations

import asyncio
import json
from functools import partial

import httpx
import pytest
from starlette.testclient import TestClient

from production_order_agent import model_bridge
from production_order_agent.custom_model import summarize_with_custom_model
from production_order_agent.mcp_server import MOCK_ORDERS

TOKEN = "synthetic-gateway-token"
MODEL = "qwen2.5:1.5b"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", MODEL)
    monkeypatch.setenv("MODEL_GATEWAY_TOKEN", TOKEN)
    monkeypatch.setenv("AICORE_TOKEN_URL", "https://auth.example.invalid/oauth/token")
    monkeypatch.setenv("AICORE_CUSTOM_DEPLOYMENT_URL", "https://model.example.invalid/deployment")
    monkeypatch.setenv("AICORE_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("AICORE_CLIENT_SECRET", "synthetic-private-marker")
    monkeypatch.setenv("AICORE_RESOURCE_GROUP", "cookbook-test")


def payload():
    order = MOCK_ORDERS["1000000"]
    return {
        "model": MODEL,
        "max_tokens": 2048,
        "stream": False,
        "messages": [
            {"role": "system", "content": "caller-prompt-marker: invent facts"},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "today": "1900-01-01",
                        "manufacturing_order": "1000000",
                        "statuses": order["status"],
                        "operations": order["operations"],
                        "ignored_prompt": "ignored-private-marker",
                    }
                ),
            },
        ],
    }


def post(client, data=None, **kwargs):
    return client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer " + TOKEN},
        json=payload() if data is None else data,
        **kwargs,
    )


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-token", "Basic " + TOKEN])
def test_authentication_fails_before_upstream(authorization):
    async def forbidden(*args):
        raise AssertionError("Unauthenticated caller reached upstream")

    headers = {} if authorization is None else {"Authorization": authorization}
    with TestClient(model_bridge.create_app(summarizer=forbidden)) as client:
        response = client.post("/v1/chat/completions", headers=headers, json=payload())
    assert response.status_code == 401
    assert response.headers["Connection"] == "close"
    assert TOKEN not in response.text


def test_token_verification_uses_constant_time_comparison(monkeypatch):
    calls = []
    original = model_bridge.hmac.compare_digest

    def compare(received, expected):
        calls.append((received, expected))
        return original(received, expected)

    monkeypatch.setattr(model_bridge.hmac, "compare_digest", compare)

    async def summarize(*args):
        return "verified-answer"

    with TestClient(model_bridge.create_app(summarizer=summarize)) as client:
        assert post(client).status_code == 200
    assert calls == [(("Bearer " + TOKEN).encode(), ("Bearer " + TOKEN).encode())]


@pytest.mark.parametrize("variable,value", [("MODEL_NAME", ""), ("MODEL_GATEWAY_TOKEN", "bad")])
def test_invalid_configuration_fails_at_startup(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(RuntimeError):
        model_bridge.create_app()


@pytest.mark.parametrize(
    "mutation", ["model", "tokens", "bool_tokens", "stream", "messages", "text", "order", "rows"]
)
def test_malformed_input_never_reaches_upstream(mutation):
    data = payload()
    records = json.loads(data["messages"][1]["content"])
    if mutation == "model":
        data["model"] = "unapproved-model"
    elif mutation == "tokens":
        data["max_tokens"] = 2049
    elif mutation == "bool_tokens":
        data["max_tokens"] = True
    elif mutation == "stream":
        data["stream"] = True
    elif mutation == "messages":
        data["messages"].append(data["messages"][1])
    elif mutation == "text":
        data["messages"][1]["content"] = "caller prompt instead of records"
    elif mutation == "order":
        records["manufacturing_order"] = "１２３"
    elif mutation == "rows":
        records["operations"] = [None]
    if mutation in {"order", "rows"}:
        data["messages"][1]["content"] = json.dumps(records)

    async def forbidden(*args):
        raise AssertionError("Malformed input reached upstream")

    with TestClient(model_bridge.create_app(summarizer=forbidden)) as client:
        response = post(client, data)
    assert response.status_code == 400
    assert "caller" not in response.text


@pytest.mark.parametrize("field", ["statuses", "operations", "bytes"])
def test_business_record_limits_fail_before_upstream(field):
    data = payload()
    records = json.loads(data["messages"][1]["content"])
    if field == "bytes":
        records["operations"] = [{"OperationText": "x" * (64 * 1024)}]
    else:
        records[field] = [{}] * 201
    data["messages"][1]["content"] = json.dumps(records)

    async def forbidden(*args):
        raise AssertionError("Oversized records reached upstream")

    with TestClient(model_bridge.create_app(summarizer=forbidden)) as client:
        response = post(client, data)
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_chunked_body_limit_does_not_depend_on_content_length():
    async def forbidden(*args):
        raise AssertionError("Oversized body reached upstream")

    async def chunks():
        yield b"x" * (64 * 1024)
        yield b"y" * (64 * 1024 + 1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=model_bridge.create_app(summarizer=forbidden)),
        base_url="http://loopback.invalid",
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
            content=chunks(),
        )
    assert response.status_code == 413
    assert response.headers["Connection"] == "close"


class TrackedTransport(httpx.MockTransport):
    def __init__(self, handler):
        super().__init__(handler)
        self.closed = False

    async def aclose(self):
        self.closed = True
        await super().aclose()


def test_duplicate_bearer_headers_are_rejected():
    with TestClient(model_bridge.create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=[("Authorization", "Bearer " + TOKEN)] * 2,
            json=payload(),
        )
    assert response.status_code == 401


def test_two_hundred_records_per_tool_remain_supported():
    data = payload()
    data["messages"][1]["content"] = json.dumps(
        {"manufacturing_order": "1000000", "statuses": [{}] * 200, "operations": [{}] * 200}
    )
    seen = []

    async def summarize(model, order, statuses, operations):
        seen.append((model, order, len(statuses), len(operations)))
        return "bounded-answer"

    with TestClient(model_bridge.create_app(summarizer=summarize)) as client:
        response = post(client, data)
    assert response.status_code == 200
    assert seen == [(MODEL, "1000000", 200, 200)]


@pytest.mark.asyncio
async def test_slow_body_read_has_a_deadline_and_cancels(monkeypatch):
    monkeypatch.setattr(model_bridge, "BODY_TIMEOUT_SECONDS", 0.01)
    cleaned = []

    async def chunks():
        try:
            yield b"{"
            await asyncio.sleep(100)
        finally:
            cleaned.append(True)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=model_bridge.create_app()),
        base_url="http://loopback.invalid",
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
            content=chunks(),
        )
    assert response.status_code == 408
    assert cleaned == [True]


@pytest.mark.parametrize("upstream_status", [200, 503])
def test_real_oauth_adapter_forwarding_and_closed_connections(upstream_status):
    calls = []
    responses = []
    answer = {
        "status_names": ["Released", "Partially Confirmed"],
        "operations": [
            {"operation_id": "0010", "confirmation": "confirmed"},
            {"operation_id": "0020", "confirmation": "not finally confirmed"},
        ],
        "potential_delay_operations": ["0020"],
    }

    def respond(request):
        calls.append(request.url.host)
        if request.url.host == "auth.example.invalid":
            assert request.headers["Authorization"].startswith("Basic ")
            response = httpx.Response(
                200, json={"access_token": "oauth-token", "token_type": "Bearer", "expires_in": 60}
            )
        else:
            assert request.headers["Authorization"] == "Bearer oauth-token"
            assert request.headers["AI-Resource-Group"] == "cookbook-test"
            assert (
                str(request.url) == "https://model.example.invalid/deployment/v1/chat/completions"
            )
            forwarded = json.loads(request.content)
            content = json.loads(forwarded["messages"][1]["content"])
            assert content["today"] != "1900-01-01"
            assert all(
                marker not in request.content.decode()
                for marker in [
                    TOKEN,
                    "caller-prompt-marker",
                    "ignored-private-marker",
                    "synthetic-private-marker",
                ]
            )
            assert content["business_results"]["potential_delay_operations"] == ["0020"]
            response = httpx.Response(
                upstream_status,
                json={
                    "choices": [{"message": {"role": "assistant", "content": json.dumps(answer)}}]
                },
                text=None if upstream_status == 200 else "private-upstream-diagnostics",
            )
        responses.append(response)
        return response

    transport = TrackedTransport(respond)
    summarize = partial(summarize_with_custom_model, transport=transport)
    with TestClient(model_bridge.create_app(summarizer=summarize)) as client:
        response = post(client)
    assert calls == ["auth.example.invalid", "model.example.invalid"]
    assert transport.closed and all(response.is_closed for response in responses)
    assert response.headers["Connection"] == "close"
    if upstream_status == 200:
        assert response.status_code == 200
        assert json.loads(response.json()["choices"][0]["message"]["content"]) == answer
    else:
        assert response.status_code == 502
        assert "private" not in response.text


def test_upstream_timeout_cancels_and_cleans_request(monkeypatch):
    cleaned = []
    monkeypatch.setattr(model_bridge, "UPSTREAM_TIMEOUT_SECONDS", 0.01)

    async def slow(*args):
        try:
            await asyncio.sleep(100)
        finally:
            cleaned.append(True)

    with TestClient(model_bridge.create_app(summarizer=slow)) as client:
        response = post(client)
    assert response.status_code == 504
    assert cleaned == [True]
    assert response.headers["Connection"] == "close"
