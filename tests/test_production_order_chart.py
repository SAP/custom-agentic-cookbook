from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "production-order-agent"
DIGEST = "sha256:" + "a" * 64
IMAGE = "registry.example.com/team/production-order-agent:tested@" + DIGEST
IMAGE_VALUES = {
    "image.repository": "registry.example.com/team/production-order-agent",
    "image.tag": "tested",
    "image.digest": DIGEST,
}


def helm(command: str, **values: str) -> subprocess.CompletedProcess[str]:
    arguments = ["helm", command]
    if command == "template":
        arguments.append("recipe-test")
    arguments.extend([str(CHART), "--namespace", "recipe-test"])
    for name, value in {**IMAGE_VALUES, **values}.items():
        arguments.extend(["--set", f"{name}={value}"])
    return subprocess.run(arguments, capture_output=True, text=True, timeout=30)


def render(**values: str) -> list[dict]:
    result = helm("template", **values)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [document for document in yaml.safe_load_all(result.stdout) if document]


class ProductionOrderChartTests(unittest.TestCase):
    def test_chart_lints_with_an_immutable_image(self) -> None:
        result = helm("lint")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_chart_packages_both_processes_with_disjoint_services(self) -> None:
        documents = render()
        self.assertCountEqual(
            [item["kind"] for item in documents], ["Deployment"] * 2 + ["Service"] * 2
        )
        deployments = {
            item["metadata"]["labels"]["app.kubernetes.io/component"]: item
            for item in documents
            if item["kind"] == "Deployment"
        }
        services = {
            item["metadata"]["labels"]["app.kubernetes.io/component"]: item
            for item in documents
            if item["kind"] == "Service"
        }
        for component, deployment in deployments.items():
            with self.subTest(component=component):
                spec = deployment["spec"]
                self.assertEqual(spec["replicas"], 1)
                self.assertEqual(spec["strategy"], {"type": "Recreate"})
                pod = spec["template"]
                selector = spec["selector"]["matchLabels"]
                self.assertTrue(selector.items() <= pod["metadata"]["labels"].items())
                self.assertEqual(services[component]["spec"]["selector"], selector)
                self.assertEqual(services[component]["spec"]["type"], "ClusterIP")
                container = pod["spec"]["containers"][0]
                self.assertEqual(container["image"], IMAGE)
                module = (
                    "production_order_agent"
                    if component == "agent"
                    else "production_order_agent.mcp_server"
                )
                self.assertEqual(container["command"], ["python", "-m", module])
                port = 8000 if component == "agent" else 8090
                self.assertEqual(container["ports"][0]["containerPort"], port)
                self.assertEqual(services[component]["spec"]["ports"][0]["port"], port)
                environment = {item["name"]: item["value"] for item in container["env"]}
                self.assertEqual(environment["DATA_MODE"], "mock")
                self.assertEqual(environment["LLM_PROVIDER"], "mock")
                self.assertNotIn("envFrom", container)
                self.assertEqual(pod["spec"]["automountServiceAccountToken"], False)
                self.assertEqual(
                    pod["spec"]["securityContext"],
                    {
                        "runAsNonRoot": True,
                        "runAsUser": 10001,
                        "runAsGroup": 10001,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                )
                self.assertEqual(
                    container["securityContext"],
                    {
                        "allowPrivilegeEscalation": False,
                        "capabilities": {"drop": ["ALL"]},
                    },
                )
        self.assertNotEqual(
            services["agent"]["spec"]["selector"], services["mcp"]["spec"]["selector"]
        )
        agent = deployments["agent"]["spec"]["template"]["spec"]["containers"][0]
        environment = {item["name"]: item["value"] for item in agent["env"]}
        self.assertEqual(
            environment["MCP_SERVER_URL"],
            "http://recipe-test-production-order-agent-mcp.recipe-test.svc.cluster.local:8090/sse",
        )
        self.assertEqual(
            environment["URL"],
            "http://recipe-test-production-order-agent-agent.recipe-test.svc.cluster.local:8000",
        )
        for probe in ("readinessProbe", "livenessProbe"):
            self.assertEqual(
                agent[probe]["httpGet"], {"path": "/.well-known/agent-card.json", "port": "http"}
            )
        mcp = deployments["mcp"]["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(mcp["readinessProbe"]["tcpSocket"], {"port": "http"})

    def test_existing_pull_secret_names_are_references_only(self) -> None:
        documents = render(**{"imagePullSecrets[0]": "existing-registry"})
        self.assertNotIn("Secret", [item["kind"] for item in documents])
        for item in documents:
            if item["kind"] == "Deployment":
                self.assertEqual(
                    item["spec"]["template"]["spec"]["imagePullSecrets"],
                    [{"name": "existing-registry"}],
                )

    def test_explicit_development_apirule_exposes_only_the_agent(self) -> None:
        documents = render(
            **{
                "apirule.enabled": "true",
                "apirule.noAuth": "true",
                "apirule.host": "agent.example.com",
            }
        )
        rules = [item for item in documents if item["kind"] == "APIRule"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["apiVersion"], "gateway.kyma-project.io/v2")
        self.assertEqual(
            rules[0]["spec"]["service"],
            {
                "name": "recipe-test-production-order-agent-agent",
                "namespace": "recipe-test",
                "port": 8000,
            },
        )
        self.assertEqual(
            rules[0]["spec"]["rules"],
            [{"path": "/{**}", "methods": ["GET", "POST"], "noAuth": True}],
        )
        agent = next(
            item
            for item in documents
            if item["kind"] == "Deployment"
            and item["metadata"]["labels"]["app.kubernetes.io/component"] == "agent"
        )
        environment = {
            item["name"]: item["value"]
            for item in agent["spec"]["template"]["spec"]["containers"][0]["env"]
        }
        self.assertEqual(environment["URL"], "https://agent.example.com")
        self.assertIn("-mcp.recipe-test.svc.cluster.local:8090/sse", environment["MCP_SERVER_URL"])

    def test_invalid_image_replica_and_exposure_inputs_fail_before_deployment(self) -> None:
        cases = [
            {"image.repository": ""},
            {"image.tag": "latest"},
            {"image.digest": ""},
            {"image.digest": "sha256:bad"},
            {"replicaCount": "2"},
            {"apirule.enabled": "true", "apirule.noAuth": "true"},
            {"apirule.enabled": "true", "apirule.host": "agent.example.com"},
            {
                "apirule.enabled": "true",
                "apirule.noAuth": "true",
                "apirule.host": "https://agent.example.com",
            },
            {"credentials.apiKey": "unsupported"},
            {"imagePullSecrets[0]": ""},
        ]
        for values in cases:
            with self.subTest(values=values):
                result = helm("template", **values)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
