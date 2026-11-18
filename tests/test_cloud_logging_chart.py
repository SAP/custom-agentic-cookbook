from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "charts" / "optional-cloud-logging"
VALUES = {
    "enabled": True,
    "namespace": "cookbook-demo",
    "releaseName": "logging-demo",
    "ownershipConfirmed": True,
    "telemetryModuleVersion": "1.52.0",
    "backendSecret": {"name": "approved-logging"},
}


def render(
    values: dict | None = None,
    *,
    release="logging-demo",
    namespace="cookbook-demo",
    chart=CHART,
):
    with tempfile.TemporaryDirectory() as directory:
        command = [
            "helm",
            "template",
            release,
            str(chart),
            "--namespace",
            namespace,
        ]
        if values is not None:
            path = Path(directory) / "values.yaml"
            path.write_text(yaml.safe_dump(values))
            command.extend(["--values", str(path)])
        return subprocess.run(command, capture_output=True, text=True, check=False)


class CloudLoggingChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("helm"):
            raise RuntimeError("Helm is required to validate this integration chart")

    def test_disabled_chart_creates_no_objects(self):
        result = render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(yaml.safe_load_all(result.stdout)), [])

    def test_enabled_chart_is_only_three_scoped_pipelines(self):
        result = render(VALUES)
        self.assertEqual(result.returncode, 0, result.stderr)
        resources = list(yaml.safe_load_all(result.stdout))
        self.assertEqual(
            {resource["kind"] for resource in resources},
            {"LogPipeline", "MetricPipeline", "TracePipeline"},
        )
        self.assertEqual(len(resources), 3)
        for resource in resources:
            self.assertNotIn("namespace", resource["metadata"])
            self.assertNotIn("ownerReferences", resource["metadata"])
            annotations = resource["metadata"]["annotations"]
            self.assertEqual(annotations["meta.helm.sh/release-name"], "logging-demo")
            self.assertEqual(
                annotations["meta.helm.sh/release-namespace"], "cookbook-demo"
            )
            self.assertEqual(
                annotations["cookbook.sap.com/telemetry-scope"],
                "cb-cl-cookbook-demo-logging-demo-61fa640d",
            )
            spec = resource["spec"]
            output = spec["output"]["otlp"]
            for source in (
                output["endpoint"],
                output["tls"]["cert"],
                output["tls"]["key"],
            ):
                self.assertEqual(set(source), {"valueFrom"})
                reference = source["valueFrom"]["secretKeyRef"]
                self.assertEqual(reference["name"], "approved-logging")
                self.assertEqual(reference["namespace"], "cookbook-demo")
            if resource["kind"] != "TracePipeline":
                self.assertEqual(
                    spec["input"]["otlp"]["namespaces"]["include"], ["cookbook-demo"]
                )
                self.assertFalse(spec["input"]["runtime"]["enabled"])
            else:
                self.assertNotIn("input", spec)
            if resource["kind"] == "MetricPipeline":
                self.assertFalse(spec["input"]["istio"]["enabled"])
                self.assertFalse(spec["input"]["prometheus"]["enabled"])

    def test_scope_keys_survive_transform_before_filter(self):
        result = render(VALUES)
        self.assertEqual(result.returncode, 0, result.stderr)
        for resource in yaml.safe_load_all(result.stdout):
            transform = resource["spec"]["transform"][0]["statements"][0]
            self.assertEqual(
                transform,
                'keep_keys(resource.attributes, ["service.name", "k8s.namespace.name", "cookbook.telemetry.scope"])',
            )
            conditions = resource["spec"]["filter"][0]["conditions"]
            self.assertIn(
                'resource.attributes["service.name"] == nil or resource.attributes["service.name"] != "production-order-agent"',
                conditions,
            )
            self.assertIn(
                'resource.attributes["k8s.namespace.name"] == nil or resource.attributes["k8s.namespace.name"] != "cookbook-demo"',
                conditions,
            )
            self.assertIn(
                'resource.attributes["cookbook.telemetry.scope"] == nil or resource.attributes["cookbook.telemetry.scope"] != "cb-cl-cookbook-demo-logging-demo-61fa640d"',
                conditions,
            )

    def test_missing_inputs_and_unknown_or_secret_values_fail(self):
        cases = [
            {"enabled": True},
            {**VALUES, "namespace": ""},
            {**VALUES, "releaseName": ""},
            {**VALUES, "ownershipConfirmed": False},
            {**VALUES, "telemetryModuleVersion": "1.51.9"},
            {**VALUES, "telemetryModuleVersion": "not-a-version"},
            {**VALUES, "backendSecret": {"name": ""}},
            {
                **VALUES,
                "backendSecret": {
                    "name": "approved-logging",
                    "certificate": "forbidden-value",
                },
            },
            {**VALUES, "namespace": 'demo" or true'},
            {**VALUES, "collectAll": True},
        ]
        for values in cases:
            with self.subTest(values=values):
                self.assertNotEqual(render(values).returncode, 0)

    def test_system_namespaces_and_scope_mismatch_fail(self):
        for namespace in ["default", "kyma-system", "kube-system", "istio-system"]:
            with self.subTest(namespace=namespace):
                self.assertNotEqual(
                    render(
                        {**VALUES, "namespace": namespace}, namespace=namespace
                    ).returncode,
                    0,
                )
        self.assertNotEqual(render(VALUES, namespace="other-demo").returncode, 0)
        self.assertNotEqual(render(VALUES, release="other-release").returncode, 0)

    def test_names_are_bounded_and_distinguish_long_scopes(self):
        names = []
        for suffix in ["alpha", "beta"]:
            namespace = "n" * 50 + "-" + suffix
            release = "r" * 44 + "-" + suffix
            result = render(
                {**VALUES, "namespace": namespace, "releaseName": release},
                namespace=namespace,
                release=release,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            current = {
                resource["metadata"]["name"]
                for resource in yaml.safe_load_all(result.stdout)
            }
            self.assertTrue(all(len(name) <= 63 for name in current))
            names.append(current)
        self.assertFalse(names[0] & names[1])

    def test_ownership_conflict_helper_fails_without_adopting(self):
        # Evaluate the actual helper with synthetic lookup results. No cluster access.
        for owned in [False, True]:
            with self.subTest(owned=owned), tempfile.TemporaryDirectory() as directory:
                chart = Path(directory) / "chart"
                shutil.copytree(CHART, chart)
                (chart / "templates" / "pipelines.yaml").unlink()
                existing = {"metadata": {"labels": {}, "annotations": {}}}
                if owned:
                    existing["metadata"]["labels"] = {
                        "app.kubernetes.io/managed-by": "Helm",
                        "cookbook.sap.com/integration": "optional-cloud-logging",
                    }
                    existing["metadata"]["annotations"] = {
                        "meta.helm.sh/release-name": "logging-demo",
                        "meta.helm.sh/release-namespace": "cookbook-demo",
                    }
                fixture = json.dumps(existing)
                (chart / "templates" / "ownership.yaml").write_text(
                    "{{- $existing := fromJson `"
                    + fixture
                    + '` -}}\n{{- include "optional-cloud-logging.assertOwned" (dict "root" . "existing" $existing) -}}'
                )
                result = render(VALUES, chart=chart)
                self.assertEqual(result.returncode == 0, owned, result.stderr)


if __name__ == "__main__":
    unittest.main()
