"""Test an amd64 mock image through real HTTP and remove its exact resources."""

from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import time
from uuid import uuid4

import httpx
from smoke_a2a import business_reply
from smoke_joule import legacy_business_reply


def docker(*arguments: str, timeout: int = 90) -> str:
    result = subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode:
        raise RuntimeError(f"Docker {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def send(client: httpx.Client, base: str, *, legacy: bool = False) -> dict:
    message = {
        "messageId": str(uuid4()),
        "role": "user" if legacy else "ROLE_USER",
        "parts": [
            {"kind": "text", "text": "Why is production order 1000000 delayed?"}
            if legacy
            else {"text": "Why is production order 1000000 delayed?"}
        ],
    }
    response = client.post(
        base + "/",
        headers={} if legacy else {"A2A-Version": "1.0"},
        json={
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": "message/send" if legacy else "SendMessage",
            "params": {"message": message},
        },
    )
    response.raise_for_status()
    return response.json()


def run(image: str, mode: str) -> dict:
    if not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ValueError("--image must be the immutable local image ID from docker image inspect")
    metadata = json.loads(docker("image", "inspect", image))[0]
    if metadata["Architecture"] != "amd64" or metadata["Config"]["User"] != "10001:10001":
        raise RuntimeError("expected an amd64 image with USER 10001:10001")
    prefix = "cookbook-proof-" + uuid4().hex[:12]
    names: list[str] = []
    network = prefix + "-network"
    agent = prefix + "-agent"
    mcp = prefix + "-mcp"
    network_created = False
    results = {"image_id": image, "architecture": "amd64", "mode": mode}
    port = 0
    try:
        docker("network", "create", network)
        network_created = True
        common = (
            "--detach",
            "--platform",
            "linux/amd64",
            "--network",
            network,
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
        )
        if mode != "cf":
            names.append(mcp)
            docker(
                "run",
                *common,
                "--name",
                mcp,
                "--network-alias",
                "mcp",
                "--env",
                "DATA_MODE=mock",
                image,
                "python",
                "-m",
                "production_order_agent.mcp_server",
            )
        names.append(agent)
        command = ["python", "-m", "production_order_agent"]
        if mode == "joule":
            command.append("--joule-v03")
        if mode == "cf":
            command = ["python", "-m", "production_order_agent.cf_launcher"]
        docker(
            "run",
            *common,
            "--name",
            agent,
            "--publish",
            "127.0.0.1::8000",
            "--env",
            "DATA_MODE=mock",
            "--env",
            "LLM_PROVIDER=mock",
            "--env",
            "PORT=8000",
            "--env",
            "URL=http://127.0.0.1:8000",
            "--env",
            "MCP_SERVER_URL=http://mcp:8090/sse",
            image,
            *command,
        )
        port = int(docker("port", agent, "8000/tcp").rsplit(":", 1)[1])
        base = f"http://127.0.0.1:{port}"
        with httpx.Client(timeout=30, trust_env=False) as client:
            deadline = time.monotonic() + 90
            while True:
                try:
                    response = client.get(base + "/.well-known/agent-card.json")
                    response.raise_for_status()
                    results["reply"] = business_reply(send(client, base))
                    break
                except (httpx.HTTPError, RuntimeError):
                    if time.monotonic() >= deadline:
                        raise RuntimeError(
                            "container did not return the expected business reply"
                        ) from None
                    time.sleep(0.25)
            if mode == "joule":
                legacy_business_reply(send(client, base, legacy=True))
                results["v03_and_v1"] = True
            for name in names:
                controls = json.loads(
                    docker(
                        "exec",
                        name,
                        "python",
                        "-c",
                        "import json,os,pathlib; s=pathlib.Path('/proc/self/status').read_text(); "
                        "print(json.dumps({'uid':os.getuid(),'gid':os.getgid(),"
                        "'caps_zero':'CapEff:\t0000000000000000' in s,"
                        "'no_new_privs':'NoNewPrivs:\t1' in s,'seccomp':'Seccomp:\t2' in s}))",
                    )
                )
                if controls != {
                    "uid": 10001,
                    "gid": 10001,
                    "caps_zero": True,
                    "no_new_privs": True,
                    "seccomp": True,
                }:
                    raise RuntimeError("container process restrictions did not match")
            if mode != "cf":
                if json.loads(docker("inspect", mcp))[0]["HostConfig"]["PortBindings"]:
                    raise RuntimeError("MCP must have no published port")
                docker("stop", "--time", "15", mcp)
                failures = {}
                for legacy in (False, True) if mode == "joule" else (False,):
                    failed = send(client, base, legacy=legacy)
                    task = failed.get("result", {})
                    if not legacy:
                        task = task.get("task", {})
                    expected_state = "failed" if legacy else "TASK_STATE_FAILED"
                    if task.get("status", {}).get("state") != expected_state:
                        raise RuntimeError("backend loss did not return a failed A2A task")
                    artifacts = task.get("artifacts", [])
                    if len(artifacts) != 1 or artifacts[0].get("name") != "error":
                        raise RuntimeError("backend loss did not return only the error artifact")
                    if "The production-order data could not be retrieved." not in json.dumps(
                        artifacts
                    ):
                        raise RuntimeError("backend loss did not return the safe error message")
                    failures["0.3.0" if legacy else "1.0"] = True
                results["backend_failure_protocols"] = failures
                results["backend_failure"] = True
                results["safe_error_artifact"] = True
                docker("start", mcp)
                deadline = time.monotonic() + 30
                while True:
                    try:
                        for legacy in (False, True) if mode == "joule" else (False,):
                            payload = send(client, base, legacy=legacy)
                            restored = (
                                legacy_business_reply(payload)
                                if legacy
                                else business_reply(payload)
                            )
                            if restored != results["reply"]:
                                raise RuntimeError(
                                    "restored backend returned a different business reply"
                                )
                        results["restored_success"] = True
                        break
                    except (httpx.HTTPError, RuntimeError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError("restored backend did not recover") from None
                        time.sleep(0.25)
        docker("stop", "--time", "15", agent)
        if mode == "cf" and int(docker("inspect", "--format", "{{.State.ExitCode}}", agent)):
            raise RuntimeError("CF launcher did not stop gracefully")
        results["process_restrictions"] = True
    finally:
        for name in reversed(names):
            if docker("ps", "--all", "--quiet", "--filter", f"name=^{name}$"):
                docker("rm", "--force", name)
        if network_created:
            docker("network", "rm", network)
        for name in names:
            if docker("ps", "--all", "--quiet", "--filter", f"name=^{name}$"):
                raise RuntimeError("an exact test container remains")
        if port:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    raise RuntimeError("the published test port remains open")
    results["cleanup"] = True
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--mode", choices=["split", "joule"], default="split")
    args = parser.parse_args()
    print(json.dumps(run(args.image, args.mode), indent=2))


if __name__ == "__main__":
    main()
