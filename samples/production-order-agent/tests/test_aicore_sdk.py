from __future__ import annotations

import json
import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from production_order_agent.agent import summarize_with_aicore


class MockDeployment:
    model_name = "synthetic-model"
    url = "https://mock-model.invalid/deployment"
    prediction_url = None

    def additional_request_body_kwargs(self) -> dict[str, Any]:
        return {}


class MockProxy:
    request_header = {"AI-Resource-Group": "synthetic-group"}

    def select_deployment(self, **kwargs: Any) -> MockDeployment:
        assert kwargs == {"model_name": "synthetic-model"}
        return MockDeployment()


@pytest.mark.parametrize("content", ["Synthetic order assessment", "", " ", None])
@pytest.mark.asyncio
async def test_native_sdk_routes_tool_records_and_rejects_empty_content(
    content: str | None,
) -> None:
    try:
        version("sap-ai-sdk-gen")
    except PackageNotFoundError:
        pytest.skip("Install the aicore extra to test its native SDK client")
    import gen_ai_hub.proxy.native.openai as sdk

    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.scheme == "https"
        assert request.url.host == "mock-model.invalid"
        assert request.url.path == "/deployment/chat/completions"
        assert request.url.params["api-version"]
        assert request.headers["AI-Resource-Group"] == "synthetic-group"
        payload = json.loads(request.content)
        assert payload["model"] == "synthetic-model"
        assert payload["temperature"] == 0
        assert payload["messages"][0]["role"] == "system"
        records = json.loads(payload["messages"][1]["content"])
        assert records["manufacturing_order"] == "1000000"
        assert records["statuses"] == [{"StatusName": "Released"}]
        assert records["operations"] == [{"Operation": "0010"}]
        return httpx.Response(
            200,
            json={
                "id": "synthetic-chat",
                "object": "chat.completion",
                "created": 1,
                "model": "synthetic-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(respond), trust_env=False) as http_client,
        sdk.AsyncOpenAI(proxy_client=MockProxy(), http_client=http_client, max_retries=0) as client,
    ):
        with patch.object(sdk, "AsyncOpenAI", return_value=client):
            arguments = (
                "synthetic-model",
                "1000000",
                [{"StatusName": "Released"}],
                [{"Operation": "0010"}],
            )
            if content and content.strip():
                assert await summarize_with_aicore(*arguments) == content
            else:
                with pytest.raises(RuntimeError, match="empty response"):
                    await summarize_with_aicore(*arguments)
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_sdk_completed_request_hides_endpoint_after_info_initialization(caplog):
    try:
        version("sap-ai-sdk-gen")
    except PackageNotFoundError:
        pytest.skip("Install the aicore extra to test its native SDK client")
    import gen_ai_hub.proxy.native.openai as sdk
    import httpx2

    import production_order_agent.__main__ as server

    caplog.set_level(logging.INFO)
    logger = logging.getLogger("httpx2")
    previous_level = logger.level
    logger.setLevel(logging.NOTSET)
    requests = []

    def respond(request):
        requests.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "synthetic-chat",
                "object": "chat.completion",
                "created": 1,
                "model": "synthetic-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Safe assessment"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    try:
        with patch.object(server.uvicorn, "run"):
            server.main()
        with patch.object(
            MockDeployment, "url", "https://model.private.invalid/private-endpoint-marker"
        ):
            async with (
                httpx2.AsyncClient(
                    transport=httpx2.MockTransport(respond), trust_env=False
                ) as http_client,
                sdk.AsyncOpenAI(
                    proxy_client=MockProxy(), http_client=http_client, max_retries=0
                ) as client,
            ):
                with patch.object(sdk, "AsyncOpenAI", return_value=client):
                    assert (
                        await summarize_with_aicore("synthetic-model", "1000000", [], [])
                        == "Safe assessment"
                    )
        logging.getLogger("production_order_agent").info("sdk-request-app-canary")
        assert len(requests) == 1
        assert "sdk-request-app-canary" in caplog.text
        assert "private-endpoint-marker" not in caplog.text
    finally:
        logger.setLevel(previous_level)
