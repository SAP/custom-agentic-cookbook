"""Run the mock agent and its private MCP service in one CF container."""

from __future__ import annotations

import ipaddress
import os
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
from urllib.parse import urlsplit

MCP_PORT = 8090
STARTUP_TIMEOUT = 30.0
SHUTDOWN_TIMEOUT = 10.0
POLL_INTERVAL = 0.05


def child_environment(source: dict[str, str]) -> dict[str, str]:
    port = source.get("PORT", "")
    if not port.isascii() or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("PORT must be an integer from 1 to 65535")
    if int(port) == MCP_PORT:
        raise ValueError("PORT must differ from the private MCP port")
    url = source.get("URL", "")
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        url_port = parsed.port
        loopback = hostname == "localhost"
        if hostname and not loopback:
            with suppress(ValueError):
                loopback = ipaddress.ip_address(hostname).is_loopback
        if (
            not hostname
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url)
            or "\\" in url
            or parsed.username is not None
            or parsed.password is not None
            or "?" in url
            or "#" in url
            or parsed.path not in ("", "/")
            or (url_port is not None and not 1 <= url_port <= 65535)
            or not (parsed.scheme == "https" or (parsed.scheme == "http" and loopback))
        ):
            raise ValueError
    except ValueError:
        raise ValueError("URL must be an explicit HTTPS origin or loopback HTTP origin") from None

    env = {
        key: value
        for key, value in source.items()
        if not key.startswith(("AICORE_", "MODEL_GATEWAY_", "S4_", "HANA_", "OPENAI_"))
        and key not in ("MODEL_NAME", "VCAP_SERVICES", "SERVICE_BINDING_ROOT")
    }
    env.update(
        HOST="0.0.0.0",
        PORT=port,
        URL=url.rstrip("/"),
        DATA_MODE="mock",
        LLM_PROVIDER="mock",
        MCP_HOST="127.0.0.1",
        MCP_PORT=str(MCP_PORT),
        MCP_SERVER_URL=f"http://127.0.0.1:{MCP_PORT}/sse",
    )
    return env


def stop_children(children: list[subprocess.Popen]) -> bool:
    """Stop and reap every child, returning whether shutdown was graceful."""
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + SHUTDOWN_TIMEOUT
    graceful = True
    for child in reversed(children):
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            graceful = False
            child.kill()
            child.wait()
    return graceful


def run() -> int:
    env = child_environment(os.environ.copy())
    children: list[subprocess.Popen] = []
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    handlers = {sig: signal.signal(sig, request_stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    result = 1
    try:
        # Reject an existing listener instead of treating another service as readiness.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", MCP_PORT))
        children.append(
            subprocess.Popen(
                [sys.executable, "-m", "production_order_agent.mcp_server"],
                env=env,
            )
        )
        mcp = children[0]
        deadline = time.monotonic() + STARTUP_TIMEOUT
        ready = False
        while not stopping and time.monotonic() < deadline:
            exit_code = mcp.poll()
            if exit_code is not None:
                result = exit_code if exit_code > 0 else 1
                break
            try:
                with socket.create_connection(("127.0.0.1", MCP_PORT), timeout=0.1):
                    ready = True
                break
            except OSError:
                time.sleep(POLL_INTERVAL)
        if stopping:
            result = 0
        elif ready and mcp.poll() is None:
            children.append(
                subprocess.Popen(
                    [sys.executable, "-m", "production_order_agent"],
                    env=env,
                )
            )
            while not stopping:
                for child in children:
                    exit_code = child.poll()
                    if exit_code is not None:
                        result = exit_code if exit_code > 0 else 1
                        break
                else:
                    time.sleep(POLL_INTERVAL)
                    continue
                break
            if stopping:
                result = 0
    finally:
        if not stop_children(children):
            result = 1
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    return result


def main() -> None:
    try:
        result = run()
    except (ValueError, OSError):
        print(
            "CF mock launcher could not start; check URL, PORT, and local processes.",
            file=sys.stderr,
        )
        result = 1
    raise SystemExit(result)


if __name__ == "__main__":
    main()
