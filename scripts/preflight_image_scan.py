"""Full, unsuppressed native AMD64 archive scans; no Docker socket or real DB mount."""
import argparse,json,os,platform,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args()
r=Path(a.root).resolve()
assert 'autolink-round3-stage-native' in str(r) and os.environ.get('AUTOLINK_STAGE_ACK')=='ISOLATED_ROUND3'
assert platform.machine()=='x86_64'
out=r/'evidence'/'trivy';out.mkdir(mode=0o700,exist_ok=True)
cache=r/'scanner-cache';cache.mkdir(mode=0o700,exist_ok=True)
scanner='aquasec/trivy@sha256:9db099105405c648166e6b94155eb32f8da12673cf1f455207f7385cc9a77283'
subprocess.run(['docker','pull','--platform','linux/amd64',scanner],check=True)
summary={}
for label,path in [('candidate-auth',r/'auth-image.tar'),('candidate-caddy',r/'caddy-image.tar'),('production-auth',r/'private-production-backup/prod-auth-image.tar'),('production-caddy',r/'private-production-backup/prod-caddy-image.tar')]:
    assert path.is_file()
    cmd=['docker','run','--rm','--platform','linux/amd64','--cpus','0.5','--memory','512m','--pids-limit','128','--cap-drop','ALL','--security-opt','no-new-privileges:true',
    '-v',str(path)+':/input/image.tar:ro','-v',str(out)+':/output','-v',str(cache)+':/root/.cache/trivy',scanner,
    'image','--scanners','vuln','--ignorefile','/dev/null','--format','json','--output','/output/'+label+'.json','--input','/input/image.tar']
    with (out/(label+'.log')).open('w') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
    report=json.loads((out/(label+'.json')).read_text());findings=[v for x in report.get('Results',[]) for v in x.get('Vulnerabilities',[])]
    summary[label]={severity:sum(v['Severity']==severity for v in findings) for severity in ['CRITICAL','HIGH','MEDIUM','LOW','UNKNOWN']}
    (out/'summary.json').write_text(json.dumps(summary,indent=2));print(label,json.dumps(summary[label]),flush=True)
print('NATIVE_AMD64_FULL_IMAGE_SCANS_COMPLETE')
