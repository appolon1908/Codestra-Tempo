"""Tempo platform contract: TLS receivers, bounded attributes, propagation contract, OpenBao references."""
from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tempo_platform", ROOT / "scripts" / "validate_codestra_tempo_platform.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class TempoPlatformTests(unittest.TestCase):
    def test_validator_passes_offline(self) -> None:
        result = subprocess.run([sys.executable, "scripts/validate_codestra_tempo_platform.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TEMPO_RECEIVED_SPANS_LOGGED=NO", result.stdout)

    def test_receivers_terminate_tls_from_openbao_rendered_files(self) -> None:
        config = yaml.safe_load((ROOT / "codestra/config/tempo.yaml").read_text(encoding="utf-8"))
        for protocol in ("grpc", "http"):
            tls = config["distributor"]["receivers"]["otlp"]["protocols"][protocol]["tls"]
            self.assertTrue(tls["cert_file"].startswith("/run/secrets/"))
            self.assertEqual(str(tls["min_version"]), "1.2")
        references = json.loads((ROOT / "codestra/secret-references.v1.json").read_text(encoding="utf-8"))
        covered = {f for r in references["references"] for f in r["runtime_files"]}
        self.assertIn("/run/secrets/tempo_server_cert", covered)
        self.assertIn("/run/secrets/tempo_s3_credentials", covered)

    def test_propagation_contract_covers_the_test_syn_path(self) -> None:
        contract = json.loads((ROOT / "codestra/trace-propagation-contract.v1.json").read_text(encoding="utf-8"))
        self.assertEqual({h["component"] for h in contract["hops"]}, MODULE.REQUIRED_HOPS)
        self.assertEqual(contract["proof"]["campaign"], "TEST_SYN")
        self.assertIn("correlation.id", contract["requiredSpanAttributes"])
        self.assertFalse(set(contract["requiredSpanAttributes"]) & set(contract["forbiddenSpanAttributes"]))

    def test_value_bearing_reference_is_rejected(self) -> None:
        document = json.loads((ROOT / "codestra/secret-references.v1.json").read_text(encoding="utf-8"))
        poisoned = copy.deepcopy(document)
        poisoned["references"][0]["client_secret"] = "x"
        with self.assertRaises(SystemExit):
            MODULE.reject_secret_material(poisoned, "root")

    def test_public_ingest_port_is_rejected(self) -> None:
        compose = (ROOT / "codestra/deploy/compose.candidate.yaml").read_text(encoding="utf-8")
        original = MODULE.COMPOSE
        try:
            poisoned = ROOT / "codestra" / "deploy" / "_poisoned.yaml"
            poisoned.write_text(compose.replace('- "127.0.0.1:${TEMPO_QUERY_HOST_PORT:-3200}:3200"', '- "0.0.0.0:4317:4317"'), encoding="utf-8")
            MODULE.COMPOSE = poisoned
            with self.assertRaises(SystemExit):
                MODULE.validate_listeners()
        finally:
            MODULE.COMPOSE = original
            poisoned.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
