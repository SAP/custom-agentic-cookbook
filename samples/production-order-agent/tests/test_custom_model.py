from __future__ import annotations

import json
from functools import partial

import httpx
import pytest
from starlette.testclient import TestClient

from production_order_agent.__main__ import create_app
from production_order_agent.agent import ProductionOrderAgent
from production_order_agent.custom_model import summarize_with_custom_model
from production_order_agent.mcp_server import MOCK_ORDERS
from production_order_agent.settings import Settings


@pytest.fixture
def environment(monkeypatch):
    monkeypatch.setenv("AICORE_TOKEN_URL", "https://auth.example.invalid/oauth/token")
    monkeypatch.setenv(
        "AICORE_CUSTOM_DEPLOYMENT_URL", "https://inference.example.invalid/deployment"
    )
    monkeypatch.setenv("AICORE_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("AICORE_CLIENT_SECRET", "synthetic-private-marker")
    monkeypatch.setenv("AICORE_RESOURCE_GROUP", "cookbook-test")


@pytest.mark.asyncio
async def test_oauth_expiry_retries_once_and_keeps_credentials_out_of_business_payload(environment):
    tokens = 0
    requests = 0

    def respond(request):
        nonlocal tokens, requests
        if request.url.host == "auth.example.invalid":
            tokens += 1
            assert request.headers["Authorization"].startswith("Basic ")
            assert request.content == b"grant_type=client_credentials"
            return httpx.Response(
                200,
                json={"access_token": f"token-{tokens}", "token_type": "Bearer", "expires_in": 60},
            )
        requests += 1
        assert request.headers["AI-Resource-Group"] == "cookbook-test"
        assert (
            str(request.url) == "https://inference.example.invalid/deployment/v1/chat/completions"
        )
        assert request.headers["Authorization"] == f"Bearer token-{tokens}"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen2.5:1.5b"
        assert "private-marker" not in request.content.decode()
        records = json.loads(payload["messages"][1]["content"])
        assert records["business_results"]["status_names"] == ["Released"]
        assert records["business_results"]["operations"][0]["operation_id"] == "0020"
        assert records["business_results"]["potential_delay_operations"] == []
        if requests == 1:
            return httpx.Response(401)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "status_names": ["Released"],
                                    "operations": [
                                        {
                                            "operation_id": "0020",
                                            "confirmation": "not finally confirmed",
                                        }
                                    ],
                                    "potential_delay_operations": [],
                                }
                            ),
                        }
                    }
                ]
            },
        )

    answer = await summarize_with_custom_model(
        "qwen2.5:1.5b",
        "1000000",
        [{"StatusName": "Released"}],
        [{"Operation": "0020"}],
        transport=httpx.MockTransport(respond),
    )
    assert json.loads(answer)["status_names"] == ["Released"]
    assert tokens == requests == 2


@pytest.mark.parametrize("status", [301, 403, 429, 503])
@pytest.mark.asyncio
async def test_errors_never_follow_redirects_or_expose_diagnostics(environment, status):
    calls = 0

    def respond(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            status, headers={"Location": "https://private.example.invalid"}, text="private-marker"
        )

    with pytest.raises(RuntimeError, match="HTTP") as error:
        await summarize_with_custom_model(
            "qwen2.5:1.5b", "1000000", [], [], transport=httpx.MockTransport(respond)
        )
    assert calls == 1
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"access_token": "private\nmarker"},
        {"access_token": "valid", "token_type": "Basic"},
        {"access_token": "valid", "token_type": "Bearer", "expires_in": 0},
    ],
)
@pytest.mark.asyncio
async def test_bad_tokens_fail_without_inference(environment, payload):
    with pytest.raises(RuntimeError, match="token"):
        await summarize_with_custom_model(
            "qwen2.5:1.5b",
            "1000000",
            [],
            [],
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
        )


