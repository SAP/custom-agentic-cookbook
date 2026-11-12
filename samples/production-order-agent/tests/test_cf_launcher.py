"""Cloud Foundry supervisor tests with isolated loopback child processes."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path

import pytest

from production_order_agent import cf_launcher


@pytest.mark.parametrize("port", ["", "0", "65536", "8090", "-1", "1.5", " 8000", "٨٠٠٠"])
def test_rejects_invalid_cf_port(port: str) -> None:
    with pytest.raises(ValueError, match="PORT"):
        cf_launcher.child_environment({"PORT": port, "URL": "https://agent.example.com"})


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://agent.example.com",
        "https://user:secret@agent.example.com",
        "https://agent.example.com/path",
        "https://agent.example.com?key=secret",
        "https://agent.example.com#fragment",
        "https://agent.example.com:0",
        "https://agent.example.com:65536",
        "https://agent.example.com\\bad",
        "https://agent.example.com\n",
        "https://",
    ],
)
def test_rejects_unsafe_advertised_url(url: str) -> None:
    with pytest.raises(ValueError, match="URL"):
        cf_launcher.child_environment({"PORT": "8080", "URL": url})


@pytest.mark.parametrize("url", ["https://agent.example.com/", "http://127.0.0.1:8080"])
def test_enforces_mock_and_loopback_inputs(url: str) -> None:
    env = cf_launcher.child_environment(
        {
            "PORT": "8080",
            "URL": url,
            "HOST": "bad-host",
            "DATA_MODE": "s4",
            "LLM_PROVIDER": "aicore",
            "MCP_HOST": "bad-host",
            "MCP_PORT": "9000",
            "MCP_SERVER_URL": "https://tool.example.com",
            "MODEL_NAME": "live-model",
            "AICORE_CLIENT_SECRET": "test-secret",
            "MODEL_GATEWAY_API_KEY": "test-key",
            "S4_API_KEY": "test-key",
            "HANA_PASS": "test-secret",
            "VCAP_SERVICES": "test-bindings",
            "PATH": "/some/path",
        }
    )
    assert env["HOST"] == "0.0.0.0"
    assert env["PORT"] == "8080"
    assert env["URL"] == url.rstrip("/")
    assert env["DATA_MODE"] == env["LLM_PROVIDER"] == "mock"
    assert env["MCP_HOST"] == "127.0.0.1"
    assert env["MCP_PORT"] == "8090"
    assert env["MCP_SERVER_URL"] == "http://127.0.0.1:8090/sse"
    assert env["PATH"] == "/some/path"
    assert not any(key.startswith(("AICORE_", "MODEL_GATEWAY_", "S4_", "HANA_")) for key in env)
    assert "MODEL_NAME" not in env and "VCAP_SERVICES" not in env


CHILD = r"""import json, os, signal, socket, sys, time
from pathlib import Path
kind, mode, port, log = sys.argv[1:]
port = int(port)
def record(event):
    with Path(log).open("a") as out:
        out.write(json.dumps({"kind": kind, "event": event, "pid": os.getpid()}) + "\n")
def stop(signum, _frame):
    record("signal")
    raise SystemExit(0)
if mode == "ignore":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
else:
    signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
record("started")
if kind == "agent":
    assert os.environ["HOST"] == "0.0.0.0"
    assert os.environ["DATA_MODE"] == os.environ["LLM_PROVIDER"] == "mock"
    assert os.environ["MCP_SERVER_URL"] == f"http://127.0.0.1:{port}/sse"
    assert not any(k.startswith(("AICORE_", "MODEL_GATEWAY_", "S4_", "HANA_")) for k in os.environ)
    assert "VCAP_SERVICES" not in os.environ
if mode.startswith("exit-"):
    raise SystemExit(int(mode.split("-")[1]))
listener = None
if kind == "mcp" and mode != "never-ready":
    time.sleep(0.1)
    listener = socket.socket()
    listener.bind(("127.0.0.1", port))
    listener.listen()
record("ready")
if mode == "die-later":
    time.sleep(0.3)
    raise SystemExit(9)
while True:
    time.sleep(0.05)
