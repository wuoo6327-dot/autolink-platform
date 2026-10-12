#!/usr/bin/env bash
# Round 11 candidate -> current production -> candidate on loopback AMD64.
set -euo pipefail
[[ "$(id -u)" == 0 && "$(uname -m)" == x86_64 ]] || { echo 'Requires root on linux/amd64' >&2; exit 2; }
RELEASE="${QA_RELEASE:?Set the immutable candidate release directory}"
BACKUP="${QA_BACKUP_MANIFEST:?Set a restored, current production backup manifest}"
LOCK="$RELEASE/brand-release-lock.json"
[[ -s "$LOCK" && -s "$BACKUP" ]] || { echo 'Missing release lock or backup' >&2; exit 2; }
readarray -t CFG < <(python3 - "$LOCK" "$BACKUP" <<'PY'
import json,sys
lock=json.load(open(sys.argv[1]));backup=json.load(open(sys.argv[2]))
assert backup['isolatedRestoreVerified']
for value in (lock['authImageID'],lock['oldAuthImageID'],lock['webImageID'],
              lock['baselineRoot'],backup['sqliteBackup'],backup['publicCatalog']):print(value)
PY
)
AUTH_IMAGE="${CFG[0]}"; OLD_AUTH="${CFG[1]}"; WEB_IMAGE="${CFG[2]}"
BASELINE="${CFG[3]}"; DB_SNAPSHOT="${CFG[4]}"; CATALOG="${CFG[5]}"
QA_BASE="/opt/autolink-round11-qa/$(basename "$RELEASE")"
[[ ! -e "$QA_BASE" ]] || { echo 'QA directory already exists; do not reuse a possibly modified database' >&2; exit 2; }
mkdir -p -m 0700 "$QA_BASE/data"
cp --reflink=auto "$DB_SNAPSHOT" "$QA_BASE/data/autolink-auth.sqlite3"
chown -R 10001:10001 "$QA_BASE/data"
NET=autolink-round11-qa-net
AUTH=autolink-round11-qa-auth
WEB=autolink-round11-qa-web
PORT=18088
cleanup() {
  docker rm -f "$WEB" "$AUTH" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf "$QA_BASE"
}
trap cleanup EXIT
docker image inspect "$AUTH_IMAGE" "$OLD_AUTH" "$WEB_IMAGE" >/dev/null
docker network create "$NET" >/dev/null
start_pair() {
  local image="$1" site="$2" caddy="$3"
  docker run -d --name "$AUTH" --network "$NET" --network-alias auth --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=32m,mode=1777 \
    -v "$QA_BASE/data:/data" -v "$site:/srv:ro" -e AUTH_DB_PATH=/data/autolink-auth.sqlite3 \
    -e GOOGLE_CLIENT_ID=qa-client -e MEMBERSHIP_RESTRICTIONS=true "$image" >/dev/null
  docker run -d --name "$WEB" --network "$NET" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --tmpfs /tmp:size=16m,mode=1777 \
    --tmpfs /data:size=16m,uid=10001,gid=10001 --tmpfs /config:size=16m,uid=10001,gid=10001 \
    -p "127.0.0.1:$PORT:8088" -v "$caddy:/etc/caddy/Caddyfile:ro" -v "$site:/srv:ro" \
    -e SITE_ADDRESS=:8088 "$WEB_IMAGE" >/dev/null
  for attempt in $(seq 1 45); do
    if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then return; fi
    sleep 1
  done
  docker logs --tail 40 "$AUTH" >&2 || true
  docker logs --tail 40 "$WEB" >&2 || true
  return 1
}
stop_pair() { docker rm -f "$WEB" "$AUTH" >/dev/null; }
probe() {
  local phase="$1"
  QA_PHASE="$phase" QA_CATALOG="$CATALOG" python3 - <<'PY'
import json,os,urllib.request,urllib.error,xml.etree.ElementTree as ET
base='http://127.0.0.1:18088'; phase=os.environ['QA_PHASE']
def get(path):
    try:
        with urllib.request.urlopen(base+path,timeout=12) as result:return result.status,result.read()
    except urllib.error.HTTPError as error:return error.code,error.read()
saved=json.load(open(os.environ['QA_CATALOG']))
assert get('/healthz')[0]==200
status,models=get('/autolink/public/models?limit=500');assert status==200
status,brands=get('/autolink/public/brands');assert status==200
models=json.loads(models)['data'];brands=json.loads(brands)['data']
assert models==saved['models'] and brands==saved['brands']
assert get('/autolink/admin/users')[0]==401
assert get('/buyer/login')[0]==200
assert get('/supplier')[0]==200 and get('/admin')[0]==200
assert get('/robots.txt')[0]==200
for model in models:
    path=model.get('url') or '/trade/models/'+str(model['id'])
    assert path.startswith('/trade/models/'),(model,'bad model URL')
    status,body=get(path)
    assert status==200 and b'<h1' in body,(path,status)
for brand in brands:
    path='/trade/brands/'+str(brand['id'])
    status,body=get(path)
    assert status==200 and b'<h1' in body,(path,status)
assert get('/trade/models/brand-qa-nonexistent')[0]==404
result={'phase':phase,'publicModels':len(models),'publicBrands':len(brands),'allPublicPages':len(models)+len(brands)}
if phase=='candidate':
    status,home=get('/');assert status==200
    assert b'Chinese Vehicle Sourcing &amp; B2B Supplier Platform' in home
    assert b'About AUTOLINK' in home
    assert b'<div class="home-static">' in home and b'home-static-search' in home
    assert home.count(b'id="autolink-public-jsonld"')==1
    for code in ('zh','ar','ru','kk','uz','ko','fr','sw'):
        status,page=get('/?lang='+code);assert status==200
        expected=('zh-CN' if code=='zh' else code).encode()
        assert b'<html lang="'+expected+b'"' in page
        assert (b'index, follow' if code=='zh' else b'noindex, follow') in page
        assert b'<div class="home-static">' in page
    status,about=get('/about');assert status==200 and b'<h1>About AUTOLINK</h1>' in about
    assert b'does not directly provide vehicle shipping' in about
    assert b'https://autolinkglobal.com/about' in about
    assert get('/about.html')[0]==200  # urllib follows the 308 canonical redirect
    status,xml=get('/sitemaps/static-1.xml');assert status==200
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    urls=[node.text for node in ET.fromstring(xml).findall('.//s:loc',ns)]
    assert urls.count('https://autolinkglobal.com/about')==1
    assert all('/about?lang=' not in url for url in urls)
    assert urls.count('https://autolinkglobal.com/')==1
    assert urls.count('https://autolinkglobal.com/?lang=zh')==1
    assert not any('autolinkglobal.com/?lang='+code in url for code in ('ar','ru','kk','uz','ko','fr','sw'))
    status,root_xml=get('/sitemap.xml');assert status==200
    children=[node.text.rsplit('/',1)[-1] for node in ET.fromstring(root_xml).findall('.//s:loc',ns)]
    assert children==['static-1.xml','brands-1.xml','models-1.xml'],children
    for name in children:
        status,child=get('/sitemaps/'+name);assert status==200
        assert ET.fromstring(child).findall('.//s:url',ns),name
    assert get('/sitemaps/suppliers-1.xml')[0]==404
    assert get('/sitemaps/vehicles-1.xml')[0]==404
    assert get('/trade/models/aeolus-catalog-1')[0]==200
    assert b'noindex' in get('/trade/models/aeolus-catalog-1')[1]
    assert b'Geely Monjaro' in get('/trade/models/geely-monjaro-2026')[1]
    assert b'index, follow' in get('/trade/models/geely-monjaro-2026')[1]
    result['aboutSitemap']=True;result['homepageLanguages']=9;result['nonemptySitemapChildren']=children
else:
    status,home=get('/');assert status==200 and b'Source China. Drive Global.' in home
    result['baselineHomepage']=True
print(json.dumps(result,sort_keys=True))
PY
  docker inspect -f '{{.Name}} {{.Image}} {{.State.Status}} {{.HostConfig.ReadonlyRootfs}}' "$AUTH" "$WEB"
}
start_pair "$AUTH_IMAGE" "$RELEASE/site" "$RELEASE/Caddyfile"
probe candidate
stop_pair
start_pair "$OLD_AUTH" "$BASELINE/site" "$BASELINE/Caddyfile"
probe rollback
stop_pair
start_pair "$AUTH_IMAGE" "$RELEASE/site" "$RELEASE/Caddyfile"
probe candidate
python3 - "$LOCK" "$BACKUP" "$RELEASE/isolated-qa-ok.json" <<'PY'
import datetime,hashlib,json,sys
lock=json.load(open(sys.argv[1]))
digest=hashlib.sha256(open(sys.argv[2],'rb').read()).hexdigest()
data={'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'gitCommit':lock['gitCommit'],'authImageID':lock['authImageID'],
      'backupManifestSHA256':digest,'phases':['candidate','rollback','candidate'],
      'allPublicPagesChecked':True,'result':'pass'}
with open(sys.argv[3],'w') as output:json.dump(data,output,indent=2,sort_keys=True)
PY
echo 'ISOLATED_ROUND11_QA_OK'
