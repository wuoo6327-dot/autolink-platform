#!/usr/bin/env bash
# Native AMD64 candidate -> current production -> candidate rehearsal, never mounting live volumes.
set -euo pipefail
ROOT=/opt/autolink-releases/16f65c8-afme-20261014
OLD=/opt/autolink-releases/c215c54-notifications-20261014
PORT=18184
AUTH=autolink-afme-isolated-auth
WEB=autolink-afme-isolated-web
NET=autolink-afme-isolated-net
[[ "${QA_RUN_ID:-}" =~ ^[a-z0-9-]+$ ]] || { echo 'Set a unique QA_RUN_ID' >&2; exit 2; }
DATA="$ROOT/isolated-data-$QA_RUN_ID"
[[ "$(id -u)" == 0 && "$(uname -m)" == x86_64 ]] || { echo 'Root on native AMD64 required' >&2; exit 2; }
[[ -n "${QA_AUTH_IMAGE:-}" && -n "${QA_BASELINE_AUTH_IMAGE:-}" && -n "${QA_WEB_IMAGE:-}" && -s "${QA_DB_SNAPSHOT:-/missing}" ]] || { echo 'Fixed images and verified SQLite snapshot required' >&2; exit 2; }
[[ ! -e "$DATA" ]] || { echo 'Isolated data exists; use a fresh stage' >&2; exit 2; }
docker image inspect "$QA_AUTH_IMAGE" "$QA_BASELINE_AUTH_IMAGE" "$QA_WEB_IMAGE" >/dev/null
stop_pair(){ docker rm -f "$WEB" "$AUTH" >/dev/null 2>&1 || true; }
cleanup(){ stop_pair; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
mkdir -m 0700 "$DATA"
cp "$QA_DB_SNAPSHOT" "$DATA/autolink-auth.sqlite3"
chown 10001:10001 "$DATA" "$DATA/autolink-auth.sqlite3"
python3 - "$DATA/autolink-auth.sqlite3" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('PRAGMA foreign_key_check').fetchone() is None
    assert db.execute('SELECT count(*) FROM catalog_models').fetchone()[0]>=270
    assert db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0]>=60
PY
docker network create "$NET" >/dev/null
start_pair(){
  local image="$1" site="$2" config="$3"
  docker run -d --name "$AUTH" --network "$NET" --network-alias auth --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=32m,mode=1777 \
    -v "$DATA:/data" -v "$site:/srv:ro" -e AUTH_DB_PATH=/data/autolink-auth.sqlite3 \
    -e GOOGLE_CLIENT_ID=qa-client -e MEMBERSHIP_RESTRICTIONS=true "$image" >/dev/null
  docker run -d --name "$WEB" --network "$NET" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=16m,mode=1777 \
    --tmpfs /data:size=16m,uid=10001,gid=10001 --tmpfs /config:size=16m,uid=10001,gid=10001 \
    -p "127.0.0.1:$PORT:8088" -v "$config:/etc/caddy/Caddyfile:ro" -v "$site:/srv:ro" \
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
  local phase="$1" expected_image="$2"
  [[ "$(docker inspect -f '{{.Image}}' "$AUTH")" == "$expected_image" ]]
  [[ "$(docker inspect -f '{{.State.Health.Status}}' "$AUTH")" == healthy ]]
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/autolink/admin/users")" == 401 ]]
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/autolink/supplier/documents")" == 401 ]]
  [[ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/trade/models/unknown-model")" == 404 ]]
  PHASE="$phase" python3 - <<'PY'
import json,os,urllib.request
base='http://127.0.0.1:18184'
def read(path):
    with urllib.request.urlopen(base+path,timeout=10) as r:return r.read()
models=json.loads(read('/autolink/public/models?limit=500'))['data']
brands=json.loads(read('/autolink/public/brands'))['data']
assert len(models)==244 and len(brands)==53
assert b'Geely Monjaro' in read('/trade/models/geely-monjaro-2026')
if os.environ['PHASE']!='rollback':
    assert b'Haval H6' in read('/trade/models/haval-catalog-1')
    assert b'Brand and model information is provided for reference only' in read('/trade/brands/haval')
    assert b'Chinese vehicle sourcing for African importers' in read('/guide/african-importers')
print(json.dumps({'phase':os.environ['PHASE'],'publicModels':len(models),'publicBrands':len(brands)}))
PY
}
start_pair "$QA_AUTH_IMAGE" "$ROOT/site" "$ROOT/Caddyfile"
probe candidate "$QA_AUTH_IMAGE"
python3 "$ROOT/scripts/overseas_seo_http_qa.py" "http://127.0.0.1:$PORT" "$ROOT/isolated-overseas-seo-http.json"
stop_pair
start_pair "$QA_BASELINE_AUTH_IMAGE" "$OLD/site" "$OLD/Caddyfile"
probe rollback "$QA_BASELINE_AUTH_IMAGE"
stop_pair
start_pair "$QA_AUTH_IMAGE" "$ROOT/site" "$ROOT/Caddyfile"
probe restored_candidate "$QA_AUTH_IMAGE"
python3 - "$DATA/autolink-auth.sqlite3" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert db.execute('SELECT count(*) FROM catalog_models').fetchone()[0]>=270
    assert db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0]>=60
PY
echo 'AFME_ISOLATED_QA_PASSED'
