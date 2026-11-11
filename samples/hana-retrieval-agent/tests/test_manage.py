"""Test exact object proof and safe cleanup without contacting HANA or AI Core."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hana_retrieval import manage
from hana_retrieval.repository import RetrievalError


class Cursor:
    def __init__(self, *, fail_operation=False, fail_close=False, count=0):
        self.fail_operation = fail_operation
        self.fail_close = fail_close
        self.count = count
        self.closed = False

    def execute(self, *_):
        if self.fail_operation:
            raise RuntimeError("private driver endpoint credential-canary")

    def fetchone(self):
        return (self.count,)

    def callproc(self, _, args):
        self.execute()
        return (
            args[0],
            args[1],
            json.dumps({"results": {"bindings": [{"n": {"value": str(self.count)}}]}}),
            None,
        )

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("private driver endpoint credential-canary")


class Connection:
    def __init__(self, cursor, fail_close=False):
        self.cur = cursor
        self.fail_close = fail_close
        self.closed = False

    def cursor(self):
        return self.cur

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("private driver endpoint credential-canary")


@pytest.mark.parametrize(
    "kind,target",
    [("vector", "COOKBOOK_TEST_VECTOR01"), ("graph", "urn:cookbook:graph:test-graph01")],
)
@pytest.mark.parametrize("failure", ["operation", "cursor-close", "connection-close"])
def test_driver_errors_are_safe_and_both_resources_close(
    monkeypatch, capsys, kind, target, failure
):
    cursor = Cursor(fail_operation=failure == "operation", fail_close=failure == "cursor-close")
    conn = Connection(cursor, fail_close=failure == "connection-close")
    monkeypatch.setattr(manage, "connect_hana", lambda: conn)
    with pytest.raises(RetrievalError) as error:
        manage.manage(kind, "cleanup", target)
    assert "credential-canary" not in str(error.value)
    assert error.value.__suppress_context__ is True
    assert conn.closed and cursor.closed
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "kind,target",
    [("vector", "COOKBOOK_TEST_VECTOR01"), ("graph", "urn:cookbook:graph:test-graph01")],
)
def test_remaining_objects_fail_without_success_output(monkeypatch, capsys, kind, target):
    conn = Connection(Cursor(count=1))
    monkeypatch.setattr(manage, "connect_hana", lambda: conn)
    with pytest.raises(RetrievalError):
        manage.manage(kind, "cleanup", target)
    assert conn.closed and conn.cur.closed
    assert capsys.readouterr().out == ""


def test_optimized_python_keeps_graph_cleanup_proof():
    script = """
import json
from hana_retrieval import manage
class Cursor:
    def callproc(self, name, args):
        body = json.dumps({'results': {'bindings': [{'n': {'value': '1'}}]}})
        return (args[0], args[1], body, None)
    def close(self): pass
class Connection:
    def cursor(self): return Cursor()
    def close(self): pass
manage.connect_hana = Connection
manage.manage('graph', 'cleanup', 'urn:cookbook:graph:test-graph01')
"""
    result = subprocess.run(
        [sys.executable, "-O", "-c", script],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "kind,action,target",
    [
        ("other", "cleanup", "x"),
        ("graph", "other", "urn:cookbook:graph:test-graph01"),
        ("vector", "cleanup", "OTHER_SCHEMA"),
        ("graph", "cleanup", "urn:unrelated:graph"),
    ],
)
def test_unreviewed_targets_or_actions_fail_before_connection(monkeypatch, kind, action, target):
    monkeypatch.setattr(manage, "connect_hana", lambda: pytest.fail("must not connect"))
    with pytest.raises(ValueError):
        manage.manage(kind, action, target)
