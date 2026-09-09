# Codestra Tempo Operating Model

## Corporate role

Tempo is the private distributed-tracing data plane for Codestra-managed businesses. It receives governed OTLP traces, stores them in S3-compatible object storage, serves trace search and trace-by-ID queries, and generates service-graph and span metrics for Prometheus.

Tempo is not an authentication provider, secrets store, log store, business-intelligence warehouse, audit ledger, incident router, communications platform, product administrator or financial/trading authority.

## Current source candidate

The repository currently defines a **single-binary test/staging candidate** using the locked Tempo source. This choice is deliberate:

- it provides real multi-tenancy, S3 storage, WAL durability, derived metrics and query controls now;
- it avoids claiming a distributed architecture that has not been validated against the current Tempo source and required dependencies;
- it does not introduce an unowned or unproven Kafka control plane merely to appear highly available.

The candidate is not production-approved. A production release requires a separate distributed-HA design and evidence package.

## Private network model

- Query/API endpoint: container `tempo:3200`; optional host bind defaults to `127.0.0.1:3200` for the approved edge or local operator only.
- Internal self-metrics: container port `3101`.
- OTLP/gRPC: container port `4317`.
- OTLP/HTTP: container port `4318`.
- Internal gRPC: container port `9095`.

Only the Codestra observability network may reach these endpoints. Native Tempo and OTLP ports are never exposed directly to the Internet. Grafana queries Tempo privately; OpenTelemetry and Alloy ingest privately.

## Tenant boundary

Tempo multi-tenancy is enabled. `X-Scope-OrgID` represents a Codestra business domain:

- `platform`
- `codestra`
- `moneybee`
- `beyvra`
- `breero`
- `larim-a`
- `transportation`
- `booked4seasons`
- `social`
- `klyrow`
- `telnexa`
- `kyqra`
- `restaurant`
- `provisioning`

The ingestion gateway must authenticate workload identity, overwrite any incoming tenant header and map the workload to exactly one allowlisted business. Customer, account, user, campaign and message identifiers are never Tempo tenants.

Grafana access is not considered isolated merely because a folder is restricted. Business-specific access requires tenant-aware datasource headers, Keycloak role/team evidence and cross-business denial tests.

## Storage, credentials and recovery

The candidate uses:

- S3-compatible trace storage;
- Parquet v4 blocks with zstd compression;
- a durable local WAL and generator-state volume;
- AWS shared-credentials file injected as an external secret;
- a runtime CA file with TLS verification;
- no access key, secret key or certificate committed to Git.

Before staging, operators must prove bucket encryption, versioning, least-privilege policy, object-lock/lifecycle decisions, access logging, endpoint certificate validation and deletion behavior.

Before production, operators must additionally prove:

1. recovery from an isolated object-store copy;
2. WAL replay after unclean shutdown;
3. trace search after block-list rebuild;
4. per-tenant retention enforcement;
5. credential and CA rotation;
6. one-component and one-node failure behavior in the approved distributed topology;
7. query continuity during ingestion failover;
8. capacity for expected peak spans, derived metrics and object-store requests.

## Derived metrics

Tempo generates service graphs and span metrics and remote-writes them to the private Prometheus endpoint. Dimensions are limited to approved bounded resource/operation fields. Prometheus exemplars link metrics to trace IDs without turning trace IDs into labels.

The Prometheus remote-write receiver must remain private and accept only approved observability workloads. Tempo-generated metrics are supporting evidence; Prometheus remains the metrics and SLO authority.

## Sampling and redaction

OpenTelemetry owns tail sampling and redaction. Sampling policy preserves errors, high latency, security and reconciliation failures and low-rate critical paths while bounding normal successful traffic.

Authorization headers, cookies, credentials, raw bodies, customer financial data and provider signing material must be removed before Tempo receives a span. Tempo logging of received/discarded spans is disabled to avoid accidentally logging payload attributes.

## Service objectives

Initial engineering objectives, subject to staging calibration:

- accepted trace availability: at least 99.9% for the approved topology;
- acknowledged trace durability: no known silent loss;
- trace-by-ID p95 for recent traces: under 5 seconds;
- bounded 6-hour search p95: under 10 seconds;
- derived-metric remote-write success visible in Prometheus;
- per-business retention and query limits continuously enforced;
- zero public native Tempo or OTLP listeners;
- zero unapproved cross-business reads or writes;
- zero credentials or raw customer payloads in trace attributes.

These objectives are not production SLOs until distributed-HA and load-test evidence exists.

## Runtime hardening

The candidate image:

- requires immutable builder, upstream and final image digests;
- runs as UID/GID `10001:10001`;
- uses a read-only root filesystem;
- drops all Linux capabilities;
- enables `no-new-privileges`;
- sets CPU, memory, PID and file-descriptor limits;
- stores only WAL/generator state on a writable durable volume;
- includes a minimal static readiness binary that probes `/ready`;
- logs through the bounded container log driver for Alloy/Loki collection.

## Release and activation

Promotion is:

`feature/* -> development -> test -> staging -> production -> main`

CI builds the Tempo binary from the repository's locked upstream source and runs native configuration verification. It also validates tenant completeness, retention, privacy/cardinality policy, immutable packaging and Compose rendering.

Merge or CI success is not deployment approval. Production remains blocked until the profile's distributed-HA requirement is met and the release packet includes immutable artifact provenance, staging evidence, object-store recovery evidence, load/capacity evidence, security approval and rollback instructions.
