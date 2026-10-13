"""Pin the exact SEO overlay and native AMD64 image before production cutover."""
import hashlib
import json
import os
import platform
import re
import subprocess
from pathlib import Path

OLD = Path('/opt/autolink-releases/c215c54-notifications-20261014')
RELEASE = Path('/opt/autolink-releases/16f65c8-afme-20261014')
AUTH_OLD = 'sha256:23e88a9bc8b84bd5baa07f8ecb2a970ca99a90b5404b887567f6ed651a080052'
AUTH_NEW = 'sha256:dd5523c9fe02eab7b7915c90444c95fef1b36a0d99a557b7fda8b0c9f423e148'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'
SITE = {'guide/african-importers.fallback.html','guide/african-importers.html',
    'guide/middle-east-importers.ar.html','guide/vehicle-sourcing.html',
    'locales/seo-brand-en-reviewed.json','locales/seo-model-en-reviewed.json'}
AUTH = {'seo_service.py','trade_service.py'}
FILES = {'.env','Caddyfile','compose.yaml',
    'git-commit.txt',
    'scripts/afme_cutover.py','scripts/afme_prepare_backup.py',
    'scripts/afme_isolated_qa.sh','scripts/afme_release_lock.py',
    'scripts/notification_cutover.py','scripts/prepare_notification_backup.py',
    'scripts/brand_identity_cutover.py','scripts/backup_production_sqlite.py'}

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()

def inventory(root):
    return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.relative_to(root).parts}

def main():
    if os.geteuid() or platform.machine()!='x86_64':
        raise RuntimeError('Native AMD64 root required')
    commit=(RELEASE/'git-commit.txt').read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{40}',commit):
        raise RuntimeError('Release Git commit identity missing')
    previous,current=inventory(OLD/'site'),inventory(RELEASE/'site')
    changed={name for name in previous.keys()|current.keys() if previous.get(name)!=current.get(name)}
    if changed!=SITE or previous['index.html']!=current['index.html']:
        raise RuntimeError('Site overlay differs from reviewed SEO scope')
    before,after=inventory(OLD/'auth'),inventory(RELEASE/'auth')
    changed_auth={name for name in before.keys()|after.keys() if before.get(name)!=after.get(name)}
    if changed_auth!={'seo_service.py','trade_service.py','test_catalog.py',
        'test_current_catalog_seo.py','test_overseas_seo.py','test_seo.py',
        'test_seo_quality.py','test_trade.py'}:
        raise RuntimeError('Auth staging differs from reviewed SEO scope')
    image=json.loads(subprocess.check_output(['docker','image','inspect',AUTH_NEW]))[0]
    if image['Id']!=AUTH_NEW or image['Architecture']!='amd64':
        raise RuntimeError('Candidate image identity or architecture differs')
    for name in AUTH:
        embedded=subprocess.check_output(['docker','run','--rm','--network','none',
            '--read-only',AUTH_NEW,'sha256sum','/app/'+name],text=True).split()[0]
        if embedded!=sha(RELEASE/'auth'/name):
            raise RuntimeError('Image source hash differs: '+name)
    if (RELEASE/'native-container-tests.exit').read_text().strip()!='0' or \
            (RELEASE/'isolated-qa.exit').read_text().strip()!='0' or \
            (RELEASE/'afme-trivy.exit').read_text().strip()!='0':
        raise RuntimeError('Native tests, isolated QA or image scan not passed')
    audit=json.loads((RELEASE/'isolated-overseas-seo-http.json').read_text())
    if not audit.get('pass'):
        raise RuntimeError('Full public HTTP crawl did not pass')
    scan=json.loads((RELEASE/'afme-trivy.json').read_text())
    if any(item.get('Severity') in ('HIGH','CRITICAL') for result in scan.get('Results',[])
           for item in result.get('Vulnerabilities',[]) or []) or \
       any(result.get('Secrets') for result in scan.get('Results',[])):
        raise RuntimeError('Candidate image scan has blocking findings')
    archive=RELEASE/'afme-auth-amd64.tar'
    if not archive.is_file():
        raise RuntimeError('Candidate image archive missing')
    for name in FILES:
        if not (RELEASE/name).is_file():
            raise RuntimeError('Release file missing: '+name)
    lock={'gitCommit':commit,'releaseRoot':str(RELEASE),'baselineRoot':str(OLD),
        'authImageId':AUTH_NEW,'oldAuthImageId':AUTH_OLD,'webImageId':WEB,
        'authArchiveSHA256':sha(archive),
        'authSources':{name:sha(RELEASE/'auth'/name) for name in sorted(AUTH)},
        'siteFiles':{name:current[name] for name in sorted(SITE)},
        'releaseFiles':{name:sha(RELEASE/name) for name in sorted(FILES)}}
    output=RELEASE/'afme-release-lock.json'
    if output.exists():
        raise RuntimeError('Release lock already exists')
    output.write_text(json.dumps(lock,sort_keys=True,indent=2)+'\n')
    output.chmod(0o600)
    print(json.dumps({'releaseLock':str(output),'gitCommit':commit,
        'authImageId':AUTH_NEW,'siteFiles':len(SITE)},sort_keys=True))

if __name__=='__main__':
    main()
