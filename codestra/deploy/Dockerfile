# syntax=docker.io/docker/dockerfile@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG GO_BUILDER_IMAGE
ARG TEMPO_BASE_IMAGE
ARG TEMPO_SOURCE_REVISION

FROM ${GO_BUILDER_IMAGE} AS tempo-builder
ARG TEMPO_SOURCE_REVISION
WORKDIR /src/upstream
COPY upstream /src/upstream
RUN CGO_ENABLED=0 GOOS=linux go build \
      -buildvcs=false \
      -trimpath \
      -ldflags="-s -w -buildid= -X main.Version=codestra-source -X main.Revision=${TEMPO_SOURCE_REVISION} -X main.Branch=codestra-vendored" \
      -o /out/tempo \
      ./cmd/tempo

WORKDIR /src
COPY codestra/deploy/healthcheck.go ./healthcheck.go
COPY codestra/config/tempo.yaml ./config/tempo.yaml
COPY codestra/config/overrides.yaml ./config/overrides.yaml
COPY CODESTRA_UPSTREAM_LOCK.json ./metadata/CODESTRA_UPSTREAM_LOCK.json
COPY codestra/source-image-contract.v1.json ./metadata/source-image-contract.v1.json
RUN CGO_ENABLED=0 GOOS=linux go build \
      -trimpath \
      -ldflags='-s -w -buildid=' \
      -o /out/tempo-healthcheck \
      ./healthcheck.go \
    && /out/tempo-healthcheck 2>&1 | grep -q 'readiness request failed' \
    && install -d -m 0555 /out/rootfs/etc/tempo /out/rootfs/usr/share/codestra \
    && install -d -m 0755 /out/rootfs/var/lib/tempo /out/rootfs/var/tempo/live-store \
    && install -m 0444 ./config/tempo.yaml /out/rootfs/etc/tempo/tempo.yaml \
    && install -m 0444 ./config/overrides.yaml /out/rootfs/etc/tempo/overrides.yaml \
    && install -m 0444 ./metadata/CODESTRA_UPSTREAM_LOCK.json /out/rootfs/usr/share/codestra/CODESTRA_UPSTREAM_LOCK.json \
    && install -m 0444 ./metadata/source-image-contract.v1.json /out/rootfs/usr/share/codestra/source-image-contract.v1.json \
    && touch /out/rootfs/var/lib/tempo/.codestra-volume-owner \
             /out/rootfs/var/tempo/live-store/.codestra-volume-owner

FROM ${TEMPO_BASE_IMAGE}
LABEL org.opencontainers.image.title="Codestra Corporate Tempo"
LABEL org.opencontainers.image.description="Private multi-tenant tracing authority for Codestra-managed businesses"
LABEL org.opencontainers.image.vendor="Codestra"
LABEL codestra.source.authority="vendored-verified-upstream-tree"
LABEL codestra.runtime.base-role="runtime-substrate-only"

COPY --from=tempo-builder --chown=10001:10001 --chmod=0555 /out/tempo /tempo
COPY --from=tempo-builder --chown=10001:10001 --chmod=0555 /out/tempo-healthcheck /tempo-healthcheck
COPY --from=tempo-builder --chown=10001:10001 /out/rootfs/ /

USER 10001:10001
ENTRYPOINT ["/tempo"]
