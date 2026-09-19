#!/usr/bin/env python3
"""Fail-closed validation of the Middleware V3 trace contract against tempo.yaml.

``codestra/contracts/middleware-v3-trace-contract.v1.json`` fixes the trace path,
W3C propagation, the ten V3 kernel spans, the forbidden span attributes and the
bounded span-metric dimensions. This validator proves the contract is dark and
pinned, consistent with ``codestra/trace-propagation-contract.v1.json``, and that
``codestra/config/tempo.yaml`` matches it: TLS >= 1.2 on both OTLP receivers with
material from /run/secrets, no span logging, bounded trace size and metrics
generator dimensions drawn only from the allowed closed set. PyYAML only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CODESTRA = ROOT / "codestra"
CONTRACT = CODESTRA / "contracts" / "middleware-v3-trace-contract.v1.json"
PROPAGATION = CODESTRA / "trace-propagation-contract.v1.json"
TEMPO = CODESTRA / "config" / "tempo.yaml"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
V3_STAGES = ["http_ingress", "jwt_auth", "policy_engine", "safety_gate", "db_transaction", "outbox", "worker_lease", "adapter_execution", "provider_readback", "reconciliation"]
MISSION_FORBIDDEN = {"authorization", "cookie", "password", "api_key", "client_secret", "private_key", "db.statement", "user.email", "phone", "tenant_id", "customer_id", "command_payload", "secret_value"}


def fail(message: str) -> None:
    print(f"MIDDLEWARE_V3_TRACE_CONTRACT_ERROR={message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def load_yaml(path: Path) -> Any:
    import yaml

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"invalid YAML {path.relative_to(ROOT)}: {exc}")


def validate_contract(contract: dict[str, Any], propagation: dict[str, Any]) -> None:
    if contract.get("contract_id") != "middleware-v3-trace-contract" or contract.get("status") != "PREPARED_DISABLED":
        fail("contract identity or status drift")
    if contract.get("activation_enabled") is not False:
        fail("activation_enabled must be false")
    middleware = contract.get("middleware", {})
    if not SHA40.fullmatch(str(middleware.get("prep_base_sha", ""))):
        fail("middleware.prep_base_sha must be a 40-hex commit")
    if middleware.get("v3_final_sha") != "PENDING" and not SHA40.fullmatch(str(middleware.get("v3_final_sha"))):
        fail("middleware.v3_final_sha must be PENDING or a 40-hex commit")
    prop = contract.get("propagation", {})
    if prop.get("headers") != ["traceparent", "tracestate"] or prop.get("standard") != propagation["propagation"]["standard"]:
        fail("propagation must be W3C traceparent + tracestate")
    if prop.get("correlation_attribute") != "correlation.id" or prop.get("correlation_max_length") != propagation["propagation"]["correlationBound"]["maxLength"]:
        fail("correlation attribute drift from trace-propagation-contract.v1.json")
    stages = [span.get("stage") for span in contract.get("v3_span_coverage", [])]
    if stages != V3_STAGES:
        fail(f"span coverage must list exactly {V3_STAGES}")
    if any(span.get("status") != "EXPECTED_PENDING_V3" for span in contract["v3_span_coverage"]):
        fail("every V3 span is EXPECTED_PENDING_V3")
    forbidden = set(contract.get("forbidden_span_attributes", []))
    if not set(propagation["forbiddenSpanAttributes"]) <= forbidden:
        fail("the V3 contract must forbid everything the propagation contract forbids")
    if not MISSION_FORBIDDEN <= forbidden:
        fail(f"forbidden span attributes must include {sorted(MISSION_FORBIDDEN - forbidden)}")
    required = set(a.split(" ")[0] for a in contract.get("required_span_attributes", []))
    if not set(propagation["requiredSpanAttributes"]) <= required or "correlation.id" not in required:
        fail("required span attributes drift")
    if required & forbidden:
        fail("an attribute cannot be both required and forbidden")
    metrics = contract.get("span_metrics_policy", {})
    allowed = set(metrics.get("dimensions_allowed", []))
    never = {d.split(" ")[0] for d in metrics.get("dimensions_forbidden", [])}
    if allowed & never:
        fail("a span-metric dimension cannot be both allowed and forbidden")
    for name in ("correlation.id", "codestra.operation.id", "tenant_id", "customer_id", "db.statement"):
        if name not in never:
            fail(f"{name} must be a forbidden span-metric dimension")
    bounds = contract.get("tempo_bounds", {})
    if bounds.get("public_exposure") is not False or bounds.get("log_received_spans") is not False:
        fail("Tempo must stay private and must not log span content")


def validate_tempo(contract: dict[str, Any], tempo: dict[str, Any]) -> None:
    receivers = tempo.get("distributor", {}).get("receivers", {}).get("otlp", {}).get("protocols", {})
    for protocol in ("grpc", "http"):
        tls = receivers.get(protocol, {}).get("tls", {})
        if str(tls.get("min_version", "")) not in {"1.2", "1.3"}:
            fail(f"OTLP {protocol} receiver must require TLS >= 1.2")
        for key in ("cert_file", "key_file"):
            if not str(tls.get(key, "")).startswith("/run/secrets/"):
                fail(f"OTLP {protocol} receiver {key} must be a /run/secrets file")
    distributor = tempo.get("distributor", {})
    for key in ("log_received_spans", "log_discarded_spans"):
        if distributor.get(key, {}).get("enabled") is not False:
            fail(f"distributor.{key} must be disabled so span content never reaches logs")
    processor = tempo.get("metrics_generator", {}).get("processor", {})
    allowed = set(contract["span_metrics_policy"]["dimensions_allowed"])
    never = {d.split(" ")[0] for d in contract["span_metrics_policy"]["dimensions_forbidden"]}
    for name in ("service_graphs", "span_metrics"):
        dimensions = set(processor.get(name, {}).get("dimensions", [])) | set(processor.get(name, {}).get("peer_attributes", []))
        if dimensions - allowed:
            fail(f"{name} dimensions outside the allowed closed set: {sorted(dimensions - allowed)}")
        if dimensions & never:
            fail(f"{name} uses a forbidden dimension: {sorted(dimensions & never)}")
    if processor.get("span_metrics", {}).get("enable_instance_label") is not False:
        fail("span metrics must not carry an instance label")
    overrides = tempo.get("overrides", {}).get("defaults", {})
    max_bytes = overrides.get("global", {}).get("max_bytes_per_trace") or overrides.get("max_bytes_per_trace")
    if max_bytes != contract["tempo_bounds"]["max_bytes_per_trace"]:
        fail("max_bytes_per_trace differs between tempo.yaml and the contract")
    text = TEMPO.read_text(encoding="utf-8")
    if "insecure_skip_verify: true" in text or "insecure: true" in text:
        fail("tempo.yaml must never disable TLS verification")


def main() -> None:
    contract = load_json(CONTRACT)
    propagation = load_json(PROPAGATION)
    tempo = load_yaml(TEMPO)
    validate_contract(contract, propagation)
    validate_tempo(contract, tempo)
    print(
        "MIDDLEWARE_V3_TRACE_CONTRACT=PASS "
        f"prep_base={contract['middleware']['prep_base_sha'][:12]} v3_final={contract['middleware']['v3_final_sha']} "
        f"spans={len(contract['v3_span_coverage'])}"
    )


if __name__ == "__main__":
    main()
