"""Verify client-facing deployment metadata and the supported Compose architecture."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from hana_retrieval.__main__ import build_agent_card

SAMPLE = Path(__file__).parents[1]


@pytest.mark.skipif(shutil.which("helm") is None, reason="Helm is required for chart render checks")
@pytest.mark.parametrize(
    "release,namespace", [("first-release", "test-one"), ("other-release", "test-two")]
)
def test_private_chart_advertises_its_own_service_to_a2a_clients(release, namespace):
    result = subprocess.run(
        [
            "helm",
            "template",
            release,
            str(SAMPLE / "chart"),
            "--namespace",
            namespace,
            "--set",
            "image.repository=example.com/fixture",
            "--set",
            "image.digest=sha256:" + "0" * 64,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    objects = list(yaml.safe_load_all(result.stdout))
    deployment = next(obj for obj in objects if obj["kind"] == "Deployment")
    service = next(obj for obj in objects if obj["kind"] == "Service")
    agent = next(
        c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == "agent"
    )
    environment = {entry["name"]: entry["value"] for entry in agent["env"]}
    expected = f"http://{service['metadata']['name']}.{namespace}.svc.cluster.local:{service['spec']['ports'][0]['port']}"
    card = build_agent_card(environment.get("URL", "http://localhost:8000"))
    assert card.supported_interfaces[0].url == expected
    assert service["spec"]["type"] == "ClusterIP"


@pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker Compose is required for config checks"
)
def test_compose_selects_supported_amd64_even_on_an_arm64_host():
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            os.devnull,
            "config",
            "--format",
            "json",
        ],
        cwd=SAMPLE,
        env={**os.environ, "DOCKER_DEFAULT_PLATFORM": "linux/arm64"},
        capture_output=True,
        text=True,
        check=True,
    )
    services = json.loads(result.stdout)["services"]
    assert set(services) == {"agent", "mcp"}
    assert all(service.get("platform") == "linux/amd64" for service in services.values())
