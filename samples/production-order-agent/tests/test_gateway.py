from __future__ import annotations

import builtins
import json
import logging
from datetime import date
from functools import partial
from typing import Any

import httpx
import pytest
from starlette.testclient import TestClient

from production_order_agent.__main__ import create_app
from production_order_agent.agent import ProductionOrderAgent
from production_order_agent.gateway import summarize_with_gateway
from production_order_agent.settings import Settings


@pytest.fixture
def gateway_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_GATEWAY_URL", "https://gateway.example.invalid/v1")
    monkeypatch.setenv("MODEL_GATEWAY_API_KEY", "synthetic-bearer-key")
    monkeypatch.setenv("S4_API_KEY", "s4-secret-marker")
    monkeypatch.setenv("AICORE_CLIENT_SECRET", "aicore-secret-marker")


def completion(content: Any = "Gateway summary", role: str = "assistant") -> dict:
    return {"choices": [{"message": {"role": role, "content": content}}]}


@pytest.mark.asyncio
async def test_gateway_posts_selected_model_and_both_datasets_without_credentials(
    gateway_environment: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    requests: list[httpx.Request] = []
    statuses = [{"StatusName": "Released"}]
    operations = [{"Operation": "0010"}]

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://gateway.example.invalid/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-bearer-key"
        assert request.headers["Accept"] == "application/json"
        payload = json.loads(request.content)
        assert payload["model"] == "selected-model"
        assert payload["temperature"] == 0
        assert payload["stream"] is False
        assert payload["messages"][0]["role"] == "system"
        assert "Summarize only the supplied" in payload["messages"][0]["content"]
        records = json.loads(payload["messages"][1]["content"])
        assert records == {
            "today": date.today().isoformat(),
            "manufacturing_order": "1000000",
            "statuses": statuses,
            "operations": operations,
        }
        for private_value in (
            "synthetic-bearer-key",
            "s4-secret-marker",
            "aicore-secret-marker",
            "gateway.example.invalid",
        ):
            assert private_value not in payload["messages"][1]["content"]
        return httpx.Response(200, json=completion("  Gateway summary  "))

    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore")
    result = await summarize_with_gateway(
        "selected-model", "1000000", statuses, operations, transport=httpx.MockTransport(respond)
    )
    assert result == "Gateway summary"
    assert len(requests) == 1
    assert "gateway.example.invalid" not in caplog.text
    assert "synthetic-bearer-key" not in caplog.text


@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        (
            "https://gateway.example.invalid/v1/",
            "https://gateway.example.invalid/v1/chat/completions",
        ),
        ("http://127.0.0.1:3031/v1", "http://127.0.0.1:3031/v1/chat/completions"),
        ("http://[::1]:3031/v1", "http://[::1]:3031/v1/chat/completions"),
        ("http://localhost:3031/v1", "http://localhost:3031/v1/chat/completions"),
    ],
)
@pytest.mark.asyncio
async def test_https_and_local_http_gateway_paths(
    gateway_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    expected_url: str,
) -> None:
    monkeypatch.setenv("MODEL_GATEWAY_URL", base_url)

    def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == expected_url
        return httpx.Response(200, json=completion())

    assert (
        await summarize_with_gateway(
            "selected-model", "1000000", [], [], transport=httpx.MockTransport(respond)
        )
        == "Gateway summary"
    )


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("MODEL_GATEWAY_URL", ""),
        ("MODEL_GATEWAY_URL", "  "),
        ("MODEL_GATEWAY_URL", "http://external.example.invalid/v1"),
        ("MODEL_GATEWAY_URL", "ftp://gateway.example.invalid/v1"),
        ("MODEL_GATEWAY_URL", "https:///v1"),
        ("MODEL_GATEWAY_URL", "https://private-user:private-pass@gateway.example.invalid/v1"),
        ("MODEL_GATEWAY_URL", "https://gateway.example.invalid/v1?private=marker"),
        ("MODEL_GATEWAY_URL", "https://gateway.example.invalid/v1#private-marker"),
        ("MODEL_GATEWAY_URL", "https://gateway.example.invalid:bad/v1"),
        ("MODEL_GATEWAY_URL", "https://gateway.example.invalid/v1\nprivate-marker"),
        ("MODEL_GATEWAY_API_KEY", ""),
        ("MODEL_GATEWAY_API_KEY", "  "),
        ("MODEL_GATEWAY_API_KEY", "secret\nheader-marker"),
        ("MODEL_GATEWAY_API_KEY", "secret\x01header-marker"),
        ("MODEL_GATEWAY_API_KEY", "secret-é-marker"),
    ],
)
@pytest.mark.asyncio
async def test_invalid_gateway_configuration_fails_without_a_request(
    gateway_environment: None,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv(variable, value)

    def forbidden(_: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid configuration must not reach a provider")

    with pytest.raises(RuntimeError) as error:
        await summarize_with_gateway(
            "selected-model", "1000000", [], [], transport=httpx.MockTransport(forbidden)
        )
    assert value.strip() not in str(error.value) or not value.strip()
    assert "private-marker" not in str(error.value)


@pytest.mark.parametrize("model", ["", "  "])
@pytest.mark.asyncio
async def test_gateway_requires_an_explicit_model_before_a_request(
    gateway_environment: None,
    model: str,
) -> None:
    def forbidden(_: httpx.Request) -> httpx.Response:
        raise AssertionError("A model must be selected before a provider request")

    with pytest.raises(RuntimeError, match="MODEL_NAME"):
        await summarize_with_gateway(
            model, "1000000", [], [], transport=httpx.MockTransport(forbidden)
        )


@pytest.mark.parametrize("status", [301, 401, 429, 503])
@pytest.mark.asyncio
async def test_gateway_http_errors_hide_backend_details_and_do_not_follow_redirects(
    gateway_environment: None,
    status: int,
) -> None:
    calls = 0

    def respond(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            headers={"Location": "https://private-redirect.example.invalid/v1"},
            json={"error": "private-provider-diagnostic-marker"},
        )

    with pytest.raises(RuntimeError, match=f"HTTP {status}") as error:
        await summarize_with_gateway(
            "selected-model", "1000000", [], [], transport=httpx.MockTransport(respond)
        )
    assert calls == 1
    assert "private" not in str(error.value)
    assert "gateway.example.invalid" not in str(error.value)
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("exception_type", [httpx.ReadTimeout, httpx.ConnectError])
@pytest.mark.asyncio
async def test_gateway_transport_failures_hide_endpoint_and_diagnostics(
    gateway_environment: None,
    exception_type: type[httpx.RequestError],
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exception_type("private-transport-marker", request=request)

    with pytest.raises(RuntimeError, match="request failed") as error:
        await summarize_with_gateway(
            "selected-model", "1000000", [], [], transport=httpx.MockTransport(fail)
        )
    assert "private" not in str(error.value)
    assert "gateway.example.invalid" not in str(error.value)
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        {"choices": []},
        {"choices": "private-shape-marker"},
        {"choices": [None]},
        {"choices": [{"message": None}]},
        completion("", "assistant"),
        completion("  ", "assistant"),
        completion(None, "assistant"),
        completion([{"text": "private-content-marker"}], "assistant"),
        completion("private-content-marker", "user"),
    ],
)
@pytest.mark.asyncio
async def test_gateway_rejects_empty_or_malformed_completions(
    gateway_environment: None,
    payload: Any,
) -> None:
    with pytest.raises(RuntimeError, match="usable assistant reply") as error:
        await summarize_with_gateway(
            "selected-model",
            "1000000",
            [],
            [],
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)),
        )
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_gateway_rejects_non_json_without_exposing_its_body(
    gateway_environment: None,
) -> None:
    with pytest.raises(RuntimeError, match="invalid JSON") as error:
        await summarize_with_gateway(
            "selected-model",
            "1000000",
            [],
            [],
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, text="private-non-json-marker")
            ),
        )
    assert "private" not in str(error.value)


