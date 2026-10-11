#!/usr/bin/env bash
# Run the candidate with public-only fixture data, isolated Docker names, and no production volumes.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ "$(uname -m)" == x86_64 && "$ROOT" == /home/admin/autolink-global-seo-qa-* ]] || { echo 'Requires the named AMD64 QA checkout' >&2; exit 2; }
[[ "$(git -C "$ROOT" branch --show-current)" == codex/global-seo-20261012 ]] || { echo 'Wrong candidate branch' >&2; exit 2; }
D=(sudo -n docker)
AUTH_IMAGE="${QA_AUTH_IMAGE:-autolink-global-seo-auth:bc0649a}"
WEB_IMAGE="${QA_WEB_IMAGE:-autolink-round3-caddy@sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb}"
NETWORK=autolink-global-seo-qa-net
AUTH=autolink-global-seo-qa-auth
WEB=autolink-global-seo-qa-web
DATA="$ROOT/qa-data"
cleanup() { "${D[@]}" rm -f "$WEB" "$AUTH" >/dev/null 2>&1 || true; "${D[@]}" network rm "$NETWORK" >/dev/null 2>&1 || true; }
trap cleanup EXIT
"${D[@]}" image inspect "$AUTH_IMAGE" "$WEB_IMAGE" >/dev/null
"${D[@]}" network create "$NETWORK" >/dev/null
sudo -n install -d -m 0700 "$DATA"
"${D[@]}" run --rm --user 0 --network none --read-only --tmpfs /tmp:size=256m,mode=1777 \
  -v "$ROOT:/workspace:ro" -v "$DATA:/data" -w /workspace -e PYTHONPATH=/workspace/auth \
  "$AUTH_IMAGE" python -c '
import os,sqlite3
from test_current_catalog_seo import CurrentCatalogSEOTests
fixture=CurrentCatalogSEOTests();fixture.setUp()
with fixture.auth.connect() as source, sqlite3.connect("/data/autolink-auth.sqlite3") as target:
    source.backup(target)
os.chown("/data/autolink-auth.sqlite3",10001,10001)
fixture.doCleanups()
'
sudo -n chown 10001:10001 "$DATA"
"${D[@]}" run -d --name "$AUTH" --network "$NETWORK" --network-alias auth --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:size=32m,mode=1777 \
  -v "$DATA:/data" -v "$ROOT/site:/srv:ro" -e AUTH_DB_PATH=/data/autolink-auth.sqlite3 \
  -e GOOGLE_CLIENT_ID=qa-client -e MEMBERSHIP_RESTRICTIONS=true "$AUTH_IMAGE" >/dev/null
"${D[@]}" run -d --name "$WEB" --network "$NETWORK" --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:size=16m,mode=1777 \
  --tmpfs /data:size=16m,uid=10001,gid=10001 --tmpfs /config:size=16m,uid=10001,gid=10001 \
  -p 127.0.0.1:18082:8088 -v "$ROOT/Caddyfile:/etc/caddy/Caddyfile:ro" -v "$ROOT/site:/srv:ro" \
  -e SITE_ADDRESS=:8088 "$WEB_IMAGE" >/dev/null
for attempt in $(seq 1 30); do if curl -fsS http://127.0.0.1:18082/healthz >/dev/null; then break; fi; sleep 1; done
python3 - <<'PY'
import json,urllib.request,urllib.error,xml.etree.ElementTree as ET
base='http://127.0.0.1:18082'
def get(path):
    try:
        with urllib.request.urlopen(base+path,timeout=10) as response:return response.status,response.read()
    except urllib.error.HTTPError as error:return error.code,error.read()
checks={}
for path in ['/healthz','/robots.txt','/trade/models/geely-monjaro-2026',
             '/trade/models/zeekr-9x-2026?lang=zh','/trade/models/byd-shark',
             '/trade/brands/geely','/trade/models/not-a-model','/autolink/admin/users',
             '/guide/vehicle-sourcing?lang=zh']:
    status,body=get(path);checks[path]=status
    assert status== (404 if path.endswith('not-a-model') else 401 if path.endswith('admin/users') else 200),(path,status)
status,body=get('/autolink/public/models?limit=500');assert status==200 and len(json.loads(body)['data'])==244
status,body=get('/autolink/public/brands');assert status==200 and len(json.loads(body)['data'])==53
status,body=get('/sitemaps/models-1.xml');assert status==200
ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
assert len(ET.fromstring(body).findall('.//s:loc',ns))==205
print(json.dumps({'result':'pass','catalogModels':244,'brands':53,'indexableModelUrls':205,'httpStatuses':checks},sort_keys=True))
PY
"${D[@]}" inspect "$AUTH" "$WEB" --format '{{.Name}} {{.State.Health.Status}} {{.HostConfig.ReadonlyRootfs}}' || true
