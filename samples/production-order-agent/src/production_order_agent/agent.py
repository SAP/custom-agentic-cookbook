"""Business behavior for the production-order A2A agent."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import Any

from production_order_agent.mcp_client import call_mcp_tool
from production_order_agent.settings import Settings

ToolCaller = Callable[[str, str, str], Awaitable[list[dict[str, Any]]]]
Summarizer = Callable[
    [str, str, list[dict[str, Any]], list[dict[str, Any]]],
    Awaitable[str],
]

ORDER_ID = re.compile(r"(?<!\w)(\d{1,20})(?!\w)")
LABELED_ORDER_ID = re.compile(
    r"\b(?:(?:production|manufacturing)\s+)?order"
    r"(?:\s+(?:id|number|no\.?))?\s*(?:[:#-]\s*)?"
    r"(?<!\w)(\d{1,20})(?!\w)",
    re.IGNORECASE,
)


def extract_order_id(text: str) -> str | None:
    labeled_ids = {match.group(1) for match in LABELED_ORDER_ID.finditer(text)}
    if len(labeled_ids) == 1:
        return labeled_ids.pop()
    if labeled_ids:
        return None

    numeric_ids = {match.group(1) for match in ORDER_ID.finditer(text)}
    return numeric_ids.pop() if len(numeric_ids) == 1 else None


def _first(record: dict[str, Any], *keys: str, default: str = "unknown") -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def _is_confirmed(operation: dict[str, Any]) -> bool:
    value = _first(
        operation,
        "OperationIsFinallyConfirmed",
        "OperationIsConfirmed",
        default=False,
    )
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "x", "yes"}


def _as_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.startswith("/Date("):
        match = re.match(r"/Date\((\d+)", candidate)
        if match:
            return datetime.fromtimestamp(int(match.group(1)) / 1000, tz=UTC).date()
    try:
        return date.fromisoformat(candidate[:10])
    except ValueError:
        return None


def deterministic_summary(
    manufacturing_order: str,
    statuses: list[dict[str, Any]],
    operations: list[dict[str, Any]],
) -> str:
    lines = [f"Production order {manufacturing_order}", "", "Status"]
    if statuses:
        for status in statuses:
            name = _first(status, "StatusName", "StatusShortName", default="Unnamed status")
            code = _first(status, "StatusCode", default="")
            suffix = f" ({code})" if code else ""
            lines.append(f"- {name}{suffix}")
    else:
        lines.append("- No status records returned")

    lines.extend(["", "Scheduled operations"])
    overdue: list[str] = []
    if operations:
        for operation in operations:
            number = str(
                _first(
                    operation,
                    "ManufacturingOrderOperation",
                    "Operation",
                    default="unknown",
                )
            )
            text = _first(
                operation,
                "MfgOrderOperationText",
                "OperationText",
                default="No description",
            )
            work_center = _first(operation, "WorkCenter", default="unassigned")
            end = _first(
                operation,
                "OpErlstSchedldExecEndDte",
                "OperationScheduledEndDate",
                default="unknown",
            )
            state = "confirmed" if _is_confirmed(operation) else "not finally confirmed"
            lines.append(
                f"- {number}: {text}; work center {work_center}; scheduled end {end}; {state}"
            )
            parsed_end = _as_date(end)
            if (
                parsed_end is not None
                and parsed_end < date.today()
                and not _is_confirmed(operation)
            ):
                overdue.append(number)
    else:
        lines.append("- No operation records returned")

    lines.extend(["", "Delay assessment"])
    if overdue:
        lines.append(
            "- Potential delay: operation(s) "
            + ", ".join(overdue)
            + " passed their scheduled end date and are not finally confirmed."
        )
    else:
        lines.append("- No overdue, unconfirmed operation was identified in the returned records.")
    return "\n".join(lines)


async def summarize_with_aicore(
    model_name: str,
    manufacturing_order: str,
    statuses: list[dict[str, Any]],
    operations: list[dict[str, Any]],
) -> str:
    """Synthesize tool results through SAP AI Core using sap-ai-sdk-gen."""

    if not model_name:
        raise RuntimeError("MODEL_NAME is required when LLM_PROVIDER=aicore")
    try:
        from gen_ai_hub.proxy.native.openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "AI Core support is not installed; run 'uv sync --extra aicore'"
        ) from exc

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model=model_name,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a production-planning assistant. Summarize only the supplied "
                    "SAP S/4HANA records. Use Status, Scheduled operations, and Delay assessment "
                    "sections. Treat an operation as a potential delay only when its scheduled "
                    "end date is before today's date and it is not finally confirmed. State when "
                    "the records are insufficient; never invent causes or dates."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "today": date.today().isoformat(),
                        "manufacturing_order": manufacturing_order,
                        "statuses": statuses,
                        "operations": operations,
                    },
                    default=str,
                ),
            },
        ],
    )
    answer = response.choices[0].message.content
    if not answer or not answer.strip():
        raise RuntimeError("AI Core returned an empty response")
    return answer.strip()


class ProductionOrderAgent:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        tool_caller: ToolCaller = call_mcp_tool,
        summarizer: Summarizer = summarize_with_aicore,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.tool_caller = tool_caller
        self.summarizer = summarizer

    async def invoke(self, text: str) -> str:
        manufacturing_order = extract_order_id(text)
        if manufacturing_order is None:
            return "Please provide one unambiguous numeric manufacturing order ID."

        statuses, operations = await asyncio.gather(
            self.tool_caller(
                self.settings.mcp_server_url,
                "get_production_order_status",
                manufacturing_order,
            ),
            self.tool_caller(
                self.settings.mcp_server_url,
                "get_production_order_operations",
                manufacturing_order,
            ),
        )

        if self.settings.llm_provider == "mock":
            return deterministic_summary(manufacturing_order, statuses, operations)
        if self.settings.llm_provider == "aicore":
            return await self.summarizer(
                self.settings.model_name,
                manufacturing_order,
                statuses,
                operations,
            )
        raise RuntimeError("LLM_PROVIDER must be 'mock' or 'aicore'")
