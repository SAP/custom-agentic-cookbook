from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

import httpx
import pytest

SPEC = importlib.util.spec_from_file_location(
    "smoke_data", Path(__file__).resolve().parents[1] / "scripts" / "smoke_data.py"
)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

ORDER = "7654321"
STATUSES = [{"ManufacturingOrder": ORDER, "StatusCode": "I0001", "StatusName": "Created"}]
OPERATIONS = [{"ManufacturingOrder": ORDER, "ManufacturingOrderOperation": "0030"}]


@pytest.fixture
def backend(monkeypatch: pytest.MonkeyPatch) -> dict:
    expected = smoke.deterministic_summary(ORDER, STATUSES, OPERATIONS)
    data = {
        "statuses": STATUSES,
        "operations": OPERATIONS,
        "requests": [],
        "payload": {
            "result": {
                "task": {
                    "status": {"state": "TASK_STATE_COMPLETED"},
                    "artifacts": [{"parts": [{"text": expected}]}],
                }
            }
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        data["requests"].append(request)
        if request.url.host == "backend.example.invalid":
            field = "statuses" if "to_ProductionOrderStatus" in request.url.path else "operations"
            return httpx.Response(200, json={"d": {"results": data[field]}})
        assert request.headers["A2A-Version"] == "1.0"
        assert "APIKey" not in request.headers
        message = json.loads(request.content)["params"]["message"]
        assert message["parts"][0]["text"].endswith(f"order {ORDER}.")
        return httpx.Response(200, json=data["payload"])

    real_client = httpx.Client

    def client(*args, **kwargs) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(handler)
        kwargs["trust_env"] = False
        return real_client(*args, **kwargs)

    monkeypatch.setenv("S4_BASE_URL", "https://backend.example.invalid/service")
    monkeypatch.setenv("S4_API_KEY", "synthetic-key")
    monkeypatch.setattr(httpx, "Client", client)
    return data


def test_fresh_backend_comparison_passes(backend: dict) -> None:
    result = smoke.run("http://agent.example.invalid", ORDER)
    assert result == {
        "status_records": 1,
        "operation_records": 1,
        "state": "TASK_STATE_COMPLETED",
        "reply_matches_backend": True,
    }
    assert len(backend["requests"]) == 3


def test_different_reply_fails(backend: dict) -> None:
    backend["payload"]["result"]["task"]["artifacts"][0]["parts"][0]["text"] = "mock reply"
    with pytest.raises(RuntimeError, match="does not match"):
        smoke.run("http://agent.example.invalid", ORDER)


def test_reordered_status_operations_and_delays_pass(backend: dict) -> None:
    statuses = [*STATUSES, {"StatusCode": "I0002", "StatusName": "Released"}]
    operations = [
        {"ManufacturingOrderOperation": number, "OpErlstSchedldExecEndDte": "2000-01-01"}
        for number in ("0030", "0040")
    ]
    backend["statuses"] = statuses
    backend["operations"] = operations
    backend["payload"]["result"]["task"]["artifacts"][0]["parts"][0]["text"] = (
        smoke.deterministic_summary(ORDER, statuses[::-1], operations[::-1])
    )
    assert smoke.run("http://agent.example.invalid", ORDER)["reply_matches_backend"] is True


def test_duplicate_summary_line_fails(backend: dict) -> None:
    artifact = backend["payload"]["result"]["task"]["artifacts"][0]["parts"][0]
    artifact["text"] += "\n- Created (I0001)"
    with pytest.raises(RuntimeError, match="does not match"):
        smoke.run("http://agent.example.invalid", ORDER)


def test_http_success_with_failed_task_fails(backend: dict) -> None:
    backend["payload"]["result"]["task"]["status"]["state"] = "TASK_STATE_FAILED"
    with pytest.raises(RuntimeError, match="did not complete"):
        smoke.run("http://agent.example.invalid", ORDER)


@pytest.mark.parametrize("field", ["statuses", "operations"])
@pytest.mark.parametrize(
    "records",
    [[], [{}], [{"unrecognized": "value"}], [{"StatusCode": " ", "Operation": " "}]],
)
def test_unusable_records_fail_before_agent_request(
    backend: dict, field: str, records: list
) -> None:
    backend[field] = records
    with pytest.raises(RuntimeError, match="records"):
        smoke.run("http://agent.example.invalid", ORDER)
    assert len(backend["requests"]) == 2


@pytest.mark.parametrize("field", ["statuses", "operations"])
def test_different_order_identity_fails(backend: dict, field: str) -> None:
    backend[field] = [{"ManufacturingOrder": "9999999"}]
    with pytest.raises(RuntimeError, match="different production order"):
        smoke.run("http://agent.example.invalid", ORDER)


def test_builtin_mock_order_fails_before_network(backend: dict) -> None:
    with pytest.raises(RuntimeError, match="built-in mock"):
        smoke.run("http://agent.example.invalid", "1000000")
    assert backend["requests"] == []


def test_cli_error_hides_sensitive_exception_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def fail(*_) -> None:
        raise RuntimeError("synthetic-key https://backend.example.invalid/private-record")

    monkeypatch.setattr(smoke, "run", fail)
    monkeypatch.setattr(sys, "argv", ["smoke_data.py"])
    assert smoke.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "Data smoke failed (RuntimeError). Read the recipe troubleshooting steps.\n"
    )


def test_cli_hides_httpx_request_logs(
    backend: dict,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("httpx")
    monkeypatch.setattr(logger, "level", logger.level)
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(sys, "argv", ["smoke_data.py", "--order-id", ORDER])
    assert smoke.main() == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["reply_matches_backend"] is True
    assert captured.err == ""
    assert "backend.example.invalid" not in caplog.text
    assert "synthetic-key" not in caplog.text