@pytest.mark.asyncio
async def test_gateway_dispatch_receives_both_tools_without_calling_aicore() -> None:
    seen: dict[str, Any] = {}

    async def fake_tool(_: str, tool_name: str, __: str) -> list[dict[str, Any]]:
        return [{"source": tool_name}]

    async def gateway_summary(model: str, order: str, statuses: list, operations: list) -> str:
        seen.update(model=model, order=order, statuses=statuses, operations=operations)
        return "Selected gateway reply"

    async def forbidden(*_: Any) -> str:
        raise AssertionError("Gateway mode must not call AI Core")

    agent = ProductionOrderAgent(
        Settings(llm_provider="openai-compatible", model_name="selected-model"),
        tool_caller=fake_tool,
        summarizer=forbidden,
        gateway_summarizer=gateway_summary,
    )
    assert await agent.invoke("Show order 1000000") == "Selected gateway reply"
    assert seen == {
        "model": "selected-model",
        "order": "1000000",
        "statuses": [{"source": "get_production_order_status"}],
        "operations": [{"source": "get_production_order_operations"}],
    }


@pytest.mark.asyncio
async def test_mock_dispatch_does_not_call_a_model_provider() -> None:
    async def fake_tool(_: str, __: str, ___: str) -> list[dict[str, Any]]:
        return []

    async def forbidden(*_: Any) -> str:
        raise AssertionError("Mock mode must not call any model provider")

    agent = ProductionOrderAgent(
        Settings(llm_provider="mock"),
        tool_caller=fake_tool,
        summarizer=forbidden,
        gateway_summarizer=forbidden,
    )
    assert "Production order 1000000" in await agent.invoke("Show order 1000000")


@pytest.mark.asyncio
async def test_gateway_does_not_import_the_optional_ai_core_sdk(
    gateway_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("gen_ai_hub"):
            raise AssertionError("Gateway mode must not import the AI Core SDK")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert (
        await summarize_with_gateway(
            "selected-model",
            "1000000",
            [],
            [],
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion())),
        )
        == "Gateway summary"
    )


def test_gateway_credentials_do_not_enter_settings_representation(
    gateway_environment: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("MODEL_NAME", "selected-model")
    settings = Settings.from_env()
    assert settings.llm_provider == "openai-compatible"
    assert settings.model_name == "selected-model"
    assert "synthetic-bearer-key" not in repr(settings)
    assert "gateway.example.invalid" not in repr(settings)


def test_provider_failure_returns_safe_failed_a2a_task(gateway_environment: None) -> None:
    async def fake_tool(_: str, tool_name: str, __: str) -> list[dict[str, Any]]:
        return [{"source": tool_name}]

    gateway_summary = partial(
        summarize_with_gateway,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(503, json={"error": "private-provider-marker"})
        ),
    )
    agent = ProductionOrderAgent(
        Settings(llm_provider="openai-compatible", model_name="selected-model"),
        tool_caller=fake_tool,
        gateway_summarizer=gateway_summary,
    )
    with TestClient(create_app(agent=agent)) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": "gateway-test",
                        "role": "ROLE_USER",
                        "parts": [{"text": "Show order 1000000"}],
                    }
                },
            },
        )
    serialized = response.text
    assert response.json()["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
    assert "could not be retrieved" in serialized
    for private_value in (
        "private-provider-marker",
        "gateway.example.invalid",
        "synthetic-bearer-key",
    ):
        assert private_value not in serialized
