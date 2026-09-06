# Codestra Tempo Production Server and Native API Contract

## Authority

- Repository: `appolon1908-hue/Codestra-Tempo`
- Role: business-isolated distributed trace authority
- Canonical hostname: `temp.codestra.media`
- Central production host: `37.27.128.39`
- Core application host `65.109.65.169`: approved trace source only
- Status: `SOURCE_CONTRACT_PREPARED_NOT_DEPLOYED`

Tempo owns trace ingestion, storage, retention, search, service graphs, span metrics, source/release evidence, recovery, and rollback. It does not own OpenTelemetry normalization, Grafana presentation, business mutation, or trading authority.

## Native API surface

| Method | Path | Purpose | Boundary |
|---|---|---|---|
| `GET` | `/ready` | readiness | private/read-only |
| `GET` | `/metrics` | internal metrics | private Prometheus scrape |
| `GET` | `/api/search` | bounded trace search | authenticated and tenant-scoped |
| `GET` | `/api/traces/{trace_id}` | single trace lookup | authenticated and tenant-scoped |
| OTLP | private ingestion endpoints | trace ingestion | mTLS and deployment-assigned tenant |

Unexpected `404` and `5xx` responses block certification. Wrong-role, wrong-business, expired-credential, and revoked-credential requests must fail closed.

## Tenancy and data controls

- Native ingestion and query ports remain private.
- `codestra_business` is assigned by workload identity, not request input.
- Cross-business trace search and trace-ID lookup are denied.
- Search limits, trace-size limits, request timeouts, retention, and concurrency limits are source-controlled.
- Customer payloads, credentials, cookies, raw request/response bodies, database statements, broker/exchange signing data, authoritative balances, positions, and executions are removed or rejected before ingestion.
- Trace IDs are correlation fields, not public discovery keys.

## Production gates

```text
PROTECTED_PRODUCTION_SHA=PASS
TENANT_CONFIGURATION=PASS
TRACE_LIMITS=PASS
RETENTION_CONFIGURATION=PASS
IMMUTABLE_IMAGE_DIGEST=PASS
IMAGE_SIGNATURE=PASS
SBOM=PASS
PROVENANCE=PASS
SECRET_SCAN=PASS
VULNERABILITY_GATE=PASS
STORAGE_RECOVERY=PASS
ROLLBACK_MANIFEST=PASS
```

## Runtime certification

```text
GET_/ready=PASS
GET_/metrics=PASS
GET_/api/search_ROUTE_EXISTS=PASS
GET_/api/traces/{trace_id}_ROUTE_EXISTS=PASS
PRIVATE_OTLP_INGESTION=PASS
UNAUTHENTICATED_QUERY_DENIED=PASS
WRONG_BUSINESS_DENIED=PASS
TRACE_ID_ABUSE_CONTROLS=PASS
TLS_VERIFY=PASS
MTLS=PASS
UNEXPECTED_404=0
UNEXPECTED_5XX=0
SOURCE_RUNTIME_DRIFT=0
```

Use only synthetic canary traces. Prove OpenTelemetry-to-Tempo ingestion and Tempo-to-Grafana query/correlation without exposing customer or financial payloads.

## Recovery and remediation

Validate storage recovery, index/block integrity, retention behavior, restart recovery, and rollback to the prior exact digest/configuration. Fix runtime defects here with tests and normal protected review; never patch production and leave this repository behind.

## Safety

This document does not deploy Tempo or activate ingestion. SSH changes, business writes, communications delivery, provider actions, payments, lending, and trading are outside scope and disabled.