from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cookbookctl", ROOT / "scripts" / "cookbookctl.py"
)
assert SPEC and SPEC.loader
cookbookctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cookbookctl)

TEMPLATES = ROOT / "skills" / "sap-setup-btp-agent" / "templates"


def manifest_from_template(path: Path, **material: str) -> dict[str, object]:
    """Build a full pilot manifest from a starter template's ``agent`` block.

    The starter templates carry only the scenario-specific ``agent`` block
    (name, purpose, and the ``spec`` with mock tools and skills). The guided
    interview captures the four material architecture choices separately, so the
    test supplies them here and wraps everything with a fixed account/runtime/
    joule scaffold — mirroring the shape ``cookbookctl`` expects.
    """
    template = yaml.safe_load(path.read_text(encoding="utf-8"))
    agent = dict(template["agent"])
    agent.update(material)
    return {
        "version": 1,
        "account": {
            "global_account_subdomain": "example-global",
            "name": "Example Agent Pilot",
            "subdomain": "example-agent",
            "region": "eu10",
            "admins": ["developer@example.com"],
        },
        "runtime": {
            "target": "cf",
            "cloudfoundry": {"enabled": True, "spaces": {"dev": {"name": "dev"}}},
        },
        "agent": agent,
        "joule": {"enabled": False},
    }


class StarterTemplateTests(unittest.TestCase):
    def template_paths(self) -> list[Path]:
        return sorted(TEMPLATES.glob("*.yaml"))

    def test_every_starter_template_produces_a_valid_agent_specification(self) -> None:
        paths = self.template_paths()
        self.assertEqual(
            [p.name for p in paths],
            ["hr-leave.yaml", "inventory.yaml", "procurement.yaml", "sales-orders.yaml"],
        )

        for path in paths:
            with self.subTest(template=path.name):
                manifest = manifest_from_template(
                    path,
                    language="typescript",
                    framework="express",
                    taskstore="memory",
                    llm_provider="openai-compatible",
                )
                # normalize_manifest runs reject_embedded_credentials first, so a
                # clean return also proves the template carries no secrets.
                normalized = cookbookctl.normalize_manifest(manifest)

                agent = normalized["agent"]
                self.assertTrue(agent["name"])
                self.assertTrue(agent["purpose"])
                spec = agent["spec"]
                self.assertTrue(spec["tools"], "agent.spec.tools must survive")
                self.assertTrue(spec["skills"], "agent.spec.skills must survive")
                for tool in spec["tools"]:
                    self.assertEqual(tool["backend"], "mock")

    def test_starter_template_with_incompatible_stack_fails_with_actionable_error(
        self,
    ) -> None:
        sample = TEMPLATES / "procurement.yaml"

        with self.assertRaisesRegex(cookbookctl.CookbookError, "hana requires the CAP"):
            cookbookctl.normalize_manifest(
                manifest_from_template(
                    sample,
                    language="typescript",
                    framework="express",
                    taskstore="hana",
                    llm_provider="openai-compatible",
                )
            )

        with self.assertRaisesRegex(
            cookbookctl.CookbookError, "Python agents support only the express"
        ):
            cookbookctl.normalize_manifest(
                manifest_from_template(
                    sample,
                    language="python",
                    framework="cap",
                    taskstore="memory",
                    llm_provider="openai-compatible",
                )
            )


if __name__ == "__main__":
    unittest.main()
