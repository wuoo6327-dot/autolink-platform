"""Run only an isolated QA Compose project. Never starts production deployment."""
import argparse
import hashlib
import json
import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

def run(cmd, log=None, check=True):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if log:
        log.write_text(result.stdout+result.stderr)
    if check and result.returncode:
        raise RuntimeError('Command failed: '+str(cmd[:5])+'; see '+str(log))
    return result

p=argparse.ArgumentParser()
p.add_argument('--root', required=True)
p.add_argument('--native', action='store_true')
args=p.parse_args()
root=Path(args.root).resolve()
assert 'autolink-round3-stage' in str(root) and '/opt/autolink-demo' not in str(root)
assert os.environ.get('AUTOLINK_STAGE_ACK')=='ISOLATED_ROUND3'
assert not (root/'.env').exists()
if args.native:
    assert platform.machine()=='x86_64', 'Requires native AMD64 host'
src=root/'source'
assert src.is_dir() and not src.is_symlink()
# This tree contains sanitized candidate code and public assets only. The outer
# QA root remains private; Docker's non-root bind consumers need traversal.
assert not any(x.name=='.env' for x in src.rglob('*'))
for x in [src,*src.rglob('*')]:
    assert not x.is_symlink()
    x.chmod(0o755 if x.is_dir() else 0o644)
proof=root/'evidence';proof.mkdir(exist_ok=True,mode=0o700)
locked=json.loads((root/'images.json').read_text())
for component in ['auth','caddy']:
    expected=locked[component]
    actual=json.loads(run(['docker','image','inspect',expected['reference']]).stdout)[0]
    assert actual['Architecture']=='amd64' and actual['Descriptor']['digest']==expected['manifestDigest']
    assert actual['Config']['User']=='10001:10001'
tls=root/'tls';tls.mkdir(exist_ok=True,mode=0o750);tls.chmod(0o750)
if not (tls/'server.crt').exists():
    for cmd in [
        ['openssl','req','-x509','-newkey','rsa:2048','-sha256','-nodes','-days','2','-subj','/CN=AUTOLINK ISOLATED QA CA','-keyout',str(tls/'ca.key'),'-out',str(tls/'ca.crt')],
        ['openssl','req','-newkey','rsa:2048','-nodes','-subj','/CN=autolinkglobal.com','-keyout',str(tls/'server.key'),'-out',str(tls/'server.csr')]]:
        run(cmd,proof/'certificate-generation.log')
    (tls/'extensions.txt').write_text('subjectAltName=DNS:autolinkglobal.com\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n')
    run(['openssl','x509','-req','-in',str(tls/'server.csr'),'-CA',str(tls/'ca.crt'),'-CAkey',str(tls/'ca.key'),'-CAcreateserial','-days','2','-sha256','-extfile',str(tls/'extensions.txt'),'-out',str(tls/'server.crt')],proof/'certificate-signing.log')
if os.geteuid()==0:
    os.chown(tls,0,10001)
    os.chown(tls/'server.key',0,10001)
(tls/'server.crt').chmod(0o644)
(tls/'server.key').chmod(0o640)
(tls/'ca.key').chmod(0o600)
# On Docker Desktop bind mounts, retain a test-only readable certificate key.
if os.geteuid()!=0:
    (tls/'server.key').chmod(0o644)
qa_caddy=(src/'Caddyfile').read_text().replace('{$SITE_ADDRESS} {','{$SITE_ADDRESS} {\n\ttls /qa_tls/server.crt /qa_tls/server.key',1)
qa_caddy+='\nhttps://qa.localhost {\n\ttls internal\n\treverse_proxy auth:8080\n}\n'
(root/'Caddyfile.qa').write_text(qa_caddy)
(root/'Caddyfile.qa').chmod(0o644)
env={'AUTH_DB_PATH':'/data/round3.sqlite3','GOOGLE_CLIENT_ID':'offline-qa-client',
     'PLATFORM_ADMIN_EMAIL':'qa-owner@example.invalid','COOKIE_SECURE':'true',
     'APP_URL':'https://autolinkglobal.com','MEMBERSHIP_RESTRICTIONS':'true',
     'MAIL_PROVIDER':'','MAIL_FROM':'','RESEND_API_KEY':'','AUTOLINK_PREFLIGHT_STAGE':'round3',
     'PYTHONPATH':'/app','PYTHONDONTWRITEBYTECODE':'1'}
