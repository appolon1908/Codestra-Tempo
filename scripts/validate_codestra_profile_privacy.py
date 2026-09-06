#!/usr/bin/env python3
"""Fail-closed privacy and credential-key validation for the Tempo profile."""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROFILE = ROOT / "codestra" / "enterprise-profile.v1.json"

REQUIRED_FEATURES = {
    "otlpGrpc",
    "otlpHttp",
    "traceSearch",
    "traceById",
    "businessTenantIsolation",
    "perBusinessRetentionAndLimits",
    "serviceGraphs",
    "spanMetrics",
    "prometheusExemplars",
    "grafanaMetricsLogsCorrelation",
    "s3BackedParquetStorage",
    "durableWal",
    "queryBudgets",
    "attributeSizeBudgets",
    "metricCardinalityBudgets",
    "privateEndpoints",
    "sourceNativeConfigValidation",
    "selfMonitoring",
}
PRIVACY_FLAGS = {
    "captureSecrets",
    "captureAuthorizationHeaders",
    "captureCookies",
    "captureRawPii",
    "captureRequestBodies",
    "captureResponseBodies",
    "captureDatabaseStatements",
    "captureBrokerSigningMaterial",
}
FORBIDDEN_CONTENT = {
    "authorization_headers",
    "cookies",
    "passwords",
    "api_keys",
    "private_keys",
    "session_tokens",
    "database_dsns",
    "raw_request_or_response_bodies",
    "broker_or_exchange_signing_material",
    "customer_financial_payloads",
}
SENSITIVE_KEY_TOKENS = {
    "password",
    "passwd",
    "authorization",
    "apikey",
    "clientsecret",
    "accesstoken",
    "refreshtoken",
    "sessiontoken",
    "privatekey",
    "roottoken",
    "databaseurl",
    "dsn",
    "brokersigningsecret",
    "brokersigningkey",
    "exchangeapikey",
    "exchangesecret",
}
PLACEHOLDER_RE = re.compile(
    r"^(?:INJECT_FROM_(?:OPENBAO|SECRET_FILE|DEPLOYMENT)|\[REDACTED\]|"
    r"\$\{[A-Z0-9_]+(?::[^}]*)?\})$"
)


def fail(message: str) -> None:
    print(f"TEMPO_PROFILE_PRIVACY_ERROR={message}", file=sys.stderr)
    raise SystemExit(1)


def normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_sensitive_key(key: str) -> bool:
    normalized = normalize_key(key)
    return any(token in normalized for token in SENSITIVE_KEY_TOKENS)


def find_credential_values(value: Any, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if is_sensitive_key(str(key)) and isinstance(child, str):
                stripped = child.strip()
                normalized = normalize_key(str(key))
                safe = (
                    not stripped
                    or PLACEHOLDER_RE.fullmatch(stripped) is not None
                    or (
                        normalized.endswith("file")
                        and stripped.startswith("/run/secrets/")
                    )
                )
                if not safe:
                    violations.append(child_path)
            violations.extend(find_credential_values(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(find_credential_values(child, f"{path}[{index}]"))
    return violations


def prove_scanner() -> None:
    unsafe = (
        {"api_key": "committed"},
        {"client_secret": "committed"},
        {"private_key": "committed"},
        {"root_token": "committed"},
        {"session-token": "committed"},
        {"brokerSigningKey": "committed"},
    )
    for sample in unsafe:
        if not find_credential_values(sample):
            fail(f"credential scanner failed negative test: {sample}")
    safe = (
        {"clientSecretFile": "/run/secrets/tempo_oidc_client_secret"},
        {"api_key": "INJECT_FROM_OPENBAO"},
        {"captureSecrets": False},
    )
    for sample in safe:
        if find_credential_values(sample):
            fail(f"credential scanner rejected safe control data: {sample}")


def main() -> None:
    prove_scanner()
    try:
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot parse profile: {exc}")

    if profile.get("exposure") != "internal_private":
        fail("Tempo exposure must remain exactly internal_private")

    features = profile.get("features")
    if not isinstance(features, dict):
        fail("features must be an object")
    missing_or_disabled = sorted(
        name for name in REQUIRED_FEATURES if features.get(name) is not True
    )
    if missing_or_disabled:
        fail(f"required features are missing or disabled: {missing_or_disabled}")
    unexpected_features = sorted(set(features) - REQUIRED_FEATURES)
    if unexpected_features:
        fail(f"unreviewed feature flags require contract update: {unexpected_features}")

    privacy = profile.get("privacy")
    if not isinstance(privacy, dict) or set(privacy) != PRIVACY_FLAGS:
        fail("privacy must define the exact corporate capture-control set")
    enabled = sorted(name for name, value in privacy.items() if value is not False)
    if enabled:
        fail(f"sensitive trace capture flags must remain false: {enabled}")

    redaction = profile.get("redaction")
    if not isinstance(redaction, dict):
        fail("redaction policy must be an object")
    if redaction.get("requiredBeforeIngestion") is not True:
        fail("redaction must be required before Tempo ingestion")
    if redaction.get("authorities") != ["opentelemetry", "alloy"]:
        fail("redaction authorities must remain OpenTelemetry and Alloy")
    if set(redaction.get("forbiddenContent", [])) != FORBIDDEN_CONTENT:
        fail("redaction forbiddenContent must match the corporate privacy contract")

    violations = find_credential_values(profile)
    if violations:
        fail("credential-like values are committed at: " + ", ".join(violations))

    print("Codestra Tempo profile privacy validation PASS")


if __name__ == "__main__":
    main()
