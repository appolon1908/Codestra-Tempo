from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ReadinessTests(unittest.TestCase):
    def test_release_build_inputs_match_publisher_and_locked_revision(self) -> None:
        from scripts import validate_repository_readiness as readiness
        manifest = json.loads((ROOT / "codestra/release/image-build.v1.json").read_text())
        lock = json.loads((ROOT / "codestra/release/runtime-base.lock.json").read_text())
        dockerfile = (ROOT / manifest["dockerfile"]).read_text()
        readiness.validate_build_inputs(manifest, lock, dockerfile)
        self.assertTrue(all(
            name.endswith("_IMAGE") and readiness.IMAGE.fullmatch(value)
            for name, value in manifest["buildArgs"].items()
        ))
        helper = (ROOT / "scripts/build_and_inspect_locked_image.sh").read_text()
        self.assertNotIn('--build-arg "TEMPO_SOURCE_REVISION=', helper)
        self.assertIn('grep -F "$revision"', helper)

    def test_non_image_release_argument_is_rejected(self) -> None:
        from scripts import validate_repository_readiness as readiness
        manifest = json.loads((ROOT / "codestra/release/image-build.v1.json").read_text())
        lock = json.loads((ROOT / "codestra/release/runtime-base.lock.json").read_text())
        manifest["buildArgs"]["TEMPO_SOURCE_REVISION"] = lock["sourceAuthorityCommit"]
        with self.assertRaisesRegex(SystemExit, "image build arguments mismatch"):
            readiness.validate_build_inputs(
                manifest, lock, (ROOT / manifest["dockerfile"]).read_text()
            )

    def test_missing_changed_or_overridden_source_default_is_rejected(self) -> None:
        from scripts import validate_repository_readiness as readiness
        manifest = json.loads((ROOT / "codestra/release/image-build.v1.json").read_text())
        lock = json.loads((ROOT / "codestra/release/runtime-base.lock.json").read_text())
        dockerfile = (ROOT / manifest["dockerfile"]).read_text()
        declaration = "ARG TEMPO_SOURCE_REVISION=" + lock["sourceAuthorityCommit"]
        variants = [
            dockerfile.replace(declaration, "ARG TEMPO_SOURCE_REVISION", 1),
            dockerfile.replace(declaration, "ARG TEMPO_SOURCE_REVISION=" + "0" * 40, 1),
            dockerfile.replace("ARG TEMPO_SOURCE_REVISION\n", "ARG TEMPO_SOURCE_REVISION=" + "0" * 40 + "\n"),
        ]
        for candidate in variants:
            with self.subTest(candidate=candidate[:150]):
                with self.assertRaisesRegex(SystemExit, "source revision default"):
                    readiness.validate_build_inputs(manifest, lock, candidate)

    def test_validator(self) -> None:
        subprocess.run(["python3", "scripts/validate_repository_readiness.py"], cwd=ROOT, check=True)

    def test_source_locks_agree(self) -> None:
        upstream = json.loads((ROOT / "CODESTRA_UPSTREAM_LOCK.json").read_text())
        lock = json.loads((ROOT / "codestra/release/runtime-base.lock.json").read_text())
        self.assertEqual(upstream["upstream_commit"], lock["sourceAuthorityCommit"])
        self.assertEqual(upstream["imported_tree_sha"], lock["sourceImportedTreeSha"])
        self.assertFalse(lock["runtimeBaseExecutableUsed"])

    def test_sanitization_policy_is_independent_from_lock_metadata(self) -> None:
        from scripts import validate_repository_readiness as readiness

        upstream = json.loads((ROOT / "CODESTRA_UPSTREAM_LOCK.json").read_text())
        upstream["sanitization"]["removed_paths"].append("cmd/tempo/main.go")
        with self.assertRaisesRegex(SystemExit, "independently approved policy"):
            readiness.verify_official_source(upstream)

    def test_imported_tree_matches_locked_git_tree(self) -> None:
        upstream = json.loads((ROOT / "CODESTRA_UPSTREAM_LOCK.json").read_text())
        imported_tree = subprocess.run(
            ["git", "rev-parse", "HEAD:upstream"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(upstream["imported_tree_sha"], imported_tree)

    def test_runtime_is_deploy_only_and_file_secret_bound(self) -> None:
        compose = yaml.safe_load((ROOT / "codestra/deploy/compose.candidate.yaml").read_text())
        service = compose["services"]["tempo"]
        self.assertNotIn("build", service)
        self.assertEqual(set(service["secrets"]), {"tempo_s3_credentials", "tempo_s3_ca"})
        self.assertTrue(all("file" in value for value in compose["secrets"].values()))

    def test_live_store_mount_target_is_initialized_for_runtime_user(self) -> None:
        dockerfile = (ROOT / "codestra/deploy/Dockerfile").read_text()
        self.assertIn("/out/rootfs/var/tempo/live-store", dockerfile)
        self.assertIn("/var/tempo/live-store/.codestra-volume-owner", dockerfile)

    def test_mutable_runtime_image_is_rejected(self) -> None:
        env = os.environ.copy()
        env.update({
            "CODESTRA_TEMPO_IMAGE": "ghcr.io/appolon1908-hue/codestra-tempo:latest",
            "CODESTRA_IMAGE_DIGEST": "sha256:" + "2" * 64,
        })
        result = subprocess.run(
            [
                "python3", "-c",
                "import scripts.validate_codestra_enterprise_profile as v; v.validate_runtime_image_environment()",
            ],
            cwd=ROOT, env=env, capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expanded CODESTRA_TEMPO_IMAGE", result.stderr + result.stdout)


if __name__ == "__main__": unittest.main()
