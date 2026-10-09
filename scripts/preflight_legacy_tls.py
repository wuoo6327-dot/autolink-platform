"""Test a PRIVATE COPY of the existing certificate state on loopback only.
No production volume mount, certificate renewal or real-account request.
"""
import argparse,hashlib,json,os,pathlib,shutil,ssl,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args()
r=pathlib.Path(a.root).resolve()
assert os.geteuid()==0 and 'autolink-round3-stage-native' in str(r)
assert os.environ.get('AUTOLINK_STAGE_ACK')=='ISOLATED_ROUND3'
image=json.loads((r/'images.json').read_text())['caddy']['reference']
original=r/'private-production-backup/caddy-data.tar.gz.restore'
assert original.is_dir()
copy=r/'private-production-backup/legacy-caddy-copy'
assert not copy.exists(),'Keep previous test evidence intact'
shutil.copytree(original,copy)
for x in [copy,*copy.rglob('*')]:
    assert not x.is_symlink();os.chown(x,10001,10001)
    if x.is_dir():x.chmod(0o750)
certs=list(copy.glob('caddy/certificates/*/autolinkglobal.com/*.crt'))
assert len(certs)==1, 'Requires unambiguous existing production certificate'
cert=certs[0];key=cert.with_suffix('.key');assert key.is_file()
relative=lambda x:'/data/'+str(x.relative_to(copy))
text=(r/'source/Caddyfile').read_text().replace('{$SITE_ADDRESS} {','{$SITE_ADDRESS} {\n\ttls '+relative(cert)+' '+relative(key),1)
conf=r/'Caddyfile.legacy.qa';conf.write_text(text);conf.chmod(0o644)
name='autolink-qa-round3-legacy-tls'
config_volume='autolink-qa-round3-native_qa_legacy_config'
cmd=['docker','create','--name',name,'--network','autolink-qa-round3-native_qa_edge','--cpus','0.5','--memory','256m','--pids-limit','128','--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only','--sysctl','net.ipv4.ip_unprivileged_port_start=0','-p','127.0.0.1:19444:443','-e','SITE_ADDRESS=https://autolinkglobal.com','-v',str(conf)+':/etc/caddy/Caddyfile:ro','-v',str(r/'source/site')+':/srv:ro','-v',str(copy)+':/data','-v',config_volume+':/config',image]
proof=r/'evidence'
subprocess.run(cmd,check=True,capture_output=True)
subprocess.run(['docker','network','connect','autolink-qa-round3-native_qa',name],check=True)
try:
    subprocess.run(['docker','start',name],check=True,capture_output=True)
    for _ in range(30):
        state=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
        if not state['State']['Running']:raise RuntimeError('Copied-certificate Caddy exited')
        if state['State'].get('Health',{}).get('Status')=='healthy':break
        time.sleep(1)
    else:raise RuntimeError('Copied-certificate Caddy health failed')
    curl=['curl','--silent','--show-error','--noproxy','*','--max-time','10','--http2','--resolve','autolinkglobal.com:19444:127.0.0.1','-w','\n%{http_code} %{http_version}\n','https://autolinkglobal.com:19444/healthz']
    result=subprocess.run(curl,capture_output=True,text=True,check=True)
    assert result.stdout.endswith('200 2\n') and '"status"' in result.stdout
    (proof/'legacy-tls-https.log').write_text(result.stdout+result.stderr)
    metadata=ssl._ssl._test_decode_cert(str(cert))
    (proof/'legacy-tls.json').write_text(json.dumps({'existingCertificateLoaded':True,'defaultPublicCAValidation':True,'HTTP2':True,'nonRootUID':10001,'certificateNotAfter':metadata['notAfter'],'copiedStateOwnershipMigrationTested':True,'productionCertificateVolumeModified':False,'ACMERenewalTested':False},indent=2))
    print('EXISTING_CERTIFICATE_COPY_DEFAULT_CA_TLS_HTTP2_PROXY_VERIFIED',flush=True)
finally:
    result=subprocess.run(['docker','logs','--tail','25',name],capture_output=True,text=True)
    (proof/'legacy-tls-caddy.log').write_text(result.stdout+result.stderr)
    subprocess.run(['docker','stop',name],check=True,capture_output=True)
