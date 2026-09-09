# Repository profile

- Authority: `appolon1908-hue/Codestra-Tempo`
- Component: `tempo`
- Artifact model: repository-built signed image
- Source authority: verified vendored Grafana Tempo commit
- Runtime identity: UID/GID 10001, read-only root filesystem
- Exposure: loopback query endpoint and private OTLP/container endpoints only
- Runtime credentials: mounted files only
- Production activation from source: disabled

The source candidate remains single-binary and explicitly not production HA
approved. A later protected promotion must supply distributed-HA evidence.