common={'restart':'no','read_only':True,'cap_drop':['ALL'],
        'security_opt':['no-new-privileges:true'],'pids_limit':128,
        'logging':{'driver':'json-file','options':{'max-size':'5m','max-file':'2'}}}
config={'name':'autolink-qa-round3-native' if args.native else 'autolink-qa-round3-emulated',
 'services':{
  'auth':{**common,'image':locked['auth']['reference'],'cpus':0.5,'mem_limit':'512m',
    'environment':env,'tmpfs':['/tmp:size=32m,mode=1777'],
    'volumes':['qa_auth:/data',str(src/'site')+':/srv:ro',str(src/'scripts')+':/qa_scripts:ro'],'networks':['qa']},
  'web':{**common,'image':locked['caddy']['reference'],'cpus':0.5,'mem_limit':'256m',
    'environment':{'SITE_ADDRESS':'https://autolinkglobal.com'},
    'sysctls':{'net.ipv4.ip_unprivileged_port_start':'0'},
    'ports':['127.0.0.1:19443:443','127.0.0.1:19080:80','127.0.0.1:19443:443/udp'],
    'volumes':[str(root/'Caddyfile.qa')+':/etc/caddy/Caddyfile:ro',str(src/'site')+':/srv:ro',str(tls)+':/qa_tls:ro','qa_caddy:/data','qa_config:/config'],
    'networks':['qa','qa_edge'],'depends_on':['auth']},
  'tests':{**common,'image':locked['auth']['reference'],'profiles':['tests'],'cpus':0.5,'mem_limit':'512m',
    'network_mode':'none','working_dir':'/qa/auth','environment':{'AUTH_DB_PATH':'/tmp/tests.sqlite3','MAIL_PROVIDER':'','RESEND_API_KEY':'','PYTHONDONTWRITEBYTECODE':'1'},
    'tmpfs':['/tmp:size=128m,mode=1777'],'volumes':[str(src/'auth')+':/qa/auth:ro',str(src/'site')+':/qa/site:ro'],
    'command':['python','-m','unittest','discover','-v']}},
 'volumes':{'qa_auth':{},'qa_caddy':{},'qa_config':{}},
 'networks':{'qa':{'internal':True},'qa_edge':{}}}
cf=root/'compose-qa.json';cf.write_text(json.dumps(config,indent=2))
compose=['docker','compose','-f',str(cf)]
prod_names=['autolink-demo-auth-1','autolink-demo-web-1']
def prod_state():
    result=run(['docker','inspect',*prod_names],check=False)
    if result.returncode:return []
    return [{'id':x['Id'],'image':x['Image'],'startedAt':x['State']['StartedAt']} for x in json.loads(result.stdout)]
before=prod_state()
(proof/'production-containers-before.json').write_text(json.dumps(before,indent=2))
run(compose+['config'],proof/'resolved-compose.log')
if not (root/'seeded.marker').exists():
    run(compose+['run','--rm','--no-deps','auth','python','/qa_scripts/preflight_seed.py'],proof/'seed.log')
    (root/'seeded.marker').write_text('synthetic-only')
run(compose+['up','-d','--no-build','auth','web'],proof/'startup.log')
auth_id=run(compose+['ps','-q','auth']).stdout.strip()
web_id=run(compose+['ps','-a','-q','web']).stdout.strip()
for _ in range(60):
    state=json.loads(run(['docker','inspect',auth_id]).stdout)[0]
    if state['State'].get('Health',{}).get('Status')=='healthy':break
    time.sleep(1)
else:raise RuntimeError('auth did not become healthy')
for _ in range(60):
    state=json.loads(run(['docker','inspect',web_id]).stdout)[0]
    if not state['State']['Running']:
        run(compose+['logs','--tail','20','web'],proof/'web-failure.log')
        raise RuntimeError('Caddy exited; see web-failure.log')
    if state['State'].get('Health',{}).get('Status')=='healthy':break
    time.sleep(1)
else:raise RuntimeError('Caddy did not become healthy')
states=json.loads(run(['docker','inspect',auth_id,web_id]).stdout)
for s in states:
    assert s['HostConfig']['Privileged'] is False
    assert all(m.get('Name','').startswith(config['name']+'_') for m in s['Mounts'] if m['Type']=='volume')
    assert all('/opt/autolink-demo' not in m['Source'] and 'docker.sock' not in m['Source'] for m in s['Mounts'])
