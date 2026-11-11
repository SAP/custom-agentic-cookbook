from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "references" / "gitops-production-order"
SPEC = importlib.util.spec_from_file_location(
    "update_image", REFERENCE / "update_image.py"
)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)
OLD = "sha256:" + "a" * 64
NEW = "sha256:" + "b" * 64
REPOSITORY = "registry.example.com/team/production-order-agent"


class GitOpsValuesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "values with spaces.yaml"
        self.values = {
            "image": {
                "repository": REPOSITORY,
                "tag": "previous",
                "digest": OLD,
                "pullPolicy": "Always",
            },
            "imagePullSecrets": ["existing-pull-secret"],
            "replicaCount": 1,
            "apirule": {"enabled": False},
            "resources": {"agent": {"limits": {"memory": "768Mi"}}},
        }
        self.write(self.values)

    def write(self, values: dict) -> None:
        self.path.write_text(yaml.safe_dump(values, sort_keys=False))

    def update(self, **overrides) -> bool:
        arguments = {
            "repository": REPOSITORY,
            "tag": "next",
            "digest": NEW,
            "expected_current_digest": OLD,
        }
        arguments.update(overrides)
        return updater.update_image(self.path, **arguments)

    def test_update_preserves_unrelated_values_and_mode(self) -> None:
        self.path.chmod(0o640)
        self.assertTrue(self.update())
        result = yaml.safe_load(self.path.read_text())
        expected = {
            **self.values,
            "image": {**self.values["image"], "tag": "next", "digest": NEW},
        }
        self.assertEqual(result, expected)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*")), [])

    def test_noop_does_not_rewrite_file(self) -> None:
        before = self.path.stat()
        self.assertFalse(self.update(tag="previous", digest=OLD))
        after = self.path.stat()
        self.assertEqual(
            (before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns)
        )

    def test_unconfigured_example_accepts_only_explicit_empty_expected_digest(
        self,
    ) -> None:
        self.path.write_bytes((REFERENCE / "deployment-values.yaml").read_bytes())
        with self.assertRaises(updater.ValuesError):
            self.update()
        self.assertTrue(self.update(expected_current_digest=""))

    def test_invalid_or_stale_inputs_leave_original_bytes(self) -> None:
        cases = [
            {"repository": ""},
            {"repository": "https://bad image"},
            {"tag": "latest"},
            {"tag": ""},
            {"digest": "sha256:bad"},
            {"expected_current_digest": NEW},
            {"expected_current_digest": "invalid"},
            {"repository": True},
            {"tag": 123},
            {"digest": False},
            {"expected_current_digest": True},
        ]
        for case in cases:
            with self.subTest(case=case):
                original = self.path.read_bytes()
                with self.assertRaises(updater.ValuesError):
                    self.update(**case)
                self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_repository_references_fail_without_write(self) -> None:
        repositories = [
            "https://registry.example.com/team/image",
            "registry.example.com/team/image:old",
            "registry.example.com/team/image@" + NEW,
            "registry.example.com/team/../image",
            "registry.example.com/./image",
            "registry.example.com/team//image",
            "registry.example.com/team/",
            "/image",
            "Registry.example.com/team/image",
            "registry.example.com/team/Image",
            "registry.example.com:port/team/image",
            "registry_example.com/team/image",
            "registry..example.com/team/image",
            "-registry.example.com/team/image",
            "registry-.example.com/team/image",
            "registry.example.com:/team/image",
            "registry.example.com:0/team/image",
            "registry.example.com:65536/team/image",
            "registry.example.com:99999/team/image",
            "registry.example.com:-1/team/image",
            "registry.example.com:5000:6000/team/image",
            "a" * 64 + ".example.com/team/image",
            "a" * 256,
        ]
        original = self.path.read_bytes()
        for repository in repositories:
            with self.subTest(repository=repository):
                with self.assertRaises(updater.ValuesError):
                    self.update(repository=repository)
                self.assertEqual(self.path.read_bytes(), original)

    def test_registry_port_and_oci_path_separators_are_supported(self) -> None:
        repositories = [
            "registry.example.com:5000/team_name/image__name--suffix.v2",
            "localhost/team/image",
            "localhost:5000/team/image",
            "registry:5000/team/image",
            "registry.example.com:65535/team/image",
            "registry.example.com:0001/team/image",
            "registry--name.example.com/team/image",
            "team_name/image",
            "image_name.v2",
        ]
        for repository in repositories:
            with self.subTest(repository=repository):
                self.write(self.values)
                self.assertTrue(self.update(repository=repository))
                self.assertEqual(
                    yaml.safe_load(self.path.read_text())["image"]["repository"],
                    repository,
                )

    def test_tag_length_boundary_rejects_without_rewrite(self) -> None:
        original = self.path.read_bytes()
        with self.assertRaises(updater.ValuesError):
            self.update(tag="a" * 129)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.update(tag="a" * 128))

    def test_ambiguous_or_invalid_documents_fail_without_write(self) -> None:
        documents = [
            "image: {}\nimage: {}\n",
            "image: [a]\n",
            "image: {repository: a}\n",
            "image: {repository: a, tag: b, digest: 12}\n",
            "image: [\n",
            "image: {}\n---\nimage: {}\n",
            "image: {<<: {tag: old}}\n",
            "image: &image {repository: a, tag: b, digest: *image}\n",
        ]
        for document in documents:
            with self.subTest(document=document):
                self.path.write_text(document)
                with self.assertRaises(updater.ValuesError):
                    self.update()
                self.assertEqual(self.path.read_text(), document)

    def test_public_route_and_multiple_replicas_are_rejected(self) -> None:
        for field, value in [
            ("apirule", {"enabled": True}),
            ("replicaCount", 2),
            ("replicaCount", True),
        ]:
            with self.subTest(field=field):
                self.write({**self.values, field: value})
                before = self.path.read_bytes()
                with self.assertRaises(updater.ValuesError):
                    self.update()
                self.assertEqual(self.path.read_bytes(), before)

    def test_failed_atomic_replace_leaves_original_and_removes_temporary(self) -> None:
        before = self.path.read_bytes()
        with (
            mock.patch.object(
                updater.os, "replace", side_effect=OSError("simulated failure")
            ),
            self.assertRaises(OSError),
        ):
            self.update()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*")), [])

    def test_changed_file_before_replace_is_preserved(self) -> None:
        concurrent = yaml.safe_dump({**self.values, "replicaCount": 2})
        with (
            mock.patch.object(
                updater.os,
                "fsync",
                side_effect=lambda _: self.path.write_text(concurrent),
            ),
            self.assertRaisesRegex(updater.ValuesError, "changed during preparation"),
        ):
            self.update()
        self.assertEqual(self.path.read_text(), concurrent)
        self.assertEqual(list(self.path.parent.glob(f".{self.path.name}.*")), [])

    def test_symlink_target_is_rejected(self) -> None:
        link = self.path.parent / "link.yaml"
        link.symlink_to(self.path)
        with self.assertRaises(updater.ValuesError):
            updater.update_image(
                link,
                repository=REPOSITORY,
                tag="next",
                digest=NEW,
                expected_current_digest=OLD,
            )

    def test_git_revert_restores_previous_digest_and_all_values(self) -> None:
        def git(*arguments: str) -> str:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.path.parent,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env={
                    "PATH": os.environ["PATH"],
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.strip()

        def rendered_images() -> list[str]:
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    "production-order-gitops",
                    str(ROOT / "charts" / "production-order-agent"),
                    "--namespace",
                    "gitops-test",
                    "--values",
                    str(self.path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            documents = list(yaml.safe_load_all(result.stdout))
            self.assertCountEqual(
                [item["kind"] for item in documents],
                ["Deployment"] * 2 + ["Service"] * 2,
            )
            return [
                item["spec"]["template"]["spec"]["containers"][0]["image"]
                for item in documents
                if item["kind"] == "Deployment"
            ]

        git("init", "--quiet")
        git("config", "user.name", "GitOps Test")
        git("config", "user.email", "gitops-test@example.invalid")
        git("add", self.path.name)
        git("commit", "--quiet", "-m", "previous working image")
        previous_bytes = self.path.read_bytes()
        previous_images = rendered_images()
        self.assertEqual(previous_images, [f"{REPOSITORY}:previous@{OLD}"] * 2)
        self.update()
        self.assertEqual(rendered_images(), [f"{REPOSITORY}:next@{NEW}"] * 2)
        git("add", self.path.name)
        git("commit", "--quiet", "-m", "next tested image")
        git("revert", "--no-edit", "HEAD")
        self.assertEqual(self.path.read_bytes(), previous_bytes)
        self.assertEqual(yaml.safe_load(self.path.read_text()), self.values)
        self.assertEqual(rendered_images(), previous_images)


class ArgoExampleTests(unittest.TestCase):
    def test_inert_application_has_bounded_manual_sync_and_matching_release(
        self,
    ) -> None:
        application = yaml.safe_load((REFERENCE / "application.yaml").read_text())
        spec = application["spec"]
        self.assertEqual(
            application["metadata"]["name"], spec["source"]["helm"]["releaseName"]
        )
        self.assertNotIn("automated", spec["syncPolicy"])
        self.assertNotIn("finalizers", application["metadata"])
        self.assertEqual(
            spec["syncPolicy"]["syncOptions"],
            ["CreateNamespace=false", "FailOnSharedResource=true"],
        )
        self.assertIn("REPLACE_WITH_REVIEWED", spec["source"]["targetRevision"])
        source = ROOT / spec["source"]["path"]
        for values in spec["source"]["helm"]["valueFiles"]:
            self.assertEqual(
                (source / values).resolve(),
                (REFERENCE / "deployment-values.yaml").resolve(),
            )


if __name__ == "__main__":
    unittest.main()
