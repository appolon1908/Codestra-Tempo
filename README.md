# Codestra Tempo

Repository authority for the private Codestra Tempo tracing service. The final
binary is compiled from the exact verified vendored upstream tree and packaged as
a non-root, signed immutable image. Repository changes do not deploy production.

The canonical runtime is `codestra/deploy/compose.candidate.yaml`; it performs no
target-host build and accepts credentials and trust only as mounted files.
