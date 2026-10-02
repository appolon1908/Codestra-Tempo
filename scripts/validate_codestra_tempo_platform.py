#!/usr/bin/env python3
"""Fail-closed validation of Tempo's place in the monitoring platform.

Tempo owns distributed traces on private, tenant-separated listeners. This
validator proves from source that the OTLP receivers terminate TLS with
OpenBao-rendered material, that received spans are never logged, that tenants
are business domains, that attribute sizes stay bounded, that the trace
propagation contract for the TEST_SYN path is complete and never lists a
forbidden attribute as required, that every secret file is an OpenBao
reference, and, with a Telemetry checkout, that the gateway exporter and the
receiver agree on TLS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CODESTRA = ROOT / "codestra"
CONFIG = CODESTRA / "config" / "tempo.yaml"
OVERRIDES = CODESTRA / "config" / "overrides.yaml"
COMPOSE = CODESTRA / "deploy" / "compose.candidate.yaml"
CONTRACT = CODESTRA / "trace-propagation-contract.v1.json"
SECRET_REFERENCES = CODESTRA / "secret-references.v1.json"
SECRET_SCHEMA = CODESTRA / "contracts" / "secret-reference.v1.schema.json"
SECRET_SCHEMA_PIN = CODESTRA / "contracts" / "secret-reference.v1.schema.sha256"

BUSINESS_TENANTS = {
    "platform", "codestra", "moneybee", "beyvra", "breero", "larim-a", "transportation", "booked4seasons",
    "social", "klyrow", "telnexa", "kyqra", "restaurant", "provisioning",
}
FORBIDDEN_REFERENCE_KEYS = {
    "value", "password", "token", "private_key", "client_secret", "secret",
    "secret_value", "unseal_key", "recovery_key", "root_token",
}
REQUIRED_HOPS = {"caddy", "kong", "middleware", "odoo", "n8n"}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        fail(f"invalid YAML {path.relative_to(ROOT)}: {exc}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def validate_receivers() -> dict[str, Any]:
    config = load_yaml(CONFIG)
    if config.get("multitenancy_enabled") is not True:
        fail("Tempo must keep multitenancy enabled")
    protocols = config.get("distributor", {}).get("receivers", {}).get("otlp", {}).get("protocols", {})
    for protocol in ("grpc", "http"):
        tls = protocols.get(protocol, {}).get("tls", {})
        if not str(tls.get("cert_file", "")).startswith("/run/secrets/") or not str(tls.get("key_file", "")).startswith("/run/secrets/"):
            fail(f"OTLP/{protocol} receiver must terminate TLS with OpenBao-rendered server material")
        if str(tls.get("min_version", "")) not in {"1.2", "1.3"}:
            fail(f"OTLP/{protocol} receiver must require TLS 1.2 or newer")
    logging = config.get("distributor", {})
    if logging.get("log_received_spans", {}).get("enabled") is not False or logging.get("log_discarded_spans", {}).get("enabled") is not False:
        fail("received and discarded spans must never be logged")
    server = config.get("server", {})
    if server.get("log_request_headers") is not False or server.get("trace_request_headers") is not False:
        fail("request headers must never be logged or traced")
    defaults = config.get("overrides", {}).get("defaults", {})
    if int(defaults.get("ingestion", {}).get("max_attribute_bytes", 0)) > 4096:
        fail("attribute size must stay bounded at 4096 bytes")
    if config.get("usage_report", {}).get("reporting_enabled") is not False:
        fail("usage reporting must stay disabled")
    return config


def validate_listeners() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    for match in re.finditer(r'^\s*-\s*"?([^"\n]+:\d+:\d+)"?\s*$', compose, flags=re.MULTILINE):
        binding = match.group(1)
        if not binding.startswith("127.0.0.1:"):
            fail(f"Tempo may publish host ports on loopback only, not {binding}")
        if binding.endswith((":4317", ":4318", ":9095", ":3101")):
            fail(f"native ingest, gRPC and internal listeners must not be published: {binding}")


def validate_tenants() -> None:
    overrides = load_yaml(OVERRIDES).get("overrides", {})
    unknown = set(overrides) - BUSINESS_TENANTS
    if unknown:
        fail(f"tenant overrides must be business domains, never customers: {sorted(unknown)}")
    for tenant, override in overrides.items():
        if int(override.get("ingestion", {}).get("max_attribute_bytes", 0)) > 4096:
            fail(f"tenant {tenant} raises the attribute bound above 4096 bytes")


def validate_contract() -> None:
    contract = load_json(CONTRACT)
    propagation = contract.get("propagation", {})
    if propagation.get("headers") != ["traceparent", "tracestate"] or propagation.get("correlationHeader") != "X-Correlation-ID":
        fail("propagation contract must carry W3C trace context and X-Correlation-ID")
    if propagation.get("correlationAttribute") != "correlation.id" or propagation.get("correlationBound", {}).get("maxLength") != 128:
        fail("correlation attribute contract drifted")
    required = set(contract.get("requiredSpanAttributes", []))
    forbidden = set(contract.get("forbiddenSpanAttributes", []))
    if required & forbidden:
        fail(f"an attribute cannot be both required and forbidden: {sorted(required & forbidden)}")
    for attribute in ("service.name", "deployment.id", "correlation.id", "codestra.business"):
        if attribute not in required:
            fail(f"required span attribute missing: {attribute}")
    for attribute in ("authorization", "cookie", "password", "x-openbao-token", "db.statement", "user_id", "tenant_id"):
        if attribute not in forbidden:
            fail(f"forbidden span attribute missing: {attribute}")
    hops = {hop.get("component") for hop in contract.get("hops", [])}
    if not REQUIRED_HOPS <= hops:
        fail(f"propagation hops missing: {sorted(REQUIRED_HOPS - hops)}")
    proof = contract.get("proof", {})
    if proof.get("campaign") != "TEST_SYN" or "correlation.id" not in str(proof.get("traceql")) or proof.get("runtimeEvidenceRequired") is not True:
        fail("TEST_SYN proof contract drifted")
    if contract.get("tenancy", {}).get("callerSuppliedTenantTrusted") is not False:
        fail("caller-supplied tenants must never be trusted")
    if contract.get("receiverSecurity", {}).get("tls") is not True or contract.get("receiverSecurity", {}).get("logReceivedSpans") is not False:
        fail("receiver security contract drifted")
    if contract.get("runtimeApplyAuthorized") is not False:
        fail("contract must not authorize runtime apply")


def reject_secret_material(value: Any, trail: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_REFERENCE_KEYS or str(key).lower().endswith(("_password", "_token", "_secret")):
                fail(f"secret reference carries a value-bearing key at {trail}.{key}")
            reject_secret_material(item, f"{trail}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            reject_secret_material(item, f"{trail}[{index}]")
    elif isinstance(value, str) and (value.startswith("hvs.") or ("PRIVATE " + "KEY") in value or re.fullmatch("AK" + "IA[0-9A-Z]{16}", value)):
        fail(f"secret-shaped value at {trail}")


def validate_secret_references() -> None:
    schema = load_json(SECRET_SCHEMA)
    pin = SECRET_SCHEMA_PIN.read_text(encoding="utf-8").strip()
    if hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest() != pin:
        fail("vendored secret-reference schema does not match its pin")
    document = load_json(SECRET_REFERENCES)
    if document.get("secretValuesIncluded") is not False or document.get("schemaSha256") != pin:
        fail("secret references must declare no values and bind the pinned schema")
    if document.get("authority", {}).get("workloadIdentity") != "tempo-runtime":
        fail("Tempo reads OpenBao only as the tempo-runtime identity")
    reject_secret_material(document, "secret-references")
    covered: set[str] = set()
    environments: set[str] = set()
    for index, reference in enumerate(document.get("references", [])):
        trail = f"references[{index}]"
        for required in schema["required"]:
            if required not in reference:
                fail(f"{trail} missing {required}")
        env = reference["environment"]
        ref = reference["secret_ref"]
        if reference["provider"] != "openbao" or reference["workload_identity"] != "tempo-runtime":
            fail(f"{trail} must be an openbao reference readable by tempo-runtime")
        if not ref.startswith(f"codestra/{env}/observability/tempo/"):
            fail(f"{trail} must lie beneath the tempo prefix for {env}")
        if reference.get("reference_uri") != "openbao://" + ref:
            fail(f"{trail} reference_uri must equal openbao:// + secret_ref")
        if reference["secret_class"] not in schema["properties"]["secret_class"]["enum"]:
            fail(f"{trail} has an unknown secret_class")
        environments.add(env)
        covered.update(reference.get("runtime_files", []))
    if environments != {"staging", "production"}:
        fail("secret references must cover exactly staging and production")
    for text in (CONFIG.read_text(encoding="utf-8"), COMPOSE.read_text(encoding="utf-8")):
        for path in sorted(set(re.findall(r"/run/secrets/tempo_[a-z0-9_]+", text))):
            if path not in covered:
                fail(f"Tempo secret file has no OpenBao reference: {path}")


def cross_check_gateway(telemetry_repo: Path) -> str:
    collector = load_yaml(telemetry_repo / "codestra" / "collector.yaml")
    exporter = collector.get("exporters", {}).get("otlp/tempo", {})
    tls = exporter.get("tls", {})
    if tls.get("insecure") is not False or not str(tls.get("ca_file", "")).startswith("/run/secrets/"):
        fail("the gateway Tempo exporter must verify TLS with a CA from /run/secrets")
    if "X-Scope-OrgID" not in exporter.get("headers", {}):
        fail("the gateway Tempo exporter must set the tenant header")
    processors = collector.get("processors", {})
    if "transform/correlation" not in processors:
        fail("the gateway must preserve correlation.id on spans")
    return "PASS"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--telemetry-repo")
    parser.add_argument("--require-cross-check", action="store_true")
    args = parser.parse_args()
    candidate = args.telemetry_repo or os.environ.get("TELEMETRY_REPO")
    repo = Path(candidate) if candidate else None
    if repo is None and args.require_cross_check:
        fail("Telemetry checkout is required for the gateway cross-check")
    validate_receivers()
    validate_listeners()
    validate_tenants()
    validate_contract()
    validate_secret_references()
    cross = cross_check_gateway(repo) if repo is not None else "SKIPPED_NO_TELEMETRY_CHECKOUT"
    print("Codestra Tempo platform validation PASS")
    print(f"TEMPO_GATEWAY_TLS_CROSS_CHECK={cross}")
    print("TEMPO_RECEIVED_SPANS_LOGGED=NO")
    print("TEMPO_SECRET_VALUES_IN_SOURCE=NONE")


if __name__ == "__main__":
    main()
