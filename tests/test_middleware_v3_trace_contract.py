"""Middleware V3 trace contract: dark, pinned, W3C propagation, bounded span metrics."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_middleware_v3_trace_contract", ROOT / "scripts" / "validate_middleware_v3_trace_contract.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class TraceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(VALIDATOR.CONTRACT.read_text(encoding="utf-8"))
        cls.propagation = json.loads(VALIDATOR.PROPAGATION.read_text(encoding="utf-8"))
        cls.tempo = VALIDATOR.load_yaml(VALIDATOR.TEMPO)

    def test_source_passes(self) -> None:
        VALIDATOR.validate_contract(self.contract, self.propagation)
        VALIDATOR.validate_tempo(self.contract, self.tempo)

    def test_pins(self) -> None:
        self.assertEqual(self.contract["middleware"]["prep_base_sha"], "22d023a9c65b0789a0f7ee6c28548753521a9eff")
        self.assertEqual(self.contract["middleware"]["v3_final_sha"], "PENDING")
        self.assertEqual(self.contract["status"], "PREPARED_DISABLED")

    def test_ten_kernel_spans_in_order(self) -> None:
        self.assertEqual([s["stage"] for s in self.contract["v3_span_coverage"]], VALIDATOR.V3_STAGES)

    def test_contract_drift_is_rejected(self) -> None:
        for mutate in (
            lambda c: c.__setitem__("activation_enabled", True),
            lambda c: c["propagation"].__setitem__("headers", ["traceparent"]),
            lambda c: c["forbidden_span_attributes"].remove("db.statement"),
            lambda c: c["span_metrics_policy"]["dimensions_allowed"].append("correlation.id"),
            lambda c: c["v3_span_coverage"].pop(),
            lambda c: c["tempo_bounds"].__setitem__("public_exposure", True),
        ):
            mutated = copy.deepcopy(self.contract)
            mutate(mutated)
            with self.assertRaises(SystemExit):
                VALIDATOR.validate_contract(mutated, self.propagation)

    def test_tempo_drift_is_rejected(self) -> None:
        for mutate in (
            lambda t: t["distributor"]["receivers"]["otlp"]["protocols"]["grpc"]["tls"].__setitem__("min_version", "1.0"),
            lambda t: t["distributor"]["receivers"]["otlp"]["protocols"]["http"]["tls"].__setitem__("cert_file", "/etc/tempo/inline.pem"),
            lambda t: t["distributor"]["log_received_spans"].__setitem__("enabled", True),
            lambda t: t["metrics_generator"]["processor"]["span_metrics"]["dimensions"].append("codestra.operation.id"),
            lambda t: t["metrics_generator"]["processor"]["service_graphs"]["dimensions"].append("http.target"),
            lambda t: t["overrides"]["defaults"]["global"].__setitem__("max_bytes_per_trace", 50_000_000),
        ):
            mutated = copy.deepcopy(self.tempo)
            mutate(mutated)
            with self.assertRaises(SystemExit):
                VALIDATOR.validate_tempo(self.contract, mutated)


if __name__ == "__main__":
    unittest.main()
