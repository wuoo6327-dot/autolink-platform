#!/usr/bin/env bash
# Build a fixed native AMD64 candidate for isolated verification only.
set -euo pipefail
[[ "$(id -u)" == 0 && "$(uname -m)" == x86_64 && -n "${QA_ROOT:-}" ]] || exit 2
[[ -f "$QA_ROOT/auth/Dockerfile" && ! -e "$QA_ROOT/brand-auth-image.tar" ]] || exit 2
trap 'printf "%s\n" "$?" > "$QA_ROOT/native-build.exit"' EXIT
tag="autolink-auth:brand-auth-$(cut -c1-7 "$QA_ROOT/git-commit.txt")"
docker build --pull=false --network none --platform linux/amd64 -t "$tag" "$QA_ROOT/auth"
image=$(docker image inspect -f '{{.Id}}' "$tag")
[[ "$(docker image inspect -f '{{.Architecture}}' "$image")" == amd64 ]]
for source in app.py brand_authorization_service.py seo_service.py trade_service.py; do
  embedded=$(docker run --rm --network none --read-only --entrypoint sha256sum "$image" "/app/$source" | cut -d' ' -f1)
  staged=$(sha256sum "$QA_ROOT/auth/$source" | cut -d' ' -f1)
  [[ "$embedded" == "$staged" ]] || { echo "Image source mismatch: $source" >&2; exit 1; }
done
docker save --output "$QA_ROOT/brand-auth-image.tar" "$image"
sha256sum "$QA_ROOT/brand-auth-image.tar" > "$QA_ROOT/brand-auth-image.tar.sha256"
printf '%s\n' "$image" > "$QA_ROOT/brand-auth-image-id.txt"
printf 'NATIVE_BUILD_OK image=%s architecture=amd64\n' "$image"
