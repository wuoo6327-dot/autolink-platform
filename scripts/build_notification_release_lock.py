"""Lock the reviewed notification overlay and native AMD64 image."""

import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path


OLD = Path('/opt/autolink-releases/7fefb90-account-role-20261013')
RELEASE = Path('/opt/autolink-releases/c215c54-notifications-20261014')
AUTH_OLD = 'sha256:8c14559850ac1ebe5d778415adb6e1b5777e75b5424fe8677ae402ada81242e0'
AUTH_NEW = 'sha256:23e88a9bc8b84bd5baa07f8ecb2a970ca99a90b5404b887567f6ed651a080052'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'
COMMIT = 'c215c54ea98e2f9ac00b34fc432a69d2b661d99e'
SITE = {
    'assets/business-page-bootstrap.mjs', 'assets/notification-indicator.mjs',
    'buyer/app.js', 'buyer/buyer.css', 'buyer/index.html',
    'supplier/app.js', 'supplier/bootstrap.mjs', 'supplier/index.html',
}
AUTH = {'app.py', 'platform_service.py'}
FILES = {
    '.env', 'Caddyfile', 'compose.yaml', 'scripts/notification_cutover.py',
    'scripts/notification_isolated_qa.py', 'scripts/prepare_notification_backup.py',
    'scripts/backup_production_sqlite.py', 'scripts/brand_identity_cutover.py',
}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path)
            for path in root.rglob('*') if path.is_file()}


def main():
    if os.geteuid() or platform.machine() != 'x86_64':
        raise RuntimeError('Requires root on the reviewed native AMD64 host')
    before, after = inventory(OLD / 'site'), inventory(RELEASE / 'site')
    changed = {name for name in before.keys() | after.keys()
               if before.get(name) != after.get(name)}
    if changed != SITE:
        raise RuntimeError(f'Unexpected site overlay: {sorted(changed)}')
    image = json.loads(subprocess.check_output(['docker', 'image', 'inspect', AUTH_NEW]))[0]
    if image['Id'] != AUTH_NEW or image['Architecture'] != 'amd64':
        raise RuntimeError('Candidate Auth image identity differs')
    for name in AUTH:
        embedded = subprocess.check_output(
            ['docker', 'run', '--rm', '--network', 'none', '--read-only', AUTH_NEW,
             'sha256sum', '/app/' + name], text=True).split()[0]
        if embedded != sha(RELEASE / 'auth' / name):
            raise RuntimeError(f'Candidate image differs from staged source: {name}')
    archive = RELEASE / 'notification-auth-amd64.tar'
    if not archive.is_file():
        raise RuntimeError('Immutable Auth archive is missing')
    manifest = {
        'gitCommit': COMMIT, 'releaseRoot': str(RELEASE), 'baselineRoot': str(OLD),
        'authImageId': AUTH_NEW, 'oldAuthImageId': AUTH_OLD, 'webImageId': WEB,
        'authArchiveSHA256': sha(archive),
        'authSources': {name: sha(RELEASE / 'auth' / name) for name in sorted(AUTH)},
        'siteFiles': {name: after[name] for name in sorted(SITE)},
        'releaseFiles': {name: sha(RELEASE / name) for name in sorted(FILES)},
    }
    output = RELEASE / 'notification-release-lock.json'
    if output.exists():
        raise RuntimeError('Release lock already exists')
    output.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    output.chmod(0o600)
    print(json.dumps({'releaseLock': str(output), 'gitCommit': COMMIT,
                      'authImageId': AUTH_NEW, 'siteFiles': len(SITE)}, sort_keys=True))


if __name__ == '__main__':
    main()
