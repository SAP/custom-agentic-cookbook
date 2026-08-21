import json

from starlette.testclient import TestClient

from app.__main__ import build_agent_card, create_app

BASE_URL = "http://testserver"


def test_agent_card_advertises_only_a2a_v1_sync() -> None:
    card = build_agent_card(BASE_URL)

    assert card.name == "Hello World Agent"
    assert len(card.supported_interfaces) == 1
    assert card.supported_interfaces[0].protocol_version == "1.0"
    assert card.capabilities.streaming is False
    assert card.capabilities.push_notifications is False


def test_agent_card_route() -> None:
    with TestClient(create_app(BASE_URL)) as client:
        response = client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    assert response.json()["name"] == "Hello World Agent"


def test_send_message_returns_hello_world_artifact() -> None:
    request = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
            "message": {
                "messageId": "msg-1",
                "role": "ROLE_USER",
                "parts": [{"text": "hi"}],
            }
        },
    }

    with TestClient(create_app(BASE_URL)) as client:
        response = client.post(
            "/",
            headers={"A2A-Version": "1.0"},
            json=request,
        )

    payload = response.json()
    assert response.status_code == 200
    assert "error" not in payload
    assert "Hello, World!" in json.dumps(payload)
