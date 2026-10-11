#!/usr/bin/env bash
# Candidate -> current production image -> candidate, all on an isolated loopback port.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ "$(uname -m)" == x86_64 && "$ROOT" == /home/admin/autolink-seo-release-stage-* ]] || { echo 'Requires named AMD64 stage checkout' >&2; exit 2; }
[[ "$(git -C "$ROOT" branch --show-current)" == codex/seo-release-ready-20261012 ]] || { echo 'Wrong SEO release branch' >&2; exit 2; }
CANDIDATE="${QA_AUTH_IMAGE:?Set fixed candidate local image ID}"
BASELINE="${QA_BASELINE_AUTH_IMAGE:?Set current production auth image ID}"
WEB="${QA_WEB_IMAGE:?Set current production web manifest digest}"
BASE_SITE="$ROOT/production-public/site"
BASE_CADDY="$ROOT/production-public/Caddyfile"
[[ -d "$BASE_SITE" && -s "$BASE_CADDY" ]] || { echo 'Missing read-only copy of current production public site/config' >&2; exit 2; }
D=(sudo -n docker)
AUTH=autolink-seo-release-stage-auth
FRONT=autolink-seo-release-stage-web
NET=autolink-seo-release-stage-net
DATA="$ROOT/qa-data"
PORT=18083
stop_pair() { "${D[@]}" rm -f "$FRONT" "$AUTH" >/dev/null 2>&1 || true; }
cleanup() { stop_pair; "${D[@]}" network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${D[@]}" image inspect "$CANDIDATE" "$BASELINE" "$WEB" >/dev/null
"${D[@]}" network create "$NET" >/dev/null
sudo -n install -d -m 0700 "$DATA"
"${D[@]}" run --rm --user 0 --network none --read-only --tmpfs /tmp:size=256m,mode=1777 \
  -v "$ROOT:/workspace:ro" -v "$DATA:/data" -w /workspace -e PYTHONPATH=/workspace/auth \
  "$CANDIDATE" python -c '
import os,sqlite3
from test_current_catalog_seo import CurrentCatalogSEOTests
fixture=CurrentCatalogSEOTests();fixture.setUp()
with fixture.auth.connect() as source, sqlite3.connect("/data/autolink-auth.sqlite3") as target:
    source.backup(target)
os.chown("/data/autolink-auth.sqlite3",10001,10001)
fixture.doCleanups()
'
sudo -n chown 10001:10001 "$DATA"
start_pair() {
  local image="$1" site="$2" config="$3"
  "${D[@]}" run -d --name "$AUTH" --network "$NET" --network-alias auth --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=32m,mode=1777 \
    -v "$DATA:/data" -v "$site:/srv:ro" -e AUTH_DB_PATH=/data/autolink-auth.sqlite3 \
    -e GOOGLE_CLIENT_ID=qa-client -e MEMBERSHIP_RESTRICTIONS=true "$image" >/dev/null
  "${D[@]}" run -d --name "$FRONT" --network "$NET" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=16m,mode=1777 \
    --tmpfs /data:size=16m,uid=10001,gid=10001 --tmpfs /config:size=16m,uid=10001,gid=10001 \
    -p "127.0.0.1:$PORT:8088" -v "$config:/etc/caddy/Caddyfile:ro" -v "$site:/srv:ro" \
    -e SITE_ADDRESS=:8088 "$WEB" >/dev/null
  for attempt in $(seq 1 45); do
    if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then return; fi
    sleep 1
  done
  "${D[@]}" logs --tail 30 "$AUTH" "$FRONT" >&2
  return 1
}
probe() {
  local phase="$1"
  PHASE="$phase" python3 - <<'PY'
import json,os,urllib.request,urllib.error,xml.etree.ElementTree as ET
base='http://127.0.0.1:18083'; phase=os.environ['PHASE']
def get(path):
    try:
        with urllib.request.urlopen(base+path,timeout=15) as response:return response.status,response.read()
    except urllib.error.HTTPError as error:return error.code,error.read()
health,_=get('/healthz'); models_status,models=get('/autolink/public/models?limit=500')
brand_status,brands=get('/autolink/public/brands'); admin,_=get('/autolink/admin/users')
home,_=get('/'); detail_status,detail=get('/trade/models/geely-monjaro-2026')
assert (health,models_status,brand_status,admin,home,detail_status)==(200,200,200,401,200,200)
assert len(json.loads(models)['data'])==244 and len(json.loads(brands)['data'])==53
result={'phase':phase,'health':health,'models':244,'brands':53,'admin':admin,'home':home,'detail':detail_status}
if phase!='rollback':
    assert b'Geely Monjaro' in detail and b'index, follow' in detail
    unknown,_=get('/trade/models/not-a-model'); assert unknown==404
    sitemap_status,sitemap=get('/sitemaps/models-1.xml');assert sitemap_status==200
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    result['sitemapUrls']=len(ET.fromstring(sitemap).findall('.//s:loc',ns))
    assert result['sitemapUrls']==199
print(json.dumps(result,sort_keys=True))
PY
}
start_pair "$CANDIDATE" "$ROOT/site" "$ROOT/Caddyfile"
probe candidate
stop_pair
start_pair "$BASELINE" "$BASE_SITE" "$BASE_CADDY"
probe rollback
stop_pair
start_pair "$CANDIDATE" "$ROOT/site" "$ROOT/Caddyfile"
probe restore
