#!/usr/bin/env python3
"""Fail-closed validation for the Codestra Tempo corporate overlay."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODESTRA = ROOT / "codestra"
PROFILE = CODESTRA / "enterprise-profile.v1.json"
TEMPO_CONFIG = CODESTRA / "config" / "tempo.yaml"
OVERRIDES = CODESTRA / "config" / "overrides.yaml"
COMPOSE = CODESTRA / "deploy" / "compose.candidate.yaml"
DOCKERFILE = CODESTRA / "deploy" / "Dockerfile"
HEALTHCHECK = CODESTRA / "deploy" / "healthcheck.go"
FEATURES_DOC = CODESTRA / "docs" / "CORPORATE-FEATURES.md"
OPERATING_MODEL = CODESTRA / "docs" / "OPERATING-MODEL.md"

BUSINESSES = {
    "codestra",
    "moneybee",
    "beyvra",
    "breero",
    "larim-a",
    "transportation",
    "booked4seasons",
    "social",
    "klyrow",
    "telnexa",
    "kyqra",
    "restaurant",
    "provisioning",
}
TENANTS = BUSINESSES | {"platform"}
REQUIRED_RESOURCE_ATTRIBUTES = {
    "service.name",
    "service.namespace",
    "service.version",
    "deployment.environment.name",
    "deployment.id",
    "cloud.region",
    "codestra.business",
}
EXPECTED_RETENTION = {
    "platform": "720h",
    "codestra": "720h",
    "moneybee": "1440h",
    "beyvra": "1440h",
    "breero": "720h",
    "larim-a": "720h",
    "transportation": "720h",
    "booked4seasons": "720h",
    "social": "720h",
    "klyrow": "720h",
    "telnexa": "720h",
    "kyqra": "336h",
    "restaurant": "720h",
    "provisioning": "1440h",
}
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
FORBIDDEN_DIMENSIONS = {
    "tenant_id",
    "customer_id",
    "account_id",
    "user_id",
    "email",
    "phone",
    "message_id",
    "order_id",
    "request_id",
    "correlation_id",
    "trace_id",
    "span_id",
    "raw_url",
    "query_string",
    "db.statement",
    "exception.message",
    "container.id",
    "process.pid",
}
REQUIRED_OVERRIDE_SECTIONS = {
    "ingestion",
    "read",
    "compaction",
    "global",
    "metrics_generator",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def validate_runtime_image_environment() -> None:
    """Fail closed when deployment supplies an expanded image reference."""
    runtime_image = os.environ.get("CODESTRA_TEMPO_IMAGE")
    runtime_digest = os.environ.get("CODESTRA_IMAGE_DIGEST")
    if runtime_image is None and runtime_digest is None:
        return
    immutable_image = re.compile(
        r"^[a-z0-9./_-]+(?::[a-zA-Z0-9._-]+)?@sha256:([0-9a-f]{64})$"
    )
    match = immutable_image.fullmatch(runtime_image or "")
    if not match:
        fail("expanded CODESTRA_TEMPO_IMAGE must be an immutable @sha256:<64 hex> reference")
    if runtime_digest != f"sha256:{match.group(1)}":
        fail("CODESTRA_IMAGE_DIGEST must equal the digest in CODESTRA_TEMPO_IMAGE")


def require_file(path: pathlib.Path) -> str:
    if not path.is_file():
        fail(f"missing required file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def load_json(path: pathlib.Path) -> Any:
    try:
        return json.loads(require_file(path))
    except Exception as exc:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {exc}")


def load_yaml(path: pathlib.Path) -> Any:
    try:
        return yaml.safe_load(require_file(path))
    except Exception as exc:
        fail(f"invalid YAML {path.relative_to(ROOT)}: {exc}")


def require_positive_int(value: Any, field: str, tenant: str) -> None:
    if not isinstance(value, int) or value <= 0:
        fail(f"tenant {tenant} requires positive integer {field}")


def validate_profile() -> dict[str, Any]:
    profile = load_json(PROFILE)
    repository = os.environ.get(
        "GITHUB_REPOSITORY", "ingtrader21-spec/Codestra-Tempo"
    )
    if repository != "ingtrader21-spec/Codestra-Tempo":
        fail(f"validator is bound to Codestra-Tempo, received {repository}")
    if profile.get("schemaVersion") != "1.1":
        fail("profile schemaVersion must be 1.1")
    if profile.get("canonicalHostname") != "temp.codestra.media":
        fail("canonical Tempo hostname must be temp.codestra.media")
    if profile.get("status") != "CONFIG_PREPARED_NOT_DEPLOYED":
        fail("Tempo status must remain CONFIG_PREPARED_NOT_DEPLOYED")
    if profile.get("exposure") != "internal_private":
        fail("native Tempo exposure must remain internal_private")
    if set(profile.get("businessScope", [])) != BUSINESSES:
        fail("profile must exactly represent the Codestra business portfolio")
    if set(profile.get("requiredResourceAttributes", [])) != REQUIRED_RESOURCE_ATTRIBUTES:
        fail("profile resource attributes do not match the corporate trace contract")
    if not FORBIDDEN_DIMENSIONS.issubset(
        set(profile.get("forbiddenMetricOrTenantDimensions", []))
    ):
        fail("profile does not forbid all unsafe tenant/metric dimensions")

    tenancy = profile.get("tenancy", {})
    if tenancy.get("enabled") is not True:
        fail("Tempo business multi-tenancy must be enabled")
    if tenancy.get("customerIdentifiersAsTenantIds") is not False:
        fail("customer identifiers may not be Tempo tenant IDs")
    if tenancy.get("callerSuppliedTenantHeaderTrusted") is not False:
        fail("caller-supplied Tempo tenant headers may not be trusted")
    if tenancy.get("crossBusinessAccessDefault") != "deny":
        fail("cross-business trace access must default to deny")

    topology = profile.get("topology", {})
    if topology.get("currentCandidate") != "single_binary_test_and_staging":
        fail("current topology must remain the source-proven test/staging candidate")
    if topology.get("productionDistributedHARequired") is not True:
        fail("production must require distributed HA")
    if topology.get("productionApproved") is not False:
        fail("production may not be marked approved")

    features = profile.get("features", {})
    disabled = sorted(name for name in REQUIRED_FEATURES if features.get(name) is not True)
    if disabled:
        fail(f"required Tempo corporate features are disabled: {disabled}")
    if profile.get("sampling", {}).get("authority") != "opentelemetry":
        fail("OpenTelemetry must remain the sampling authority")
    if profile.get("sampling", {}).get("tempoPerformsTailSampling") is not False:
        fail("Tempo may not claim a second tail-sampling authority")
    return profile


def validate_tempo_config() -> dict[str, Any]:
    config = load_yaml(TEMPO_CONFIG)
    if config.get("target") != "all":
        fail("current source candidate must run target=all")
    if config.get("multitenancy_enabled") is not True:
        fail("Tempo multi-tenancy must be enabled")
    if config.get("stream_over_http_enabled") is not True:
        fail("streaming trace responses must be enabled")
    if config.get("memory", {}).get("automemlimit_enabled") is not True:
        fail("Tempo must enable automatic memory-limit awareness")

    server = config.get("server", {})
    if server.get("log_format") != "json":
        fail("Tempo service logs must be JSON")
    if server.get("log_request_headers") is not False:
        fail("Tempo may not log request headers")
    if server.get("trace_request_headers") is not False:
        fail("Tempo may not trace request headers")

    receivers = config.get("distributor", {}).get("receivers", {})
    if set(receivers) != {"otlp"}:
        fail("Tempo may expose only the governed OTLP receiver")
    protocols = receivers.get("otlp", {}).get("protocols", {})
    if set(protocols) != {"grpc", "http"}:
        fail("Tempo must support governed OTLP/gRPC and OTLP/HTTP")
    if config.get("distributor", {}).get("log_received_spans", {}).get("enabled") is not False:
        fail("received spans may not be logged")
    if config.get("distributor", {}).get("log_discarded_spans", {}).get("enabled") is not False:
        fail("discarded spans may not be logged")

    query_frontend = config.get("query_frontend", {})
    if query_frontend.get("mcp_server", {}).get("enabled") is not False:
        fail("Tempo MCP server must remain disabled")

    generator = config.get("metrics_generator", {})
    remote_write = generator.get("storage", {}).get("remote_write", [])
    if len(remote_write) != 1:
        fail("Tempo requires exactly one governed Prometheus remote-write endpoint")
    remote_url = str(remote_write[0].get("url", ""))
    if "prometheus:9090/api/v1/write" not in remote_url:
        fail("Tempo remote write must use private Codestra Prometheus")
    if remote_write[0].get("send_exemplars") is not True:
        fail("Tempo must send exemplars to Prometheus")

    processor = generator.get("processor", {})
    if set(processor) != {"service_graphs", "span_metrics"}:
        fail("Tempo must configure service graphs and span metrics only")
    dimensions = set(processor["service_graphs"].get("dimensions", [])) | set(
        processor["span_metrics"].get("dimensions", [])
    )
    unsafe = sorted(dimensions & FORBIDDEN_DIMENSIONS)
    if unsafe:
        fail(f"unsafe Tempo derived-metric dimensions: {unsafe}")
    if processor["span_metrics"].get("enable_target_info") is not False:
        fail("span-metrics target_info must remain disabled")
    if processor["span_metrics"].get("enable_instance_label") is not False:
        fail("span-metrics instance label must remain disabled")

    storage = config.get("storage", {}).get("trace", {})
    if storage.get("backend") != "s3":
        fail("Tempo trace backend must be S3-compatible storage")
    if storage.get("block", {}).get("version") != "vParquet4":
        fail("Tempo trace blocks must use vParquet4")
    # ``block.encoding`` was renamed to ``v2_encoding`` upstream and only applies to
    # v2 blocks; the locked source parses the config strictly, so the field must be
    # absent for vParquet4 (see validate_codestra_corporate_tempo.py).
    if "encoding" in storage.get("block", {}):
        fail("Tempo trace blocks must not set the removed block.encoding field")
    if storage.get("wal", {}).get("path") != "/var/lib/tempo/wal":
        fail("Tempo WAL must use the durable runtime volume")
    s3 = storage.get("s3", {})
    for required in ("endpoint", "bucket", "region", "insecure"):
        if required not in s3:
            fail(f"Tempo S3 config is missing {required}")
    serialized_s3 = json.dumps(s3).lower()
    for forbidden in ("access_key", "secret_key", "session_token"):
        if forbidden in serialized_s3:
            fail(f"Tempo config may not contain inline S3 credential field {forbidden}")

    if config.get("usage_report", {}).get("reporting_enabled") is not False:
        fail("Tempo usage reporting must remain disabled")
    overrides = config.get("overrides", {})
    if "TEMPO_OVERRIDES_FILE" not in str(overrides.get("per_tenant_override_config", "")):
        fail("Tempo must load its governed runtime override file")
    defaults = overrides.get("defaults", {})
    if not REQUIRED_OVERRIDE_SECTIONS.issubset(defaults):
        fail("Tempo default override sections are incomplete")
    if defaults.get("ingestion", {}).get("rate_strategy") != "global":
        fail("Tempo ingestion limits must use the global strategy")
    if defaults.get("read", {}).get("unsafe_query_hints") is not False:
        fail("unsafe TraceQL query hints must remain disabled")
    if set(defaults.get("metrics_generator", {}).get("processors", [])) != {
        "service-graphs",
        "span-metrics",
    }:
        fail("default derived-metric processors are incomplete")
    return config


def validate_overrides() -> None:
    document = load_yaml(OVERRIDES)
    tenants = document.get("overrides", {})
    if set(tenants) != TENANTS:
        missing = sorted(TENANTS - set(tenants))
        extra = sorted(set(tenants) - TENANTS)
        fail(f"Tempo tenant override catalogue mismatch; missing={missing}, extra={extra}")

    for tenant, override in tenants.items():
        if set(override) != REQUIRED_OVERRIDE_SECTIONS:
            fail(f"tenant {tenant} must define every governed override section")
        ingestion = override["ingestion"]
        if ingestion.get("rate_strategy") != "global":
            fail(f"tenant {tenant} must use global ingestion rate strategy")
        for field in (
            "rate_limit_bytes",
            "burst_size_bytes",
            "max_traces_per_user",
            "max_global_traces_per_user",
            "max_attribute_bytes",
        ):
            require_positive_int(ingestion.get(field), field, tenant)
        if ingestion.get("burst_size_bytes", 0) < ingestion.get("rate_limit_bytes", 0):
            fail(f"tenant {tenant} burst must be at least its rate limit")

        read = override["read"]
        for field in ("max_bytes_per_tag_values_query", "max_blocks_per_tag_values_query"):
            require_positive_int(read.get(field), field, tenant)
        if read.get("unsafe_query_hints") is not False:
            fail(f"tenant {tenant} may not enable unsafe query hints")
        if read.get("left_pad_trace_ids") is not True:
            fail(f"tenant {tenant} must normalize short trace IDs")

        if override["compaction"].get("block_retention") != EXPECTED_RETENTION[tenant]:
            fail(f"tenant {tenant} retention does not match corporate policy")
        require_positive_int(override["global"].get("max_bytes_per_trace"), "max_bytes_per_trace", tenant)

        metrics = override["metrics_generator"]
        if metrics.get("ring_size") != 1:
            fail(f"tenant {tenant} ring_size must match the single-binary candidate")
        if set(metrics.get("processors", [])) != {"service-graphs", "span-metrics"}:
            fail(f"tenant {tenant} derived-metric processors are incomplete")
        require_positive_int(metrics.get("max_active_series"), "max_active_series", tenant)
        if metrics.get("disable_collection") is not False:
            fail(f"tenant {tenant} metric collection may not be disabled")
        forwarder = metrics.get("forwarder", {})
        require_positive_int(forwarder.get("queue_size"), "forwarder.queue_size", tenant)
        require_positive_int(forwarder.get("workers"), "forwarder.workers", tenant)

    serialized = OVERRIDES.read_text(encoding="utf-8").lower()
    for forbidden in ("customer", "account_id", "email", "phone", "user_id"):
        if re.search(rf"^  [^#\n]*{re.escape(forbidden)}[^:]*:\s*$", serialized, re.MULTILINE):
            fail(f"customer/person-level Tempo tenant key found: {forbidden}")


def validate_packaging() -> None:
    compose = load_yaml(COMPOSE)
    services = compose.get("services", {})
    if set(services) != {"tempo"}:
        fail("Tempo candidate must define exactly the governed Tempo service")
    service = services["tempo"]
    if service.get("user") != "10001:10001":
        fail("Tempo must run as UID/GID 10001")
    if service.get("read_only") is not True:
        fail("Tempo root filesystem must be read-only")
    if service.get("privileged") is True or service.get("network_mode") == "host":
        fail("Tempo may not use privileged or host-network mode")
    if "ALL" not in service.get("cap_drop", []):
        fail("Tempo must drop all Linux capabilities")
    if "no-new-privileges:true" not in service.get("security_opt", []):
        fail("Tempo must enable no-new-privileges")
    if set(service.get("networks", [])) != {"codestra-observability"}:
        fail("Tempo must attach only to the observability network")
    if set(service.get("secrets", [])) != {"tempo_s3_credentials", "tempo_s3_ca"}:
        fail("Tempo external secret-file contract is incomplete")
    top_level_secrets = compose.get("secrets", {})
    if set(top_level_secrets) != {"tempo_s3_credentials", "tempo_s3_ca"}:
        fail("Tempo top-level secret-file contract is incomplete")
    if any("file" not in value or "external" in value for value in top_level_secrets.values()):
        fail("Tempo credentials and trust must use mounted files")
    if service.get("healthcheck", {}).get("test") != ["CMD", "/tempo-healthcheck"]:
        fail("Tempo must use the native readiness probe")

    ports = [str(port) for port in service.get("ports", [])]
    if ports != ["127.0.0.1:${TEMPO_QUERY_HOST_PORT:-3200}:3200"]:
        fail("Tempo may publish only the loopback-bound query endpoint")
    if not {"4317", "4318"}.issubset(set(service.get("expose", []))):
        fail("private OTLP ports must be exposed to the observability network")
    volumes = [str(volume) for volume in service.get("volumes", [])]
    if "tempo-data:/var/lib/tempo" not in volumes:
        fail("Tempo must persist WAL and generator state")

    image = str(service.get("image", ""))
    if "${CODESTRA_TEMPO_IMAGE:" not in image or "sha256" not in image:
        fail("Tempo runtime must require an immutable final image")
    validate_runtime_image_environment()
    if "build" in service:
        fail("deployment candidate may not build on the target host")
    limits = service.get("deploy", {}).get("resources", {}).get("limits", {})
    for field in ("cpus", "memory", "pids"):
        if field not in limits:
            fail(f"Tempo runtime is missing resource limit {field}")
    if service.get("labels", {}).get("codestra.production.ha-approved") != "false":
        fail("Tempo candidate must visibly remain non-HA/non-production")

    dockerfile = require_file(DOCKERFILE)
    for fragment in (
        "ARG GO_BUILDER_IMAGE",
        "ARG TEMPO_BASE_IMAGE",
        "COPY upstream /src/upstream",
        "-o /out/tempo",
        "COPY --from=tempo-builder",
        "CGO_ENABLED=0",
        "-trimpath",
        "/tempo-healthcheck",
        "/etc/tempo/tempo.yaml",
        "/etc/tempo/overrides.yaml",
        "CODESTRA_UPSTREAM_LOCK.json",
        "USER 10001:10001",
        'ENTRYPOINT ["/tempo"]',
    ):
        if fragment not in dockerfile:
            fail(f"Tempo Dockerfile is missing {fragment}")
    if ":latest" in dockerfile:
        fail("Tempo Dockerfile may not use latest tags")

    healthcheck = require_file(HEALTHCHECK)
    if "http://127.0.0.1:3200/ready" not in healthcheck:
        fail("Tempo readiness probe must default to the local /ready endpoint")
    if "exec.Command" in healthcheck or "os/exec" in healthcheck:
        fail("Tempo readiness probe may not invoke a shell or subprocess")

    serialized = COMPOSE.read_text(encoding="utf-8")
    for forbidden in (
        "0.0.0.0:3200",
        ":latest",
        "privileged: true",
        "/var/run/docker.sock",
        "network_mode: host",
    ):
        if forbidden in serialized:
            fail(f"Tempo Compose candidate contains forbidden runtime content: {forbidden}")


def validate_documents_and_secrets() -> None:
    require_file(FEATURES_DOC)
    require_file(OPERATING_MODEL)

    marker = "-" * 5
    signatures = (
        marker + "BEGIN " + "PRIVATE KEY" + marker,
        marker + "BEGIN " + "OPENSSH PRIVATE KEY" + marker,
        "AK" + "IA",
    )
    roots = (CODESTRA, ROOT / "scripts")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for signature in signatures:
                if signature in text:
                    fail(f"secret-shaped material found in {path.relative_to(ROOT)}")

    tempo_text = TEMPO_CONFIG.read_text(encoding="utf-8").lower()
    for pattern in (
        r"(?m)^\s*access_key\s*:",
        r"(?m)^\s*secret_key\s*:",
        r"(?m)^\s*password\s*:",
        r"(?m)^\s*authorization\s*:",
    ):
        if re.search(pattern, tempo_text):
            fail("Tempo source contains an inline credential field")


def main() -> None:
    validate_profile()
    validate_tempo_config()
    validate_overrides()
    validate_packaging()
    validate_documents_and_secrets()
    print("Codestra Tempo corporate configuration validation PASS")


if __name__ == "__main__":
    main()
