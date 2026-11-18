"""Keep the test project bounded to the private chart's resource kinds."""

import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "references" / "gitops-production-order"


class TestProjectBounds(unittest.TestCase):
    def test_project_cannot_create_platform_resources_or_credential_objects(self):
        project = yaml.safe_load((ROOT / "project.yaml").read_text())
        spec = project["spec"]
        self.assertEqual(spec["clusterResourceWhitelist"], [])
        self.assertEqual(
            spec["namespaceResourceWhitelist"],
            [
                {"group": "apps", "kind": "Deployment"},
                {"group": "", "kind": "Service"},
            ],
        )
        self.assertEqual(len(spec["destinations"]), 1)
        self.assertNotIn("*", json.dumps(spec))
        self.assertEqual(len(spec["sourceRepos"]), 1)
        app = yaml.safe_load((ROOT / "application.yaml").read_text())["spec"]
        self.assertEqual(app["source"]["repoURL"], spec["sourceRepos"][0])
        self.assertEqual(app["destination"], spec["destinations"][0])
        self.assertEqual(app["project"], project["metadata"]["name"])

    def test_install_input_pins_an_immutable_upstream_manifest(self):
        lock = json.loads((ROOT / "argocd-install.json").read_text())
        self.assertRegex(lock["commit"], r"^[a-f0-9]{40}$")
        self.assertRegex(lock["sha256"], r"^[a-f0-9]{64}$")
        self.assertIn("/" + lock["commit"] + "/", lock["manifest_url"])
        self.assertTrue(lock["manifest_url"].endswith("/manifests/install.yaml"))


if __name__ == "__main__":
    unittest.main()
