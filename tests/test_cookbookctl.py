from __future__ import annotations

import argparse
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
        source["account"]["client_secret"] = (
            "do-not-store-this"  # pragma: allowlist secret
        )

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
                            cookbookctl.command_render(
                                manifest, manifest_path, stdout=True
                            ),
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

    def test_render_rebuilds_malformed_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            state_dir.mkdir()
            manifest_path = root / "pilot.yaml"
            manifest_path.write_text(
                (ROOT / "pilot.yaml.example").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (state_dir / "state.json").write_text("[]\n", encoding="utf-8")
            manifest = cookbookctl.load_manifest(manifest_path)

            with (
                mock.patch.object(cookbookctl, "STATE_DIR", state_dir),
                mock.patch.object(cookbookctl, "STATE_FILE", state_dir / "state.json"),
                mock.patch.object(
                    cookbookctl,
                    "GENERATED_TFVARS",
                    state_dir / "generated.tfvars.json",
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    cookbookctl.command_render(manifest, manifest_path, stdout=False),
                    0,
                )

            rebuilt = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(rebuilt["version"], 1)
            self.assertEqual(rebuilt["stages"]["render"]["status"], "complete")


class AccountDiscoveryTests(unittest.TestCase):
    @staticmethod
    def probe(calls: list[tuple[str, ...]]):
        def fake(*arguments: str):
            calls.append(arguments)
            if arguments == ("get", "accounts/global-account"):
                return {
                    "displayName": "Example Global Account",
                    "subdomain": "example-global",
                }
            if arguments == ("list", "accounts/subaccount"):
                return {
                    "value": [
                        {
                            "guid": "00000000-0000-0000-0000-000000000001",
                            "displayName": "Existing Sandbox",
                            "subdomain": "existing-sandbox",
                            "region": "eu10",
                            "state": "OK",
                            "usedForProduction": "NOT_USED_FOR_PRODUCTION",
                        }
                    ]
                }
            raise AssertionError(f"unexpected BTP query: {arguments}")

        return fake

    def test_accounts_json_uses_only_read_only_global_account_queries(self) -> None:
        calls: list[tuple[str, ...]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                mock.patch.object(cookbookctl, "command_exists", return_value=True),
                mock.patch.object(
                    cookbookctl, "btp_json", side_effect=self.probe(calls)
                ),
                contextlib.redirect_stdout(io.StringIO()) as captured,
            ):
                code = cookbookctl.command_accounts(root / "pilot.yaml", as_json=True)

            report = json.loads(captured.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(
                calls,
                [
                    ("get", "accounts/global-account"),
                    ("list", "accounts/subaccount"),
                ],
            )
            self.assertTrue(report["logged_in"])
            self.assertEqual(report["global_account"]["subdomain"], "example-global")
            self.assertEqual(report["subaccounts"][0]["subdomain"], "existing-sandbox")
            self.assertFalse(report["manifest"]["exists"])
            self.assertFalse((root / ".cookbook").exists())

    def test_accounts_reports_existing_manifest_subdomain_without_adopting_it(
        self,
    ) -> None:
        calls: list[tuple[str, ...]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "pilot.yaml"
            manifest_path.write_text(
                "version: 1\n"
                "account:\n"
                "  global_account_subdomain: example-global\n"
                "  name: Example\n"
                "  subdomain: existing-sandbox\n"
                "  region: eu10\n",
                encoding="utf-8",
            )
            with (
                mock.patch.object(cookbookctl, "command_exists", return_value=True),
                mock.patch.object(
                    cookbookctl, "btp_json", side_effect=self.probe(calls)
                ),
                contextlib.redirect_stdout(io.StringIO()) as captured,
            ):
                self.assertEqual(
                    cookbookctl.command_accounts(manifest_path, as_json=True),
                    0,
                )

            report = json.loads(captured.getvalue())
            self.assertEqual(report["manifest"]["assessment"], "already-exists")
            self.assertEqual(
                report["manifest"]["existing_subaccount_guid"],
                "00000000-0000-0000-0000-000000000001",
            )
            self.assertTrue(
                any("does not select or adopt" in line for line in report["guidance"])
            )

    def test_accounts_json_reports_missing_session(self) -> None:
        with (
            mock.patch.object(cookbookctl, "command_exists", return_value=True),
            mock.patch.object(cookbookctl, "btp_json", return_value=None),
            contextlib.redirect_stdout(io.StringIO()) as captured,
        ):
            code = cookbookctl.command_accounts(
                Path("/nonexistent/pilot.yaml"), as_json=True
            )

        report = json.loads(captured.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(report["logged_in"])
        self.assertIn("btp login --sso", report["error"])


class LocalPilotLifecycleTests(unittest.TestCase):
    def state_patches(self, state_dir: Path):
        return (
            mock.patch.object(cookbookctl, "STATE_DIR", state_dir),
            mock.patch.object(cookbookctl, "STATE_FILE", state_dir / "state.json"),
            mock.patch.object(
                cookbookctl,
                "GENERATED_TFVARS",
                state_dir / "generated.tfvars.json",
            ),
        )

    @contextlib.contextmanager
    def patched_state(self, state_dir: Path):
        with contextlib.ExitStack() as stack:
            for patcher in self.state_patches(state_dir):
                stack.enter_context(patcher)
            yield

    def write_example_manifest(self, path: Path) -> None:
        path.write_text(
            (ROOT / "pilot.yaml.example").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    def test_park_and_unpark_roundtrip_moves_only_known_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            state_dir.mkdir()
            manifest_path = root / "pilot.yaml"
            self.write_example_manifest(manifest_path)
            (state_dir / "state.json").write_text('{"version": 1}\n', encoding="utf-8")
            (state_dir / "generated.tfvars.json").write_text("{}\n", encoding="utf-8")
            (state_dir / "notes.txt").write_text("leave me here\n", encoding="utf-8")

            with (
                self.patched_state(state_dir),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(cookbookctl.command_park(manifest_path), 0)
                archive = next((state_dir / "parked").iterdir())

            self.assertFalse(manifest_path.exists())
            self.assertFalse((state_dir / "state.json").exists())
            self.assertFalse((state_dir / "generated.tfvars.json").exists())
            self.assertTrue((state_dir / "notes.txt").is_file())
            self.assertTrue((archive / "pilot.yaml").is_file())
            self.assertTrue((archive / "state" / "state.json").is_file())
            self.assertTrue((archive / "state" / "generated.tfvars.json").is_file())

            with (
                self.patched_state(state_dir),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    cookbookctl.command_unpark(archive, manifest_path),
                    0,
                )

            self.assertTrue(manifest_path.is_file())
            self.assertTrue((state_dir / "state.json").is_file())
            self.assertTrue((state_dir / "generated.tfvars.json").is_file())
            self.assertTrue((state_dir / "notes.txt").is_file())
            self.assertFalse(archive.exists())

    def test_unpark_refuses_to_overwrite_an_active_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            manifest_path = root / "pilot.yaml"
            self.write_example_manifest(manifest_path)

            with (
                self.patched_state(state_dir),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                cookbookctl.command_park(manifest_path)
                archive = next((state_dir / "parked").iterdir())
            self.write_example_manifest(manifest_path)
            with (
                self.patched_state(state_dir),
                self.assertRaisesRegex(cookbookctl.CookbookError, "overwrite"),
            ):
                cookbookctl.command_unpark(archive, manifest_path)

            self.assertTrue((archive / "pilot.yaml").is_file())

    def test_unpark_rejects_an_archive_outside_the_managed_parked_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            outside = root / "outside-archive"
            outside.mkdir()
            (outside / "parked.json").write_text(
                '{"version": 1, "subdomain": "outside"}\n', encoding="utf-8"
            )
            self.write_example_manifest(outside / "pilot.yaml")

            with (
                self.patched_state(state_dir),
                self.assertRaisesRegex(
                    cookbookctl.CookbookError, "managed parked root"
                ),
            ):
                cookbookctl.command_unpark(outside, root / "pilot.yaml")

            self.assertTrue((outside / "pilot.yaml").is_file())

    def test_pilots_json_reports_matching_state_and_parked_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            state_dir.mkdir()
            manifest_path = root / "pilot.yaml"
            self.write_example_manifest(manifest_path)
            state = {
                "version": 1,
                "manifest_sha256": cookbookctl.manifest_digest(manifest_path),
                "stages": {"render": {"status": "complete"}},
            }
            (state_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
            archive = state_dir / "parked" / "old-pilot-20260907T000000Z"
            archive.mkdir(parents=True)
            (archive / "parked.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subdomain": "old-pilot",
                        "parked_at": "2026-09-07T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )

            with (
                self.patched_state(state_dir),
                contextlib.redirect_stdout(io.StringIO()) as captured,
            ):
                self.assertEqual(
                    cookbookctl.command_pilots(manifest_path, as_json=True),
                    0,
                )

            report = json.loads(captured.getvalue())
            self.assertTrue(report["active"]["state_matches_manifest"])
            self.assertEqual(report["active"]["stages"], {"render": "complete"})
            self.assertEqual(report["parked"][0]["subdomain"], "old-pilot")

    def test_status_is_read_only_in_a_fresh_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state_dir = root / ".cookbook"
            with (
                self.patched_state(state_dir),
                contextlib.redirect_stdout(io.StringIO()) as captured,
            ):
                self.assertEqual(
                    cookbookctl.command_status(root / "pilot.yaml", as_json=True),
                    0,
                )

            report = json.loads(captured.getvalue())
            self.assertFalse(report["manifest"]["exists"])
            self.assertFalse(report["state"]["exists"])
            self.assertFalse(state_dir.exists())

    def test_cli_exposes_only_the_approved_commands(self) -> None:
        coordinator_parser = cookbookctl.parser()
        subparsers = next(
            action
            for action in coordinator_parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )

        self.assertEqual(
            set(subparsers.choices),
            {"validate", "render", "accounts", "pilots", "park", "unpark", "status"},
        )


if __name__ == "__main__":
    unittest.main()
