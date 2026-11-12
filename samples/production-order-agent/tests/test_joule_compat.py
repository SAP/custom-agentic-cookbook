import json

import pytest
from starlette.testclient import TestClient

from production_order_agent.__main__ import create_app


class BusinessAgent:
    async def invoke(self, text: str) -> str:
        return f"Synthetic production-order summary: {text}"


class FailingAgent:
    async def invoke(self, _: str) -> str:
        raise RuntimeError("private-backend-diagnostic-marker")


def request_v03() -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "synthetic-joule",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "synthetic-joule",
                "role": "user",
                "parts": [{"kind": "text", "text": "Show production order 1000000"}],
            }
        },
    }


def test_v03_is_disabled_by_default() -> None:
    with TestClient(create_app(agent=BusinessAgent())) as client:
        response = client.post("/", json=request_v03())
        card = client.get("/.well-known/agent-card.json").json()
        legacy = client.get("/.well-known/agent.json")
    assert response.json()["error"]["code"] == -32601
    assert [i["protocolVersion"] for i in card["supportedInterfaces"]] == ["1.0"]
    assert legacy.status_code == 404


def test_opt_in_serves_legacy_card_and_preserves_v1_card() -> None:
    with TestClient(create_app("https://agent.example.com", joule_v03=True)) as client:
        legacy = client.get("/.well-known/agent.json").json()
        current = client.get("/.well-known/agent-card.json").json()
    assert legacy["protocolVersion"] == "0.3.0"
    assert legacy["url"] == "https://agent.example.com"
    assert legacy["preferredTransport"] == "JSONRPC"
    assert legacy["skills"][0]["id"] == "production_order_lookup"
    assert "securitySchemes" not in legacy
    assert [i["protocolVersion"] for i in current["supportedInterfaces"]] == ["1.0", "0.3.0"]


def test_opt_in_returns_completed_v03_artifact_without_v1_header() -> None:
    with TestClient(create_app(agent=BusinessAgent(), joule_v03=True)) as client:
        response = client.post("/", json=request_v03())
        request = request_v03()
        request["method"] = "SendMessage"
        request["params"]["message"]["role"] = "ROLE_USER"
        request["params"]["message"]["parts"] = [{"text": "Show production order 1000000"}]
        current = client.post("/", headers={"A2A-Version": "1.0"}, json=request).json()
    task = response.json()["result"]
    assert task["status"]["state"] == "completed"
    assert task["artifacts"][0]["name"] == "production-order-summary"
    assert task["artifacts"][0]["parts"][0]["kind"] == "text"
    assert "Synthetic production-order summary" in task["artifacts"][0]["parts"][0]["text"]
    assert "message" not in task["status"]
    assert current["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"


def test_opt_in_returns_safe_failed_task() -> None:
    with TestClient(create_app(agent=FailingAgent(), joule_v03=True)) as client:
        response = client.post("/", json=request_v03()).json()
    assert response["result"]["status"]["state"] == "failed"
    assert response["result"]["artifacts"][0]["name"] == "error"
    assert "could not be retrieved" in json.dumps(response)
    assert "private-backend-diagnostic-marker" not in json.dumps(response)


@pytest.mark.parametrize(
    "body, code", [("{", -32700), ('{"jsonrpc":"2.0","method":"unknown"}', -32601)]
)
def test_opt_in_reports_protocol_errors(body: str, code: int) -> None:
    with TestClient(create_app(joule_v03=True)) as client:
        response = client.post("/", content=body, headers={"Content-Type": "application/json"})
    assert response.json()["error"]["code"] == code