(proof/'isolation.json').write_text(json.dumps({'nativeAMD64':bool(args.native),'hostArch':platform.machine(),'isolatedProject':config['name'],
    'productionVolumesMounted':False,'authInternalNetwork':True,'outboundMailDisabled':True,'containers':[{'image':s['Image'],'user':s['Config']['User'],'health':s['State'].get('Health',{}).get('Status'),'mounts':s['Mounts'],'memory':s['HostConfig']['Memory'],'nanoCPUs':s['HostConfig']['NanoCpus']} for s in states]},indent=2))
run(['docker','cp',auth_id+':/data/qa-fixtures.json',str(root/'qa-fixtures.json')])
(root/'qa-fixtures.json').chmod(0o600)
run(['docker','cp',web_id+':/data/caddy/pki/authorities/local/root.crt',str(proof/'caddy-internal-ca.crt')])
auto_cmd=['curl','--silent','--show-error','--noproxy','*','--max-time','10','--http2','--cacert',str(proof/'caddy-internal-ca.crt'),'--resolve','qa.localhost:19443:127.0.0.1','-w','\n%{http_code} %{http_version}\n','https://qa.localhost:19443/healthz']
run(auto_cmd,proof/'automatic-tls-before.log')
public_headers=run(['curl','--silent','--show-error','--noproxy','*','--max-time','10','--http2','--cacert',str(tls/'ca.crt'),'--resolve','autolinkglobal.com:19443:127.0.0.1','-I','https://autolinkglobal.com:19443/'],proof/'proxy-headers.log').stdout
assert 'h3=":443"' in public_headers, 'HTTP/3 advertisement must retain public 443'
redirect=run(['curl','--silent','--show-error','--noproxy','*','--max-time','10','-I','-H','Host: autolinkglobal.com','http://127.0.0.1:19080/'],proof/'http-redirect.log').stdout
assert '308' in redirect and 'https://autolinkglobal.com/' in redirect
for name, version in [('TLS12',ssl.TLSVersion.TLSv1_2),('TLS13',ssl.TLSVersion.TLSv1_3)]:
    ctx=ssl.create_default_context(cafile=str(proof/'caddy-internal-ca.crt'))
    ctx.minimum_version=ctx.maximum_version=version
    ctx.set_alpn_protocols(['h2'])
    with socket.create_connection(('127.0.0.1',19443),timeout=10) as raw:
        with ctx.wrap_socket(raw,server_hostname='qa.localhost') as connection:
            assert connection.selected_alpn_protocol()=='h2'
            (proof/(name+'.log')).write_text(json.dumps({'TLS':connection.version(),'ALPN':'h2','certificateValidated':True}))
run([sys.executable,str(src/'scripts/preflight_http.py'),'--ca',str(tls/'ca.crt'),'--fixtures',str(root/'qa-fixtures.json'),'--output',str(proof/'http.json')],proof/'http.log')
run(compose+['run','--rm','tests'],proof/'backend.log')
# Verify soft closure retained all synthetic business records, SQLite stays valid.
code="import json,sqlite3; d=sqlite3.connect('/data/round3.sqlite3'); f=json.load(open('/data/qa-fixtures.json')); assert d.execute('PRAGMA quick_check').fetchone()[0]=='ok'; assert {t:d.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in f['before']}==f['before']; print('preserved synthetic business records, SQLite quick_check OK')"
run(['docker','exec',auth_id,'python','-c',code],proof/'data-preservation.log')
run(compose+['restart','auth','web'],proof/'restart.log')
time.sleep(3)
run(['curl','--silent','--show-error','--noproxy','*','--max-time','10','--http2','--cacert',str(tls/'ca.crt'),'--resolve','autolinkglobal.com:19443:127.0.0.1','-w','\n%{http_code} %{http_version}\n','https://autolinkglobal.com:19443/healthz'],proof/'restart-https.log')
run(auto_cmd,proof/'automatic-tls-after.log')
run(['docker','cp',web_id+':/data/caddy/pki/authorities/local/root.crt',str(proof/'caddy-internal-ca-after.crt')])
assert (proof/'caddy-internal-ca.crt').read_bytes()==(proof/'caddy-internal-ca-after.crt').read_bytes()
after=prod_state();assert before==after,'Production container identity unexpectedly changed'
(proof/'production-containers-after.json').write_text(json.dumps(after,indent=2))
(proof/'complete.json').write_text(json.dumps({'nativeAMD64':bool(args.native),'productionContainersUnchanged':True,'productionDeployed':False,'sourceBasePR2':'edd7408be94e6d1bb928edc310876b67c8776b9c'},indent=2))
print('ROUND3_ISOLATED_PREFLIGHT_COMPLETE '+str(proof))
