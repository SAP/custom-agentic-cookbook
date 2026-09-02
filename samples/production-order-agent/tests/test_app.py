import json

from starlette.testclient import TestClient

from production_order_agent.__main__ import build_agent_card, create_app

BASE_URL = "http://testserver"


class FakeAgent:
    async def invoke(self, text: str) -> str:
        return f"Production-order result for: {text}"


class FailingAgent:
    async def invoke(self, _: str) -> str:
        raise RuntimeError("private-backend-diagnostic-marker")


def _request(text: str = "Why is production order 1000000 delayed?") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "msg-1",
                "role": "ROLE_USER",
                "parts": [{"text": text}],
            }
        },
    }


def test_agent_card_advertises_a2a_v1() -> None:
    card = build_agent_card(BASE_URL)
    assert card.name == "Production Order Agent"
    assert card.supported_interfaces[0].protocol_version == "1.0"
    assert card.capabilities.streaming is False


def test_agent_card_route() -> None:
    with TestClient(create_app(BASE_URL, agent=FakeAgent())) as client:
        response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    assert response.json()["name"] == "Production Order Agent"


def test_send_message_returns_business_artifact() -> None:
    with TestClient(create_app(BASE_URL, agent=FakeAgent())) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json=_request(),
        )
    payload = response.json()
    assert response.status_code == 200
    assert "error" not in payload
    assert "Production-order result" in json.dumps(payload)


def test_backend_error_is_not_exposed() -> None:
    with TestClient(create_app(BASE_URL, agent=FailingAgent())) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json=_request(),
        )
    payload = response.json()
    serialized = json.dumps(payload)
    assert "could not be retrieved" in serialized
    assert "private-backend-diagnostic-marker" not in serialized
    assert payload["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
