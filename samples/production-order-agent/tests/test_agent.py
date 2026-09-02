from __future__ import annotations

from typing import Any

import pytest

from production_order_agent.agent import (
    ProductionOrderAgent,
    deterministic_summary,
    extract_order_id,
)
from production_order_agent.settings import Settings


@pytest.mark.parametrize(
    "prompt",
    [
        "Why is my order delayed?",
        "Compare 1000000 with 1000001",
    ],
)
@pytest.mark.asyncio
async def test_missing_or_ambiguous_order_id_does_not_call_mcp(prompt: str) -> None:
    async def forbidden(*_: object) -> list[dict[str, Any]]:
        raise AssertionError("MCP must not be called without one unambiguous order ID")

    agent = ProductionOrderAgent(tool_caller=forbidden)
    assert await agent.invoke(prompt) == (
        "Please provide one unambiguous numeric manufacturing order ID."
    )


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Check operation 0020 for production order 1000000", "1000000"),
        ("Check operation 0020 for manufacturing order no. 1000000", "1000000"),
        ("Check 1000000", "1000000"),
        ("Compare 1000000 with 1000001", None),
        ("Compare production order 1000000 with production order 1000001", None),
    ],
)
def test_extract_order_id_prefers_one_labeled_order(
    prompt: str,
    expected: str | None,
) -> None:
    assert extract_order_id(prompt) == expected


@pytest.mark.asyncio
async def test_mock_agent_calls_both_tools_and_reports_delay() -> None:
    calls: list[tuple[str, str, str]] = []

    async def fake_tool(server_url: str, tool_name: str, order: str) -> list[dict[str, Any]]:
        calls.append((server_url, tool_name, order))
        if tool_name == "get_production_order_status":
            return [{"StatusCode": "I0002", "StatusName": "Released"}]
        return [
            {
                "ManufacturingOrderOperation": "0020",
                "MfgOrderOperationText": "Final assembly",
                "WorkCenter": "ASSEMBLY-02",
                "OpErlstSchedldExecEndDte": "2024-01-16",
                "OperationIsFinallyConfirmed": False,
            }
        ]

    settings = Settings(mcp_server_url="http://mcp.test/sse")
    agent = ProductionOrderAgent(settings, tool_caller=fake_tool)
    answer = await agent.invoke("Why is production order 1000000 delayed?")

    assert {call[1] for call in calls} == {
        "get_production_order_operations",
        "get_production_order_status",
    }
    assert all(call[2] == "1000000" for call in calls)
    assert "Production order 1000000" in answer
    assert "Potential delay: operation(s) 0020" in answer


@pytest.mark.asyncio
async def test_aicore_mode_summarizes_fetched_records() -> None:
    async def fake_tool(_: str, tool_name: str, __: str) -> list[dict[str, Any]]:
        return [{"source": tool_name}]

    seen: dict[str, Any] = {}

    async def fake_summarizer(
        model: str,
        order: str,
        statuses: list[dict[str, Any]],
        operations: list[dict[str, Any]],
    ) -> str:
        seen.update(
            model=model,
            order=order,
            statuses=statuses,
            operations=operations,
        )
        return "AI Core summary"

    agent = ProductionOrderAgent(
        Settings(llm_provider="aicore", model_name="model-from-environment"),
        tool_caller=fake_tool,
        summarizer=fake_summarizer,
    )
    assert await agent.invoke("Check 1000000") == "AI Core summary"
    assert seen["model"] == "model-from-environment"
    assert seen["statuses"] == [{"source": "get_production_order_status"}]
    assert seen["operations"] == [{"source": "get_production_order_operations"}]


def test_deterministic_summary_handles_no_records() -> None:
    answer = deterministic_summary("1000000", [], [])
    assert "No status records returned" in answer
    assert "No operation records returned" in answer
