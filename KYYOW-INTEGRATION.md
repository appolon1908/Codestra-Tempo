# Kyyow integration

This repository is the source authority for **tempo** in the Kyyow platform. Its Kyyow boundary is machine-readable in [kyyow-integration.v1.json](kyyow-integration.v1.json).

The component is **private** and its native ports are not made public by this contract. Keycloak owns identity, OpenBao owns secret delivery, and Middleware remains the sole writer to Odoo. Grafana and Superset consume read-only data paths.

This contract is source-complete but deliberately does not claim a live deployment. Production activation requires an immutable image/configuration digest, private-network verification, restore and rollback evidence, and a separately approved cutover.

## Source topology and limits

`codestra/config/tempo.yaml` configures HTTP 3200, gRPC 9095, internal HTTP 3101, and OTLP 4317/4318. It depends on S3 storage and Memcached (default 11211) and sends generated metrics to Prometheus. Telemetry sends traces directly to Tempo; the committed Alloy configuration contains no OTLP trace pipeline.

All listed ports are private or loopback. This correction does not authorize runtime activation.
