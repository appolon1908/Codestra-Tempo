# Codestra Tempo Corporate Features

## Mission

Tempo is the private trace storage, search, service-graph, span-metric and correlation authority for Codestra. It connects browser/API activity, Caddy, Kong, Middleware, Odoo, n8n, workers, PostgreSQL, Redis and approved providers into one operational request path without becoming a business-action system.

## Corporate path coverage

Target trace paths include:

- browser or mobile client to public API;
- Caddy to Kong to Middleware;
- Middleware to Odoo and n8n;
- queues, outbox/inbox and asynchronous workers;
- PostgreSQL, Redis and other bounded dependencies;
- approved email, SMS, voice, scraper and external-provider adapters;
- deployment, capability and reconciliation control paths;
- Beyvra market-data and order-path health using safe metadata only.

Async boundaries preserve W3C trace context and a protected `correlation_id` when the protocol supports it.

## Corporate resource contract

Every accepted trace carries bounded resource attributes:

- `service.name`
- `service.namespace`
- `service.version`
- `deployment.environment.name`
- `deployment.id`
- `cloud.region`
- `codestra.business`

`codestra.business` is one of the approved Codestra business domains. It is not a customer, user, account or campaign identifier.

Tempo tenant IDs are business domains enforced through `X-Scope-OrgID`. The approved ingress layer must authenticate the workload, overwrite any caller-supplied tenant header, map it to exactly one approved business and deny unknown businesses.

## Corporate features

- OTLP/gRPC and OTLP/HTTP ingestion on private networks;
- business-level multi-tenancy and deny-by-default cross-business access;
- S3-compatible Parquet v4 storage with durable local WAL;
- per-business retention, ingestion, trace-size, query and active-series budgets;
- TraceQL search and trace-by-ID investigation;
- service graph generation;
- span metrics with Prometheus exemplars;
- Grafana trace-to-metric and trace-to-redacted-log links;
- deployment/version, region and business correlation;
- bounded dependency and provider latency analysis;
- queue/worker and webhook continuity;
- private readiness and self-metrics endpoints;
- runtime secret-file credentials and TLS verification;
- source-native configuration verification against the locked Tempo code.

## Sampling authority

OpenTelemetry, not Tempo, owns sampling. Tail-sampling policy must preserve errors, high latency, security or reconciliation failures and low-rate critical paths while bounding routine successful traffic. Tempo stores the already governed trace stream and does not silently apply a second sampling authority.

## Privacy and cardinality

OpenTelemetry and Alloy redact before Tempo ingestion. Tempo must never receive:

- Authorization, cookie or session headers;
- passwords, API keys, private keys, client secrets or database DSNs;
- raw request or response bodies by default;
- raw payment, lending, email, SMS, voice, identity or customer payloads;
- broker or exchange credentials and signing material;
- authoritative balances, positions, executions or ledgers.

Customer IDs, account IDs, user IDs, email addresses, phone numbers, message IDs, order IDs, request IDs, correlation IDs, trace IDs, span IDs, raw URLs, query strings, SQL text, exception messages, container IDs and process IDs are forbidden as tenant IDs and derived-metric dimensions. Trace/span IDs remain protected correlation fields, not labels.

## Retention model

- Default business and platform traces: 30 days.
- MoneyBee, Beyvra and Provisioning: 60 days.
- High-volume Kyqra traces: 14 days.

Any increase requires privacy, storage-cost, recovery and legal review. Retention is not a substitute for an audit ledger or business system of record.

## Beyvra trading boundary

Beyvra traces may show safe operation names, aggregate latency, provider health, reconciliation result, market-data freshness and externally effective capability state. Tempo never stores credentials or signing material, never exposes raw order payloads or customer financial state and never receives authority to place, replace, cancel or approve a trade.

## Release rule

The current source candidate is a single-binary test/staging topology because it can be validated against the locked source without inventing an unproven Kafka control plane. Production requires a separately reviewed distributed-HA topology, ingestion failover, query continuity, object-store restore and capacity evidence.

`temp.codestra.media` remains internal/private. Promotion is `feature/* -> development -> test -> staging -> production -> main`. Merge or CI success does not deploy Tempo, expose OTLP publicly or authorize any business mutation.
