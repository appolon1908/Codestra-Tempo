#!/usr/bin/env python3
"""Validate repository-only Tempo signed-image readiness."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE = re.compile(r"^[a-z0-9./_-]+@sha256:[0-9a-f]{64}$")
AUTHORITY = "ingtrader21-spec/Codestra-Telemetry/.github/workflows/reusable-release-image.yml@9a6aebb849bbc068105c10d9d1dfd39ebf6f78bd"
OFFICIAL_UPSTREAM = "https://github.com/grafana/tempo.git"
GIT_OBJECT = re.compile(r"^[0-9a-f]{40}$")
APPROVED_REMOVED_PATHS = (
    "opentelemetry-proto",
    "vendor/go.yaml.in/yaml/v4/CONTRIBUTING.md",
    "vendor/go.yaml.in/yaml/v4/README.md",
)
APPROVED_NORMALIZED_PATHS = (
    "example/nomad/tempo-distributed/README.md",
    "example/nomad/tempo-monolith/README.md",
    "example/nomad/tempo-monolith/tempo.hcl",
    "vendor/github.com/AzureAD/microsoft-authentication-library-for-go/LICENSE",
    "vendor/github.com/go-logfmt/logfmt/README.md",
    "vendor/github.com/klauspost/cpuid/v2/CONTRIBUTING.txt",
)
REQUIRED = (
    "README.md", "REPOSITORY_PROFILE.md", "SECURITY.md", ".github/CODEOWNERS",
    "docs/BACKUP_RESTORE_ROLLBACK.md", "docs/UPGRADE.md", ".dockerignore", ".gitleaks.toml",
    "codestra/release/image-build.v1.json", "codestra/release/runtime-base.lock.json",
    "codestra/source-image-contract.v1.json", ".github/workflows/release-image.yml",
    "scripts/build_and_inspect_locked_image.sh", "requirements-validation.txt",
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def load(relative: str) -> dict:
    value = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict): fail(f"{relative} must contain an object")
    return value


def verify_official_source(upstream: dict) -> None:
    """Verify official and sanitized trees from the fixed upstream."""
    commit = str(upstream.get("upstream_commit", ""))
    if not GIT_OBJECT.fullmatch(commit):
        fail("upstream_commit must be an exact 40-character Git object ID")
    if upstream.get("upstream_clone_url") != OFFICIAL_UPSTREAM:
        fail("upstream clone URL is not the fixed official Grafana Tempo repository")

    subprocess.run(
        ["git", "fetch", "--quiet", "--no-tags", "--depth=1", OFFICIAL_UPSTREAM, commit],
        cwd=ROOT,
        check=True,
    )
    official_tree = subprocess.run(
        ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=ROOT, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    if official_tree != upstream.get("official_tree_sha"):
        fail("official upstream tree differs from official_tree_sha")

    sanitization = upstream.get("sanitization", {})
    removed_paths = sanitization.get("removed_paths", [])
    normalized_paths = sanitization.get("normalized_line_endings", [])
    if tuple(removed_paths) != APPROVED_REMOVED_PATHS:
        fail("sanitization.removed_paths differs from the independently approved policy")
    if tuple(normalized_paths) != APPROVED_NORMALIZED_PATHS:
        fail("sanitization.normalized_line_endings differs from the independently approved policy")
    with tempfile.NamedTemporaryFile(prefix="codestra-tempo-index-") as index:
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = index.name
        subprocess.run(["git", "read-tree", official_tree], cwd=ROOT, env=env, check=True)
        subprocess.run(
            ["git", "update-index", "--force-remove", "--", *removed_paths],
            cwd=ROOT, env=env, check=True,
        )
        for path in normalized_paths:
            official_content = subprocess.run(
                ["git", "show", f"{commit}:{path}"], cwd=ROOT, check=True,
                capture_output=True,
            ).stdout
            normalized_content = official_content.replace(b"\r\n", b"\n")
            if normalized_content == official_content:
                fail(f"declared line-ending normalization has no effect: {path}")
            blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], cwd=ROOT, check=True,
                input=normalized_content, capture_output=True,
            ).stdout.decode().strip()
            subprocess.run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob},{path}"],
                cwd=ROOT, env=env, check=True,
            )
        sanitized_tree = subprocess.run(
            ["git", "write-tree"], cwd=ROOT, env=env, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    if sanitized_tree != upstream.get("imported_tree_sha"):
        fail("official upstream tree with declared sanitization differs from imported_tree_sha")


def main() -> None:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing: fail(f"missing readiness files: {missing}")
    if any(path.is_file() for path in (ROOT / "codestra/runtime-v1").glob("**/*")):
        fail("ambiguous legacy runtime-v1 authority remains")
    manifest = load("codestra/release/image-build.v1.json")
    lock = load("codestra/release/runtime-base.lock.json")
    upstream = load("CODESTRA_UPSTREAM_LOCK.json")
    verify_official_source(upstream)
    contract = load("codestra/source-image-contract.v1.json")
    if manifest.get("imageId") != "tempo" or manifest.get("context") != "." or manifest.get("productionActivation") is not False:
        fail("image manifest identity/context/activation mismatch")
    if lock.get("artifactModel") != "repository-built-signed-image" or lock.get("productionActivation") is not False:
        fail("runtime lock model/activation mismatch")
    for field in ("buildFrontendImage", "builderImage", "runtimeBaseImage"):
        if not IMAGE.fullmatch(str(lock.get(field, ""))): fail(f"mutable build input: {field}")
    expected_args = {"GO_BUILDER_IMAGE": lock["builderImage"], "TEMPO_BASE_IMAGE": lock["runtimeBaseImage"], "TEMPO_SOURCE_REVISION": lock["sourceAuthorityCommit"]}
    if manifest.get("buildArgs") != expected_args: fail("image build arguments mismatch")
    source_map = {"sourceAuthorityCommit": "upstream_commit", "sourceOfficialTreeSha": "official_tree_sha", "sourceImportedTreeSha": "imported_tree_sha"}
    for lock_key, upstream_key in source_map.items():
        if lock.get(lock_key) != upstream.get(upstream_key): fail(f"source tree mismatch: {lock_key}")
    imported_tree = subprocess.run(
        ["git", "rev-parse", "HEAD:upstream"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if imported_tree != upstream.get("imported_tree_sha"):
        fail("vendored upstream tree differs from imported_tree_sha")
    source_authority = contract.get("sourceAuthority", {})
    if source_authority.get("upstreamCommit") != lock["sourceAuthorityCommit"] or source_authority.get("importedTreeSha") != lock["sourceImportedTreeSha"]:
        fail("source image contract mismatch")
    if lock.get("runtimeBaseExecutableUsed") is not False: fail("runtime base executable may not be source authority")
    dockerfile = (ROOT / manifest["dockerfile"]).read_text(encoding="utf-8")
    if dockerfile.splitlines()[0] != f"# syntax={lock['buildFrontendImage']}": fail("Dockerfile frontend mismatch")
    for token in ("COPY upstream /src/upstream", "-o /out/tempo", "COPY --from=tempo-builder", 'ENTRYPOINT ["/tempo"]'):
        if token not in dockerfile: fail(f"source-built executable boundary missing: {token}")
    dockerignore = (ROOT / ".dockerignore").read_text()
    for token in ("upstream/docs", "upstream/integration", "upstream/**/*_test.go"):
        if token not in dockerignore: fail(f"upstream test fixture not excluded: {token}")
    compose = yaml.safe_load((ROOT / "codestra/deploy/compose.candidate.yaml").read_text())
    service = compose.get("services", {}).get("tempo", {})
    if "build" in service or service.get("privileged") is True or service.get("network_mode") == "host" or service.get("pid") == "host":
        fail("unsafe deployment candidate")
    if service.get("ports") != ["127.0.0.1:${TEMPO_QUERY_HOST_PORT:-3200}:3200"]:
        fail("Tempo may publish only its loopback query endpoint")
    if set(service.get("secrets", [])) != {"tempo_s3_credentials", "tempo_s3_ca"}:
        fail("secret-file mounts missing")
    if set(compose.get("secrets", {})) != {"tempo_s3_credentials", "tempo_s3_ca"} or any("file" not in item or "external" in item for item in compose["secrets"].values()):
        fail("top-level secrets must be mounted files")
    config = (ROOT / "codestra/config/tempo.yaml").read_text().lower()
    if "insecure: true" in config or re.search(r"(?m)^\s*(?:access_key|secret_key|session_token)\s*:", config):
        fail("unsafe object-store TLS or credential configuration")
    release = yaml.safe_load((ROOT / ".github/workflows/release-image.yml").read_text())
    job = release.get("jobs", {}).get("release", {})
    if job.get("uses") != AUTHORITY or job.get("with", {}).get("image_id") != "tempo": fail("release authority mismatch")
    build_call = 'bash scripts/build_and_inspect_locked_image.sh "$GITHUB_SHA"'
    for relative in (".github/workflows/validate-repository-readiness.yml", ".github/workflows/validate-repository-readiness-protected.yml"):
        if build_call not in (ROOT / relative).read_text(): fail(f"merge/protected image build missing: {relative}")
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        text = workflow.read_text()
        for reference in re.findall(r"(?m)^\s*(?:-\s*)?uses:\s*([^\s#]+)", text):
            if not reference.startswith("./") and not re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference): fail(f"mutable action: {workflow.name}: {reference}")
        if re.search(r"git push\s+origin\s+HEAD:(?:main|development|test|staging|production)", text): fail(f"direct protected-branch push: {workflow.name}")
    print("TEMPO_REPOSITORY_READINESS_SOURCE=PASS")
    print("ARTIFACT_MODEL=SIGNED_IMAGE")
    print("PRODUCTION_ACTIVATION=NO")


if __name__ == "__main__": main()
