"""Verify the experimental v0.3 mock path over real HTTP; no Joule tenant call."""

from __future__ import annotations

import argparse
import json
import time

import httpx
from smoke_a2a import business_reply


def legacy_business_reply(payload: dict) -> str:
    if "error" in payload:
        raise RuntimeError(f"JSON-RPC error {payload['error'].get('code', 'unknown')}")
    task = payload.get("result", {})
    if task.get("status", {}).get("state") != "completed":
        raise RuntimeError("v0.3 A2A task did not complete")
    artifacts = task.get("artifacts", [])
    if not artifacts or artifacts[0].get("name") != "production-order-summary":
        raise RuntimeError("v0.3 summary artifact is missing")
    parts = artifacts[0].get("parts", [])
    if not parts or parts[0].get("kind") != "text":
        raise RuntimeError("v0.3 text part is missing")
    return business_reply(
        {
            "result": {
                "task": {
                    "status": {"state": "TASK_STATE_COMPLETED"},
                    "artifacts": artifacts,
                }
            }
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
        card_response = client.get(base + "/.well-known/agent.json")
        card_response.raise_for_status()
        card = card_response.json()
        if card.get("protocolVersion") != "0.3.0":
            raise RuntimeError("enable --joule-v03 on the agent")
        started = time.monotonic()
        response = client.post(
            base + "/",
            json={
                "jsonrpc": "2.0",
                "id": "cookbook-joule-smoke",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": "cookbook-joule-smoke",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Why is order 1000000 delayed?"}],
                    }
                },
            },
        )
        response.raise_for_status()
        payload = response.json()
        legacy_business_reply(payload)
    print(
        json.dumps(
            {
                "protocol": "0.3.0",
                "state": "completed",
                "mock_status_and_operations_present": True,
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "scope": "HTTP mock proof only; no Joule action execution",
            }
        )
    )


if __name__ == "__main__":
    main()
