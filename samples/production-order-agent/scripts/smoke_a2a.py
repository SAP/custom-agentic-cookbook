"""Send a real A2A message and assert the sample's mock business result."""

from __future__ import annotations

import argparse
import json
from typing import Any
from uuid import uuid4

import httpx

EXPECTED = (
    "Production order 1000000",
    "Released",
    "Partially Confirmed",
    "0010",
    "0020",
    "Potential delay",
)


def business_reply(payload: dict[str, Any]) -> str:
    if "error" in payload:
        raise RuntimeError(f"JSON-RPC error {payload['error'].get('code', 'unknown')}")
    task = payload.get("result", {}).get("task", {})
    state = task.get("status", {}).get("state")
    if state != "TASK_STATE_COMPLETED":
        raise RuntimeError(f"expected a completed task, got {state}")
    text = "\n".join(
        part["text"]
        for artifact in task.get("artifacts", [])
        for part in artifact.get("parts", [])
        if isinstance(part.get("text"), str)
    )
    missing = [value for value in EXPECTED if value not in text]
    if missing:
        raise RuntimeError(f"business reply is missing {missing}")
    return text


def run(base_url: str) -> dict[str, Any]:
    with httpx.Client(timeout=30, trust_env=False) as client:
        card_response = client.get(f"{base_url.rstrip('/')}/.well-known/agent-card.json")
        card_response.raise_for_status()
        card = card_response.json()
        if card.get("name") != "Production Order Agent":
            raise RuntimeError("expected the Production Order Agent card")
        response = client.post(
            f"{base_url.rstrip('/')}/",
            headers={"A2A-Version": "1.0"},
            json={
                "jsonrpc": "2.0",
                "id": str(uuid4()),
                "method": "SendMessage",
                "params": {
                    "message": {
                        "messageId": str(uuid4()),
                        "role": "ROLE_USER",
                        "parts": [{"text": "Why is production order 1000000 delayed?"}],
                    }
                },
            },
        )
        response.raise_for_status()
    return {
        "agent": card["name"],
        "state": "TASK_STATE_COMPLETED",
        "reply": business_reply(response.json()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    print(json.dumps(run(args.base_url), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
