"""Verify local model inference through the checked-in structured bridge and gateway."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import time
from pathlib import Path
from uuid import uuid4


def run(model_image: str, consumer_image: str) -> dict:
    scripts = Path(__file__).resolve().parent
    owner = "cookbook-gateway-bridge-" + uuid4().hex[:12]
    containers = []
    phases_passed = False
    report = {"scope": "local structured bridge and actual model", "phases": [], "passed": False}

    def docker(*args, check=True, timeout=40):
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True, check=check, timeout=timeout
        )

    def create(role, image, network, *command):
        name = owner + "-" + role
        args = [
            "create",
            "--name",
            name,
            "--label",
            "cookbook.validation=" + owner,
            "--network",
            network,
            "--platform",
            "linux/amd64",
            "--memory",
            "4g" if role == "model" else "1g",
            "--cpus",
            "4" if role == "model" else "2",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
        ]
        if command:
            args += [
                "--entrypoint",
                "python",
                "-e",
                "PYTHONDONTWRITEBYTECODE=1",
                "-v",
                str(scripts) + ":/validation:ro",
            ]
        docker(*args, image, *command)
        containers.append(name)
        info = json.loads(docker("inspect", name).stdout)[0]
        if info["Config"]["User"] != "10001:10001" or info["HostConfig"]["PortBindings"]:
            raise RuntimeError("Use the checked-in non-root images without published ports")
        return name

    def interrupted(*_):
        raise RuntimeError("Local smoke interrupted")

    previous_handlers = {
        sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    try:
        images = {
            key: json.loads(docker("image", "inspect", value).stdout)[0]["Id"]
            for key, value in (("model", model_image), ("consumer", consumer_image))
        }
        report["images"] = images
        model = create("model", images["model"], "none")
        docker("start", model)
        for _ in range(100):
            health = docker(
                "exec", model, "wget", "-qO-", "http://127.0.0.1:8080/health", check=False
            )
            if health.returncode == 0 and json.loads(health.stdout).get("status") == "ok":
                break
            time.sleep(0.3)
        else:
            raise RuntimeError("Owned model did not become ready")
        bridge = create(
            "bridge",
            images["consumer"],
            "container:" + model,
            "/validation/gateway_bridge_fixture.py",
        )
        docker("start", bridge)
        for _ in range(100):
            lines = docker("logs", bridge).stdout.splitlines()
            ready = [json.loads(line[6:]) for line in lines if line.startswith("READY ")]
            if ready:
                endpoints = ready[-1]
                break
            if docker("inspect", bridge, "--format", "{{.State.Running}}").stdout.strip() != "true":
                raise RuntimeError("Owned bridge exited during startup")
            time.sleep(0.15)
        else:
            raise RuntimeError("Owned bridge did not become ready")
        gateway = create(
            "gateway",
            images["consumer"],
            "container:" + model,
            "/validation/gateway_bridge_chain.py",
            "--fixture-url",
            endpoints["fixture_url"],
            "--bridge-url",
            endpoints["bridge_url"],
        )
        output = docker("start", "-a", gateway, check=False, timeout=240)
        state = json.loads(docker("inspect", gateway).stdout)[0]["State"]
        lines = output.stdout.splitlines()
        report["phases"] = [json.loads(line) for line in lines if line.startswith("{")]
        summaries = [json.loads(line[8:]) for line in lines if line.startswith("SUMMARY ")]
        report["gateway_cleanup"] = summaries[-1] if summaries else None
        if output.returncode or state["ExitCode"] or len(report["phases"]) != 8:
            report["fixture_diagnostic"] = output.stderr
            raise RuntimeError("Gateway bridge business, refusal or recovery check failed")
        phases_passed = True
    finally:
        report["owned_containers_absent"] = True
        for name in reversed(containers):
            info = json.loads(docker("inspect", name).stdout)[0]
            if info["Config"]["Labels"].get("cookbook.validation") != owner:
                raise RuntimeError("Owned-container label changed; refusing cleanup")
            docker("stop", "--time", "15", name, check=False)
            if name.endswith("-bridge"):
                summaries = [
                    json.loads(line[8:])
                    for line in docker("logs", name).stdout.splitlines()
                    if line.startswith("CLEANUP ")
                ]
                report["bridge_cleanup"] = summaries[-1] if summaries else None
            docker("rm", name)
            report["owned_containers_absent"] &= (
                docker("inspect", name, check=False).returncode != 0
            )
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        report["passed"] = (
            phases_passed
            and report["owned_containers_absent"]
            and report.get("bridge_cleanup")
            == {"bridge_reaped": True, "fixture_and_bridge_ports_closed": True}
        )
        print(json.dumps(report, indent=2), flush=True)
    if not report["passed"]:
        raise RuntimeError("Owned helper cleanup did not pass")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-image", required=True, help="Locally built pinned Qwen image")
    parser.add_argument(
        "--consumer-image", required=True, help="Locally built core model-consumer image"
    )
    args = parser.parse_args()
    run(args.model_image, args.consumer_image)
