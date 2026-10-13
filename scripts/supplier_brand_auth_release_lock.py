"""Freeze the reviewed supplier authorization overlay and native AMD64 image."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess

BASE = Path('/opt/autolink-releases/16f65c8-afme-20261014')
ROOT = Path('/opt/autolink-releases/brand-auth-20261014')
OLD_AUTH = 'sha256:dd5523c9fe02eab7b7915c90444c95fef1b36a0d99a557b7fda8b0c9f423e148'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'
SITE = {'admin/app.js', 'supplier/app.js'}
AUTH_CHANGED = {'Dockerfile', 'app.py', 'brand_authorization_service.py',
                'seo_service.py', 'trade_service.py', 'test_brand_authorization.py'}
SOURCES = {'app.py', 'brand_authorization_service.py', 'seo_service.py', 'trade_service.py'}
FILES = {'.env', 'Caddyfile', 'compose.yaml', 'git-commit.txt',
         'scripts/backup_production_sqlite.py', 'scripts/brand_identity_cutover.py',
         'scripts/notification_cutover.py', 'scripts/overseas_seo_http_qa.py',
         'scripts/prepare_notification_backup.py', 'scripts/supplier_brand_auth_cutover.py',
         'scripts/supplier_brand_auth_isolated_qa.sh',
         'scripts/supplier_brand_auth_native_build.sh',
         'scripts/supplier_brand_auth_prepare_backup.py',
         'scripts/supplier_brand_auth_release_lock.py'}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path) for path in root.rglob('*')
            if path.is_file() and '__pycache__' not in path.relative_to(root).parts
            and not path.name.startswith('._')}


def main():
    if os.geteuid() or platform.machine() != 'x86_64':
        raise RuntimeError('Native AMD64 root required')
    commit = (ROOT / 'git-commit.txt').read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise RuntimeError('Invalid Git commit identity')
    old_site, new_site = inventory(BASE / 'site'), inventory(ROOT / 'site')
    changed = {name for name in old_site.keys() | new_site.keys()
               if old_site.get(name) != new_site.get(name)}
    if changed != SITE or old_site['index.html'] != new_site['index.html']:
        raise RuntimeError('Site changed outside reviewed authorization UI')
    old_auth, new_auth = inventory(BASE / 'auth'), inventory(ROOT / 'auth')
    changed_auth = {name for name in old_auth.keys() | new_auth.keys()
                    if old_auth.get(name) != new_auth.get(name)}
    if changed_auth != AUTH_CHANGED:
        raise RuntimeError('Auth source changed outside reviewed scope: ' + str(sorted(changed_auth)))
    image_id = (ROOT / 'brand-auth-image-id.txt').read_text().strip()
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image_id]))[0]
    if image['Id'] != image_id or image['Architecture'] != 'amd64':
        raise RuntimeError('Candidate image identity or architecture differs')
    for name in SOURCES:
        embedded = subprocess.check_output(['docker', 'run', '--rm', '--network', 'none',
            '--read-only', image_id, 'sha256sum', '/app/' + name], text=True).split()[0]
        if embedded != sha(ROOT / 'auth' / name):
            raise RuntimeError('Image source differs: ' + name)
    for name in FILES:
        if not (ROOT / name).is_file():
            raise RuntimeError('Release file missing: ' + name)
    if ((ROOT / 'native-container-tests.exit').read_text().strip() != '0'
            or (ROOT / 'isolated-qa.exit').read_text().strip() != '0'
            or (ROOT / 'brand-auth-trivy.exit').read_text().strip() != '0'):
        raise RuntimeError('Native tests, rollback or image scan not passed')
    if not json.loads((ROOT / 'isolated-overseas-seo-http.json').read_text()).get('pass'):
        raise RuntimeError('Public SEO crawl did not pass')
    scan = json.loads((ROOT / 'brand-auth-trivy.json').read_text())
    if any(v.get('Severity') in ('HIGH', 'CRITICAL') for r in scan.get('Results', [])
           for v in r.get('Vulnerabilities', []) or []) or \
       any(r.get('Secrets') for r in scan.get('Results', [])):
        raise RuntimeError('Blocking image scan findings')
    result = {'gitCommit': commit, 'releaseRoot': str(ROOT), 'baselineRoot': str(BASE),
              'authImageId': image_id, 'oldAuthImageId': OLD_AUTH, 'webImageId': WEB,
              'authArchiveSHA256': sha(ROOT / 'brand-auth-image.tar'),
              'authSources': {name: sha(ROOT / 'auth' / name) for name in sorted(SOURCES)},
              'siteFiles': {name: new_site[name] for name in sorted(SITE)},
              'releaseFiles': {name: sha(ROOT / name) for name in sorted(FILES)}}
    output = ROOT / 'brand-auth-release-lock.json'
    if output.exists():
        raise RuntimeError('Release lock exists; do not overwrite')
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({'releaseLock': str(output), 'gitCommit': commit,
        'authImageId': image_id, 'authArchiveSHA256': result['authArchiveSHA256']}, sort_keys=True))


if __name__ == '__main__':
    main()
