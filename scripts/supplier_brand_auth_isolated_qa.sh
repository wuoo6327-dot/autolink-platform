#!/usr/bin/env bash
# Candidate -> current SEO production -> candidate on a restored copy only.
set -euo pipefail
for name in QA_ROOT QA_BASE_ROOT QA_AUTH_IMAGE QA_BASE_AUTH_IMAGE QA_WEB_IMAGE QA_DB_SNAPSHOT QA_AUTH_NONDB_ARCHIVE QA_RUN_ID; do
  [[ -n "${!name:-}" ]] || { echo "Missing $name" >&2; exit 2; }
done
[[ "$(id -u)" == 0 && "$(uname -m)" == x86_64 && "$QA_RUN_ID" =~ ^[a-z0-9-]+$ ]] || exit 2
[[ -d "$QA_ROOT/auth" && -d "$QA_ROOT/site" && -d "$QA_BASE_ROOT/site" ]] || exit 2
[[ -s "$QA_DB_SNAPSHOT" && -s "$QA_AUTH_NONDB_ARCHIVE" ]] || exit 2
DATA="$QA_ROOT/isolated-data-$QA_RUN_ID"
[[ ! -e "$DATA" ]] || { echo 'Isolated data already exists' >&2; exit 2; }
PORT=18185
AUTH="autolink-brand-auth-$QA_RUN_ID-auth"
WEB="autolink-brand-auth-$QA_RUN_ID-web"
NET="autolink-brand-auth-$QA_RUN_ID-net"
for image in "$QA_AUTH_IMAGE" "$QA_BASE_AUTH_IMAGE" "$QA_WEB_IMAGE"; do
  [[ "$(docker image inspect -f '{{.Architecture}}' "$image")" == amd64 ]] || exit 2
done
umask 077
mkdir -m 0700 "$DATA"
cp "$QA_DB_SNAPSHOT" "$DATA/autolink-auth.sqlite3"
tar -xzf "$QA_AUTH_NONDB_ARCHIVE" -C "$DATA"
chown -R 10001:10001 "$DATA"
python3 - "$DATA/autolink-auth.sqlite3" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('PRAGMA foreign_key_check').fetchone() is None
    assert db.execute('SELECT count(*) FROM catalog_models').fetchone()[0]>=270
    assert db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0]>=60
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_brand_authorizations'").fetchone()
PY
docker network create "$NET" >/dev/null
stop_pair(){ docker rm -f "$WEB" "$AUTH" >/dev/null 2>&1 || true; }
cleanup(){ stop_pair; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
start_pair(){
  local image="$1" site="$2"
  docker run -d --name "$AUTH" --network "$NET" --network-alias auth --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=32m,mode=1777 \
    -v "$DATA:/data" -v "$site:/srv:ro" -e AUTH_DB_PATH=/data/autolink-auth.sqlite3 \
    -e GOOGLE_CLIENT_ID=qa-client -e MEMBERSHIP_RESTRICTIONS=true "$image" >/dev/null
  docker run -d --name "$WEB" --network "$NET" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=16m,mode=1777 \
    --tmpfs /data:size=16m,uid=10001,gid=10001 --tmpfs /config:size=16m,uid=10001,gid=10001 \
    -p "127.0.0.1:$PORT:8088" -v "$QA_BASE_ROOT/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$site:/srv:ro" \
    -e SITE_ADDRESS=:8088 "$QA_WEB_IMAGE" >/dev/null
  for attempt in $(seq 1 75); do
    if [[ "$(docker inspect -f '{{.State.Health.Status}}' "$AUTH")" == healthy ]] && \
       curl -fsS --max-time 3 "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then return; fi
    sleep 1
  done
  docker logs --tail 40 "$AUTH" >&2
  docker logs --tail 40 "$WEB" >&2
  return 1
}
probe(){
  local phase="$1" expected="$2"
  [[ "$(docker inspect -f '{{.Image}}' "$AUTH")" == "$expected" ]]
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$AUTH")" == healthy ]]
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/autolink/supplier/brand-authorizations")" == 401 ]]
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/autolink/admin/suppliers/unknown/brand-authorizations")" == 401 ]]
  PHASE="$phase" python3 - "$DATA/autolink-auth.sqlite3" <<'PY'
import json,os,sqlite3,sys,urllib.request
base='http://127.0.0.1:18185'
def read(path):
    with urllib.request.urlopen(base+path,timeout=10) as r:return r.read()
models=json.loads(read('/autolink/public/models?limit=500'))['data']
brands=json.loads(read('/autolink/public/brands'))['data']
assert len(models)==244 and len(brands)==53
assert b'Haval H6' in read('/trade/models/haval-catalog-1')
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    table=bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_brand_authorizations'").fetchone())
    assert table and db.execute('SELECT count(*) FROM supplier_brand_authorizations').fetchone()[0]==0
print(json.dumps({'phase':os.environ['PHASE'],'publicModels':len(models),'publicBrands':len(brands),'brandAuthorizationRows':0}))
PY
}
start_pair "$QA_AUTH_IMAGE" "$QA_ROOT/site"
probe candidate "$QA_AUTH_IMAGE"
stop_pair
start_pair "$QA_BASE_AUTH_IMAGE" "$QA_BASE_ROOT/site"
probe rollback "$QA_BASE_AUTH_IMAGE"
stop_pair
start_pair "$QA_AUTH_IMAGE" "$QA_ROOT/site"
probe restored_candidate "$QA_AUTH_IMAGE"
echo 'SUPPLIER_BRAND_AUTH_ISOLATED_QA_PASSED'
