# Codestra Tempo Authority

Principal repository: `ingtrader21-spec/Codestra-Tempo`
Canonical service host: `temp.codestra.media`
Canonical DNS target: `37.27.128.39`

Use no alternate authoritative hostname.

## Ownership
Own Tempo configuration, OTLP/trace ingestion endpoints, storage, retention, compaction, search/query settings and upgrade runbooks. Do not own OpenTelemetry instrumentation, Grafana dashboards, Caddy or application tracing code.

## Exposure
Private/internal only. DNS may exist; Tempo service/query/ingest ports must not be exposed publicly.

## Integration
Upstream: OpenTelemetry Collector and approved Alloy trace pipelines. Downstream: Grafana trace queries and approved troubleshooting tooling.

## Branch policy
Persistent: `main`, `development`, `test`, `staging`, `production`. Temporary: `feature/*`, `fix/*`, `upgrade/*`, `security/*`, `docs/*`, `hotfix/*`, optional `release/*`, `rollback/*`. Promotion: work -> development -> test -> staging -> production -> main.
