"""Compare an A2A reply with freshly read production-order backend records."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections import Counter
from uuid import uuid4

import httpx

from production_order_agent.agent import deterministic_summary
from production_order_agent.mcp_server import (
    DEFAULT_S4_BASE_URL,
    MOCK_ORDERS,
    S4Repository,
    validate_order_id,
)


def comparable_summary(text: str) -> Counter[str]:
    lines = []
    for line in text.splitlines():
        if line.startswith("- Potential delay: operation(s) "):
            match = re.fullmatch(
                r"(- Potential delay: operation\(s\) )(.+?)( passed their scheduled end date.*)",
                line,
            )
            if match:
                line = match[1] + ", ".join(sorted(match[2].split(", "))) + match[3]
        lines.append(line)
    return Counter(lines)


def run(base_url: str, manufacturing_order: str) -> dict[str, str | int | bool]:
    order = validate_order_id(manufacturing_order)
    if order in MOCK_ORDERS:
        raise RuntimeError("Choose an order absent from the built-in mock records")
    repository = S4Repository(
        os.getenv("S4_BASE_URL", DEFAULT_S4_BASE_URL),
        os.getenv("S4_API_KEY", ""),
    )
    statuses = repository.fetch(order, "to_ProductionOrderStatus")
    operations = repository.fetch(order, "to_ProductionOrderOperation")
    if not statuses or not operations:
        raise RuntimeError("The backend must return both status and operation records")
    if any(
        "ManufacturingOrder" in record
        and str(record["ManufacturingOrder"]).strip().lstrip("0") != order.lstrip("0")
        for record in [*statuses, *operations]
    ):
        raise RuntimeError("The backend records identify a different production order")
    if not any(
        any(
            str(record.get(key) or "").strip()
            for key in ("StatusCode", "StatusName", "StatusShortName")
        )
        for record in statuses
    ):
        raise RuntimeError("The backend returned no usable status records")
    if not any(
        any(
            str(record.get(key) or "").strip()
            for key in ("ManufacturingOrderOperation", "Operation")
        )
        for record in operations
    ):
        raise RuntimeError("The backend returned no usable operation records")
    expected = deterministic_summary(order, statuses, operations)
    with httpx.Client(timeout=30, trust_env=False) as client:
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
                        "parts": [{"text": f"Show the status and operations for order {order}."}],
                    }
                },
            },
        )
        response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError("The agent returned a JSON-RPC error")
    task = payload.get("result", {}).get("task", {})
    if task.get("status", {}).get("state") != "TASK_STATE_COMPLETED":
        raise RuntimeError("The agent task did not complete")
    reply = "\n".join(
        part["text"]
        for artifact in task.get("artifacts", [])
        for part in artifact.get("parts", [])
        if isinstance(part.get("text"), str)
    )
    if comparable_summary(reply) != comparable_summary(expected):
        raise RuntimeError("The agent reply does not match the backend records")
    return {
        "status_records": len(statuses),
        "operation_records": len(operations),
        "state": "TASK_STATE_COMPLETED",
        "reply_matches_backend": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--order-id", default="1000001")
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        result = run(args.base_url, args.order_id)
    except Exception as exc:
        print(
            f"Data smoke failed ({type(exc).__name__}). Read the recipe troubleshooting steps.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