"""


@pytest.fixture
def launch(tmp_path: Path):
    child = tmp_path / "child.py"
    child.write_text(CHILD)
    log = tmp_path / "events.jsonl"
    processes = []

    def start(mcp_mode: str = "stay", agent_mode: str = "stay"):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        runner = tmp_path / "runner.py"
        runner.write_text(
            "import subprocess, sys\n"
            "from production_order_agent import cf_launcher as launcher\n"
            f"launcher.MCP_PORT = {port}\n"
            "launcher.STARTUP_TIMEOUT = 0.8\n"
            "launcher.SHUTDOWN_TIMEOUT = 0.4\n"
            "original = subprocess.Popen\n"
            "def start(command, **kwargs):\n"
            "    kind = 'mcp' if command[-1].endswith('mcp_server') else 'agent'\n"
            f"    mode = {{'mcp': {mcp_mode!r}, 'agent': {agent_mode!r}}}[kind]\n"
            "    if mode == 'spawn-failure': raise OSError('fixture-private-error')\n"
            f"    return original([sys.executable, {str(child)!r}, kind, mode, {str(port)!r}, "
            f"{str(log)!r}], **kwargs)\n"
            "launcher.subprocess.Popen = start\n"
            "launcher.main()\n"
        )
        env = os.environ.copy()
        env.update(
            PORT="8080",
            URL="http://127.0.0.1:8080",
            DATA_MODE="s4",
            LLM_PROVIDER="aicore",
            AICORE_CLIENT_SECRET="fixture-secret",
            MODEL_GATEWAY_API_KEY="fixture-key",
            S4_API_KEY="fixture-key",
            HANA_PASS="fixture-secret",
            VCAP_SERVICES="fixture-bindings",
        )
        env["PYTHONPATH"] = str(Path(cf_launcher.__file__).resolve().parent.parent)
        proc = subprocess.Popen(
            [sys.executable, str(runner)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        processes.append(proc)
        return proc, log, port

    yield start
    for proc in processes:
        # Reclaim only this fixture's process group if a broken supervisor leaks children.
        with suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def events(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def wait_for_agent(proc: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if any(e["kind"] == "agent" and e["event"] == "ready" for e in events(log)):
            return
        if proc.poll() is not None:
            pytest.fail(f"supervisor exited before agent readiness: {proc.communicate()}")
        time.sleep(0.02)
    pytest.fail("fixture agent did not become ready")


def assert_reaped_and_port_closed(log: Path, port: int) -> None:
    for pid in {e["pid"] for e in events(log)}:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))


@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
def test_starts_mcp_before_agent_and_gracefully_reaps_both(launch, stop_signal) -> None:
    proc, log, port = launch()
    wait_for_agent(proc, log)
    timeline = [(e["kind"], e["event"]) for e in events(log)]
    assert timeline.index(("mcp", "ready")) < timeline.index(("agent", "started"))
    proc.send_signal(stop_signal)
    assert proc.wait(timeout=5) == 0
    assert {e["kind"] for e in events(log) if e["event"] == "signal"} == {"mcp", "agent"}
    assert_reaped_and_port_closed(log, port)


@pytest.mark.parametrize("exit_code", [0, 7])
def test_mcp_startup_exit_never_starts_agent(launch, exit_code: int) -> None:
    proc, log, port = launch(mcp_mode=f"exit-{exit_code}")
    assert proc.wait(timeout=5) == max(exit_code, 1)
    assert not any(e["kind"] == "agent" for e in events(log))
    assert_reaped_and_port_closed(log, port)


def test_mcp_readiness_timeout_cleans_up_without_starting_agent(launch) -> None:
    proc, log, port = launch(mcp_mode="never-ready")
    assert proc.wait(timeout=5) == 1
    assert not any(e["kind"] == "agent" for e in events(log))
    assert_reaped_and_port_closed(log, port)


@pytest.mark.parametrize("failed_child", ["mcp", "agent"])
def test_unexpected_child_exit_fails_and_stops_sibling(launch, failed_child: str) -> None:
    proc, log, port = launch(
        mcp_mode="die-later" if failed_child == "mcp" else "stay",
        agent_mode="die-later" if failed_child == "agent" else "stay",
    )
    wait_for_agent(proc, log)
    assert proc.wait(timeout=5) == 9
    assert_reaped_and_port_closed(log, port)


def test_forces_and_reaps_child_that_ignores_shutdown(launch) -> None:
    proc, log, port = launch(agent_mode="ignore")
    wait_for_agent(proc, log)
    proc.terminate()
    assert proc.wait(timeout=5) == 1
    assert_reaped_and_port_closed(log, port)


@pytest.mark.parametrize("mode", ["stay", "ignore"])
def test_shutdown_during_mcp_startup_never_starts_agent(launch, mode: str) -> None:
    proc, log, port = launch(mcp_mode="never-ready" if mode == "stay" else "ignore")
    deadline = time.monotonic() + 5
    while not any(e["kind"] == "mcp" and e["event"] == "started" for e in events(log)):
        assert proc.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.01)
    proc.terminate()
    assert proc.wait(timeout=5) == (0 if mode == "stay" else 1)
    assert not any(e["kind"] == "agent" for e in events(log))
    assert_reaped_and_port_closed(log, port)


def test_agent_spawn_failure_cleans_up_mcp_without_raw_error(launch) -> None:
    proc, log, port = launch(agent_mode="spawn-failure")
    assert proc.wait(timeout=5) == 1
    assert "fixture-private-error" not in "".join(proc.communicate())
    assert_reaped_and_port_closed(log, port)


def test_successful_agent_exit_is_still_an_unexpected_failure(launch) -> None:
    proc, log, port = launch(agent_mode="exit-0")
    assert proc.wait(timeout=5) == 1
    assert_reaped_and_port_closed(log, port)


def test_existing_mcp_listener_is_not_used_as_readiness() -> None:
    # The supervisor cannot start or adopt a service owned by another process.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        runner = (
            "from production_order_agent import cf_launcher as launcher; "
            f"launcher.MCP_PORT={port}; launcher.main()"
        )
        env = os.environ.copy()
        env.update(PORT="8080", URL="http://127.0.0.1:8080")
        env["PYTHONPATH"] = str(Path(cf_launcher.__file__).resolve().parent.parent)
        result = subprocess.run(
            [sys.executable, "-c", runner],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 1
        # Our unrelated listener survives the launcher failure.
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
