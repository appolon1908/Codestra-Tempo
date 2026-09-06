#!/usr/bin/env python3
"""Exact-head entrypoint for the Codestra Tempo corporate validation suite.

The comprehensive policy checks remain in validate_codestra_enterprise_profile.py.
This entrypoint applies the locked-source Tempo storage schema, then scans the
deployable Codestra overlay for secret material without scanning the scanner's
own source code.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
from types import ModuleType
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
LEGACY_VALIDATOR = ROOT / "scripts" / "validate_codestra_enterprise_profile.py"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_policy_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("codestra_tempo_policy", LEGACY_VALIDATOR)
    if spec is None or spec.loader is None:
        fail("unable to load the Tempo policy validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_source_compatible_tempo(module: ModuleType) -> dict[str, Any]:
    config = module.load_yaml(module.TEMPO_CONFIG)
    if config.get("target") != "all":
        module.fail("current source candidate must run target=all")
    if config.get("multitenancy_enabled") is not True:
        module.fail("Tempo multi-tenancy must be enabled")
    if config.get("stream_over_http_enabled") is not True:
        module.fail("streaming trace responses must be enabled")
    if config.get("memory", {}).get("automemlimit_enabled") is not True:
        module.fail("Tempo must enable automatic memory-limit awareness")

    server = config.get("server", {})
    if server.get("log_format") != "json":
        module.fail("Tempo service logs must be JSON")
    if server.get("log_request_headers") is not False:
        module.fail("Tempo may not log request headers")
    if server.get("trace_request_headers") is not False:
        module.fail("Tempo may not trace request headers")

    receivers = config.get("distributor", {}).get("receivers", {})
    if set(receivers) != {"otlp"}:
        module.fail("Tempo may expose only the governed OTLP receiver")
    protocols = receivers.get("otlp", {}).get("protocols", {})
    if set(protocols) != {"grpc", "http"}:
        module.fail("Tempo must support governed OTLP/gRPC and OTLP/HTTP")
    if config.get("distributor", {}).get("log_received_spans", {}).get("enabled") is not False:
        module.fail("received spans may not be logged")
    if config.get("distributor", {}).get("log_discarded_spans", {}).get("enabled") is not False:
        module.fail("discarded spans may not be logged")

    query_frontend = config.get("query_frontend", {})
    if query_frontend.get("mcp_server", {}).get("enabled") is not False:
        module.fail("Tempo MCP server must remain disabled")

    generator = config.get("metrics_generator", {})
    remote_write = generator.get("storage", {}).get("remote_write", [])
    if len(remote_write) != 1:
        module.fail("Tempo requires exactly one governed Prometheus remote-write endpoint")
    remote_url = str(remote_write[0].get("url", ""))
    if "prometheus:9090/api/v1/write" not in remote_url:
        module.fail("Tempo remote write must use private Codestra Prometheus")
    if remote_write[0].get("send_exemplars") is not True:
        module.fail("Tempo must send exemplars to Prometheus")

    processor = generator.get("processor", {})
    if set(processor) != {"service_graphs", "span_metrics"}:
        module.fail("Tempo must configure service graphs and span metrics only")
    dimensions = set(processor["service_graphs"].get("dimensions", [])) | set(
        processor["span_metrics"].get("dimensions", [])
    )
    unsafe = sorted(dimensions & module.FORBIDDEN_DIMENSIONS)
    if unsafe:
        module.fail(f"unsafe Tempo derived-metric dimensions: {unsafe}")
    if processor["span_metrics"].get("enable_target_info") is not False:
        module.fail("span-metrics target_info must remain disabled")
    if processor["span_metrics"].get("enable_instance_label") is not False:
        module.fail("span-metrics instance label must remain disabled")

    storage = config.get("storage", {}).get("trace", {})
    if storage.get("backend") != "s3":
        module.fail("Tempo trace backend must be S3-compatible storage")
    block = storage.get("block", {})
    if block.get("version") != "vParquet4":
        module.fail("Tempo trace blocks must use vParquet4")
    unsupported_block_keys = {"index_downsample_bytes", "encoding"} & set(block)
    if unsupported_block_keys:
        module.fail(
            "Tempo block config contains fields removed from the locked source: "
            f"{sorted(unsupported_block_keys)}"
        )
    wal = storage.get("wal", {})
    if wal.get("path") != "/var/lib/tempo/wal":
        module.fail("Tempo WAL must use the durable runtime volume")
    if "v2_encoding" in wal:
        module.fail("Tempo WAL contains the removed v2_encoding field")

    profile = module.load_json(module.PROFILE)
    profile_storage = profile.get("storage", {})
    if profile_storage.get("formatTuningAuthority") != "locked_tempo_source":
        module.fail("the locked Tempo source must own format tuning")
    if profile_storage.get("deprecatedStorageKnobsAllowed") is not False:
        module.fail("deprecated Tempo storage knobs must remain prohibited")

    s3 = storage.get("s3", {})
    for required in ("endpoint", "bucket", "region", "insecure"):
        if required not in s3:
            module.fail(f"Tempo S3 config is missing {required}")
    serialized_s3 = json.dumps(s3).lower()
    for forbidden in ("access_key", "secret_key", "session_token"):
        if forbidden in serialized_s3:
            module.fail(f"Tempo config may not contain inline S3 credential field {forbidden}")

    if config.get("usage_report", {}).get("reporting_enabled") is not False:
        module.fail("Tempo usage reporting must remain disabled")
    overrides = config.get("overrides", {})
    if "TEMPO_OVERRIDES_FILE" not in str(overrides.get("per_tenant_override_config", "")):
        module.fail("Tempo must load its governed runtime override file")
    defaults = overrides.get("defaults", {})
    if not module.REQUIRED_OVERRIDE_SECTIONS.issubset(defaults):
        module.fail("Tempo default override sections are incomplete")
    if defaults.get("ingestion", {}).get("rate_strategy") != "global":
        module.fail("Tempo ingestion limits must use the global strategy")
    if defaults.get("read", {}).get("unsafe_query_hints") is not False:
        module.fail("unsafe TraceQL query hints must remain disabled")
    if set(defaults.get("metrics_generator", {}).get("processors", [])) != {
        "service-graphs",
        "span-metrics",
    }:
        module.fail("default derived-metric processors are incomplete")
    return config


def scan_deployable_overlay(module: ModuleType) -> None:
    module.require_file(module.FEATURES_DOC)
    module.require_file(module.OPERATING_MODEL)

    # Build signatures at runtime so this source file cannot match its own scanner.
    dash = chr(45) * 5
    private_key = dash + "BEGIN " + "PRIVATE" + chr(32) + "KEY" + dash
    openssh_key = dash + "BEGIN " + "OPENSSH" + chr(32) + "PRIVATE" + chr(32) + "KEY" + dash
    aws_access_prefix = "A" + "K" + "I" + "A"
    signatures = (private_key, openssh_key, aws_access_prefix)

    for path in module.CODESTRA.rglob("*"):
        if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for signature in signatures:
            if signature in text:
                fail(f"secret-shaped material found in {path.relative_to(ROOT)}")

    tempo_text = module.TEMPO_CONFIG.read_text(encoding="utf-8").lower()
    inline_secret_fields = (
        r"(?m)^\s*access_key\s*:",
        r"(?m)^\s*secret_key\s*:",
        r"(?m)^\s*password\s*:",
        r"(?m)^\s*authorization\s*:",
        r"(?m)^\s*session_token\s*:",
    )
    for pattern in inline_secret_fields:
        if re.search(pattern, tempo_text):
            fail("Tempo source contains an inline credential field")


def main() -> None:
    module = load_policy_module()
    module.validate_profile()
    validate_source_compatible_tempo(module)
    module.validate_overrides()
    module.validate_packaging()
    scan_deployable_overlay(module)
    print("Codestra Tempo corporate configuration validation PASS")


if __name__ == "__main__":
    main()