@pytest.mark.parametrize(
    "variable,value",
    [
        ("AICORE_TOKEN_URL", "http://outside.example.invalid"),
        ("AICORE_CUSTOM_DEPLOYMENT_URL", "https://user:pass@host.invalid"),
        ("AICORE_RESOURCE_GROUP", "private\nmarker"),
        ("AICORE_CLIENT_SECRET", ""),
        ("AICORE_TOKEN_URL", "https://host.invalid?private=marker"),
        ("AICORE_CUSTOM_TIMEOUT_SECONDS", "0"),
        ("AICORE_CUSTOM_TIMEOUT_SECONDS", "301"),
        ("AICORE_CUSTOM_TIMEOUT_SECONDS", "invalid"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_configuration_never_contacts_provider(
    environment, monkeypatch, variable, value
):
    monkeypatch.setenv(variable, value)

    def forbidden(request):
        raise AssertionError("Invalid configuration reached a provider")

    with pytest.raises(RuntimeError):
        await summarize_with_custom_model(
            "qwen2.5:1.5b", "1000000", [], [], transport=httpx.MockTransport(forbidden)
        )


@pytest.mark.asyncio
async def test_bounded_records_fail_before_network(environment):
    def forbidden(request):
        raise AssertionError("Unbounded records reached a provider")

    with pytest.raises(RuntimeError, match="bound"):
        await summarize_with_custom_model(
            "qwen2.5:1.5b", "1000000", [{}] * 201, [], transport=httpx.MockTransport(forbidden)
        )


@pytest.mark.asyncio
async def test_completion_budget_preserves_all_accepted_operations(environment):
    operations = [{"Operation": f"{number:04d}"} for number in range(8)]
    answer = {
        "status_names": ["Released"],
        "operations": [
            {"operation_id": row["Operation"], "confirmation": "not finally confirmed"}
            for row in operations
        ],
        "potential_delay_operations": [],
    }

    def respond(request):
        if request.url.host == "auth.example.invalid":
            return httpx.Response(
                200, json={"access_token": "valid", "token_type": "Bearer", "expires_in": 60}
            )
        payload = json.loads(request.content)
        # The old two-operation completion allowance truncates longer structured replies.
        content = "{" if payload["max_tokens"] <= 192 else json.dumps(answer)
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": content}}]}
        )

    reply = await summarize_with_custom_model(
        "qwen2.5:1.5b",
        "1000000",
        [{"StatusName": "Released"}],
        operations,
        transport=httpx.MockTransport(respond),
    )
    assert json.loads(reply) == answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operations",
    [
        [{"Operation": "0010", "OperationText": "1 " * 10000}],
        [{"Operation": f"{number:04d}"} for number in range(20)],
    ],
)
async def test_inputs_that_cannot_fit_model_context_fail_before_oauth(environment, operations):
    def forbidden(request):
        raise AssertionError("Oversized model context reached a provider")

    with pytest.raises(RuntimeError, match="context.*bound"):
        await summarize_with_custom_model(
            "qwen2.5:1.5b",
            "1000000",
            [],
            operations,
            transport=httpx.MockTransport(forbidden),
        )


def test_custom_provider_completes_real_a2a_artifact(environment):
    async def tools(url, name, order):
        return MOCK_ORDERS[order]["status" if name.endswith("status") else "operations"]

    def respond(request):
        if request.url.host == "auth.example.invalid":
            return httpx.Response(
                200, json={"access_token": "valid-token", "token_type": "Bearer", "expires_in": 60}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "status_names": ["Released", "Partially Confirmed"],
                                    "operations": [
                                        {"operation_id": "0010", "confirmation": "confirmed"},
                                        {
                                            "operation_id": "0020",
                                            "confirmation": "not finally confirmed",
                                        },
                                    ],
                                    "potential_delay_operations": ["0020"],
                                }
                            ),
                        }
                    }
                ]
            },
        )

    agent = ProductionOrderAgent(
        Settings(llm_provider="aicore-custom", model_name="qwen2.5:1.5b"),
        tool_caller=tools,
        custom_summarizer=partial(
            summarize_with_custom_model, transport=httpx.MockTransport(respond)
        ),
    )
    with TestClient(create_app(agent=agent)) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": "custom-test",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": "custom-test",
                        "role": "ROLE_USER",
                        "parts": [{"text": "Show order 1000000"}],
                    }
                },
            },
        )
    assert response.json()["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert all(
        value in response.text for value in ("Released", "Partially Confirmed", "0010", "0020")
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "malformed",
        "missing_status",
        "missing_operation",
        "false_confirmation",
        "false_delay",
        "extra_operation_field",
    ],
)
@pytest.mark.asyncio
async def test_incomplete_or_changed_business_facts_fail(environment, mutation):
    answer = {
        "status_names": ["Released", "Partially Confirmed"],
        "operations": [
            {"operation_id": "0010", "confirmation": "confirmed"},
            {"operation_id": "0020", "confirmation": "not finally confirmed"},
        ],
        "potential_delay_operations": ["0020"],
    }
    if mutation == "missing_status":
        answer["status_names"].pop()
    elif mutation == "missing_operation":
        answer["operations"].pop()
    elif mutation == "false_confirmation":
        answer["operations"][1]["confirmation"] = "confirmed"
    elif mutation == "false_delay":
        answer["potential_delay_operations"] = ["0010"]
    elif mutation == "extra_operation_field":
        answer["operations"][0]["provider_diagnostic"] = "private-provider-marker"

    def respond(request):
        if request.url.host == "auth.example.invalid":
            return httpx.Response(
                200, json={"access_token": "valid-token", "token_type": "Bearer", "expires_in": 60}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "{" if mutation == "malformed" else json.dumps(answer),
                        }
                    }
                ]
            },
        )

    order = MOCK_ORDERS["1000000"]
    with pytest.raises(RuntimeError, match="no usable assistant reply"):
        await summarize_with_custom_model(
            "qwen2.5:1.5b",
            "1000000",
            order["status"],
            order["operations"],
            transport=httpx.MockTransport(respond),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "phase,status_code", [("token", 200), ("inference", 200), ("inference", 503)]
)
async def test_oversized_response_stops_reading_and_closes_stream(environment, phase, status_code):
    class Oversized(httpx.AsyncByteStream):
        chunks_read = 0
        closed = False

        async def __aiter__(self):
            for _ in range(128):
                self.chunks_read += 1
                yield b"x" * 65536

        async def aclose(self):
            self.closed = True

    stream = Oversized()

    def respond(request):
        if request.url.host == "auth.example.invalid" and phase == "inference":
            return httpx.Response(
                200, json={"access_token": "valid-token", "token_type": "Bearer", "expires_in": 60}
            )
        return httpx.Response(status_code, stream=stream)

    expected = "response.*bound" if status_code == 200 else "HTTP 503"
    with pytest.raises(RuntimeError, match=expected):
        await summarize_with_custom_model(
            "qwen2.5:1.5b", "1000000", [], [], transport=httpx.MockTransport(respond)
        )
    assert stream.chunks_read < 128
    assert stream.closed
    if status_code == 503:
        assert stream.chunks_read == 0


@pytest.mark.asyncio
async def test_complete_oauth_and_inference_call_has_one_deadline(environment, monkeypatch):
    import asyncio

    monkeypatch.setenv("AICORE_CUSTOM_TIMEOUT_SECONDS", "1")

    class Slow(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            for _ in range(20):
                await asyncio.sleep(0.1)
                yield b" "

        async def aclose(self):
            self.closed = True

    stream = Slow()
    with pytest.raises(RuntimeError, match="Custom model request failed"):
        await summarize_with_custom_model(
            "qwen2.5:1.5b",
            "1000000",
            [],
            [],
            transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
        )
    assert stream.closed
