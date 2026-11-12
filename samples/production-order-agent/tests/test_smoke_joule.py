"""Reject incomplete or failed legacy replies without exposing diagnostics."""

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("smoke_joule", SCRIPTS / "smoke_joule.py")
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_legacy_smoke_rejects_the_previously_unchecked_missing_status():
    payload = {
        "result": {
            "status": {"state": "completed"},
            "artifacts": [
                {
                    "name": "production-order-summary",
                    "parts": [
                        {
                            "kind": "text",
                            "text": (
                                "Production order 1000000 Released 0010 "
                                "Final assembly 0020 Potential delay"
                            ),
                        }
                    ],
                }
            ],
        }
    }
    with pytest.raises(RuntimeError, match="Partially Confirmed"):
        smoke.legacy_business_reply(payload)


def test_legacy_smoke_redacts_protocol_errors():
    with pytest.raises(RuntimeError, match="-32603") as error:
        smoke.legacy_business_reply({"error": {"code": -32603, "message": "private-marker"}})
    assert "private-marker" not in str(error.value)


def test_legacy_smoke_rejects_failed_tasks():
    with pytest.raises(RuntimeError, match="did not complete"):
        smoke.legacy_business_reply({"result": {"status": {"state": "failed"}}})
