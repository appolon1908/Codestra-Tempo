# Middleware V3 trace contract (Lane E preparation)

Status: **PREPARED_DISABLED**. `MIDDLEWARE_PREP_BASE=22d023a9c65b0789a0f7ee6c28548753521a9eff`,
`V3_FINAL_SHA=PENDING`. Tempo stores traces; Middleware keeps incident and control state.

Path: Middleware OTel SDK -> Codestra-Telemetry agent (loopback OTLP) -> central gateway
(mTLS) -> Tempo OTLP receivers (TLS >= 1.2, tenant header set server side).

## Contract (`codestra/contracts/middleware-v3-trace-contract.v1.json`)

* **Propagation**: W3C `traceparent` / `tracestate` preserved on every hop; `X-Correlation-ID`
  -> `correlation.id` (<= 128 chars); span links for outbox -> worker -> adapter; the incident
  timeline carries the same correlation id so Grafana joins incident -> trace -> logs.
* **V3 span coverage** (`EXPECTED_PENDING_V3`): HTTP ingress, JWT/auth, Policy Engine, Safety
  Gate, DB transaction, outbox, worker lease, adapter execution, provider readback,
  reconciliation. Attribute sets are fixed in Codestra-Telemetry's trace-pipeline contract.
* **Forbidden span attributes**: everything in `trace-propagation-contract.v1.json` plus
  `passwd`, `x-api-key`, OpenBao/Vault tokens, refresh/id tokens, `dsn`, `command_payload`,
  `secret_value`, raw request/response headers.
* **Span metrics**: the metrics generator may only use the closed dimension set already in
  `tempo.yaml` (`codestra.business`, `deployment.environment.name`, `cloud.region`,
  `deployment.id`, `service.namespace`, `http.request.method`, `http.response.status_code`,
  `rpc.system`, `messaging.system`, `db.system.name`, `peer.service`); `correlation.id`,
  `codestra.operation.id`, tenant/customer/user ids, `http.target`, `url.full` and
  `db.statement` are never dimensions.
* **Bounds**: receiver material from `/run/secrets`, span logging disabled, 5 MB per trace,
  no public exposure.

## Proof

`scripts/validate_middleware_v3_trace_contract.py` (in
`validate-codestra-enterprise-profile.yml`) proves the contract is dark and pinned, consistent
with the propagation contract, and that `tempo.yaml` matches it; `tests/test_middleware_v3_trace_contract.py`
rejects drift in either direction.
