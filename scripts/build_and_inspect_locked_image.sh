#!/usr/bin/env bash
set -Eeuo pipefail

source_sha="${1:?exact source SHA is required}"
[[ "$source_sha" =~ ^[0-9a-f]{40}$ ]]
test "$(git rev-parse HEAD)" = "$source_sha"

builder="$(jq -r '.builderImage' codestra/release/runtime-base.lock.json)"
runtime="$(jq -r '.runtimeBaseImage' codestra/release/runtime-base.lock.json)"
revision="$(jq -r '.sourceAuthorityCommit' codestra/release/runtime-base.lock.json)"
tag="local/codestra-tempo:${source_sha}"

docker build \
  --file codestra/deploy/Dockerfile \
  --build-arg "GO_BUILDER_IMAGE=$builder" \
  --build-arg "TEMPO_BASE_IMAGE=$runtime" \
  --build-arg "TEMPO_SOURCE_REVISION=$revision" \
  --tag "$tag" \
  .

version_output="$(docker run --rm "$tag" -version)"
grep -F "$revision" <<<"$version_output"

docker run --rm \
  --env CODESTRA_ENVIRONMENT=test --env CODESTRA_REGION=ci --env CODESTRA_DEPLOYMENT_ID=exact-head \
  --env TEMPO_S3_ENDPOINT=s3.internal.example:443 --env TEMPO_S3_BUCKET=codestra-tempo-ci \
  --env TEMPO_S3_REGION=us-east-1 --env TEMPO_S3_INSECURE=false \
  --env TEMPO_MEMCACHED_ADDRESSES=dns+memcached:11211 \
  --env TEMPO_PROMETHEUS_REMOTE_WRITE_URL=http://prometheus:9090/api/v1/write \
  --env TEMPO_OVERRIDES_FILE=/etc/tempo/overrides.yaml \
  "$tag" -config.file=/etc/tempo/tempo.yaml -config.expand-env=true -config.verify -config.verify-errors-only=true

docker image inspect "$tag" | jq -e '.[0].Config.User == "10001:10001" and .[0].Config.Entrypoint == ["/tempo"]'
container_id=""
cleanup() {
  if [[ -n "$container_id" ]]; then docker container rm "$container_id" >/dev/null; fi
}
trap cleanup EXIT
container_id="$(docker create "$tag")"
lock_copy="${RUNNER_TEMP:-/tmp}/tempo-source-lock-${source_sha}.json"
docker cp "$container_id:/usr/share/codestra/CODESTRA_UPSTREAM_LOCK.json" "$lock_copy"
cmp CODESTRA_UPSTREAM_LOCK.json "$lock_copy"
echo "TEMPO_LOCKED_IMAGE_INSPECTION=PASS"
