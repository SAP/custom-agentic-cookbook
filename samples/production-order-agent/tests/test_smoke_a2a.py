from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "smoke_a2a", Path(__file__).resolve().parents[1] / "scripts" / "smoke_a2a.py"
)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def completed_task(text: str) -> dict:
    return {
        "result": {
            "task": {
                "status": {"state": "TASK_STATE_COMPLETED"},
                "artifacts": [{"parts": [{"text": text}]}],
            }
        }
    }


def test_complete_mock_business_answer_passes() -> None:
    text = (
        "Production order 1000000\nReleased\nPartially Confirmed\n"
        "0010: Prepare components\n0020: Final assembly\nPotential delay"
    )
    assert smoke.business_reply(completed_task(text)) == text


def test_http_success_with_failed_task_is_not_business_success() -> None:
    payload = completed_task("Production order 1000000 Released Partially Confirmed 0010 0020")
    payload["result"]["task"]["status"]["state"] = "TASK_STATE_FAILED"
    with pytest.raises(RuntimeError, match="TASK_STATE_FAILED"):
        smoke.business_reply(payload)


def test_incomplete_business_records_do_not_pass() -> None:
    with pytest.raises(RuntimeError, match="missing.*0020"):
        smoke.business_reply(
            completed_task("Production order 1000000 Released Partially Confirmed 0010")
        )


def test_jsonrpc_error_is_reported_without_its_private_message() -> None:
    with pytest.raises(RuntimeError, match="JSON-RPC error -32603") as error:
        smoke.business_reply({"error": {"code": -32603, "message": "private-detail"}})
    assert "private-detail" not in str(error.value)


def test_agent_card_alone_is_not_a_business_reply() -> None:
    with pytest.raises(RuntimeError, match="completed task"):
        smoke.business_reply({"result": {"name": "Production Order Agent"}})


def test_status_and_operations_without_delay_assessment_do_not_pass() -> None:
    with pytest.raises(RuntimeError, match="missing.*Potential delay"):
        smoke.business_reply(
            completed_task("Production order 1000000 Released Partially Confirmed 0010 0020")
        )
