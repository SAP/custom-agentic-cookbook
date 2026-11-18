"""The optional A2A boundary returns completed or safe failed tasks."""

import json

from starlette.testclient import TestClient

from a2a_server import create_app


def request(text="revenue EMEA"):
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "SendMessage",
        "params": {
            "message": {"messageId": "test-message", "role": "ROLE_USER", "parts": [{"text": text}]}
        },
    }


class Agent:
    async def invoke(self, text):
        return '{"region":"EMEA","revenue":"20.00","source":"synthetic fixture"}'


class FailedAgent:
    async def invoke(self, text):
        raise RuntimeError("https://private.example/secret credential-marker")


def test_a2a_business_result_and_card():
    with TestClient(create_app("http://testserver", agent=Agent())) as client:
        card = client.get("/.well-known/agent-card.json").json()
        reply = client.post("/", headers={"A2A-Version": "1.0"}, json=request()).json()
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert reply["result"]["task"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert (
        json.loads(reply["result"]["task"]["artifacts"][0]["parts"][0]["text"])["revenue"]
        == "20.00"
    )


def test_a2a_backend_failure_is_safe_failed_task():
    with TestClient(create_app("http://testserver", agent=FailedAgent())) as client:
        reply = client.post("/", headers={"A2A-Version": "1.0"}, json=request()).json()
    assert reply["result"]["task"]["status"]["state"] == "TASK_STATE_FAILED"
    visible = json.dumps(reply)
    assert "could not be retrieved" in visible
    assert "private.example" not in visible and "credential-marker" not in visible


def test_agent_card_refuses_credential_bearing_advertised_url():
    import pytest

    with pytest.raises(ValueError) as error:
        create_app("http://user:private-secret@127.0.0.1:8001")
    assert "private-secret" not in str(error.value)
