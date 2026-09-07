from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cookbookctl", ROOT / "scripts" / "cookbookctl.py"
)
assert SPEC and SPEC.loader
cookbookctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cookbookctl)


class ManifestAndRenderTests(unittest.TestCase):
    def complete_manifest(self) -> dict[str, object]:
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
            "agent": {
                "name": "example-agent",
                "purpose": "Answer example questions.",
                "language": "typescript",
                "framework": "express",
                "taskstore": "memory",
                "llm_provider": "openai-compatible",
            },
            "joule": {"enabled": False},
        }

    def test_example_is_version_one_and_uses_a2a_v1_agent_card(self) -> None:
        manifest = cookbookctl.load_manifest(ROOT / "pilot.yaml.example")

        self.assertEqual(manifest["version"], 1)
        self.assertEqual(
            manifest["verification"]["agent_card_path"],
            "/.well-known/agent-card.json",
        )

    def test_material_architecture_choices_are_explicit(self) -> None:
        for section, key in (
            ("runtime", "target"),
            ("agent", "language"),
            ("agent", "framework"),
            ("agent", "taskstore"),
            ("agent", "llm_provider"),
        ):
            with self.subTest(choice=f"{section}.{key}"):
                source = json.loads(json.dumps(self.complete_manifest()))
                del source[section][key]
                with self.assertRaisesRegex(
                    cookbookctl.CookbookError,
                    "explicit|material architecture choices",
                ):
                    cookbookctl.normalize_manifest(source)

    def test_cloud_foundry_and_kyma_are_mutually_exclusive(self) -> None:
        source = self.complete_manifest()
        source["runtime"] = {
            "target": "kyma",
            "cloudfoundry": {"enabled": True},
            "kyma": {"plan": "aws", "region": "eu-central-1"},
        }

        with self.assertRaisesRegex(cookbookctl.CookbookError, "mutually exclusive"):
            cookbookctl.normalize_manifest(source)

    def test_manifest_rejects_embedded_credentials(self) -> None:
        source = self.complete_manifest()
        source["account"]["client_secret"] = "do-not-store-this"

        with self.assertRaisesRegex(cookbookctl.CookbookError, "credential-free"):
            cookbookctl.normalize_manifest(source)

    def test_validate_is_state_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "pilot.yaml"
            manifest_path.write_text(
                (ROOT / "pilot.yaml.example").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            manifest = cookbookctl.load_manifest(manifest_path)

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    cookbookctl.command_validate(manifest, manifest_path),
                    0,
                )

            self.assertFalse((root / ".cookbook").exists())

    def test_render_is_deterministic_and_records_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            manifest_path = root / "pilot.yaml"
            manifest_path.write_text(
                (ROOT / "pilot.yaml.example").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            manifest = cookbookctl.load_manifest(manifest_path)

            with (
                mock.patch.object(cookbookctl, "STATE_DIR", state_dir),
                mock.patch.object(cookbookctl, "STATE_FILE", state_dir / "state.json"),
                mock.patch.object(
                    cookbookctl,
                    "GENERATED_TFVARS",
                    state_dir / "generated.tfvars.json",
                ),
            ):
                outputs = []
                for _ in range(2):
                    with contextlib.redirect_stdout(io.StringIO()) as captured:
                        self.assertEqual(
                            cookbookctl.command_render(manifest, manifest_path, stdout=True),
                            0,
                        )
                    outputs.append(json.loads(captured.getvalue()))

                generated = json.loads(
                    (state_dir / "generated.tfvars.json").read_text(encoding="utf-8")
                )
                state_value = json.loads(
                    (state_dir / "state.json").read_text(encoding="utf-8")
                )

            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], generated)
            self.assertEqual(state_value["stages"]["render"]["status"], "complete")
            self.assertEqual(
                stat.S_IMODE((state_dir / "generated.tfvars.json").stat().st_mode),
                0o600,
            )


if __name__ == "__main__":
    unittest.main()
