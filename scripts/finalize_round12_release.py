"""Freeze an AMD64 Round 12 candidate and its local immutable image archive."""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


BASELINE = Path('/opt/autolink-releases/52c6934-round11-20261012')
OLD_AUTH = 'sha256:5dfea447ad82555952ec7cb037b3e877bf361cf162267f7b82e16822f8736049'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True, timeout=60).strip()


def container(name):
    result = json.loads(run('docker', 'inspect', name))
    if len(result) != 1:
        raise RuntimeError(f'Missing production container: {name}')
    return result[0]


def prepare(source, release, auth_image):
    source, release = Path(source).resolve(), Path(release).resolve()
    if os.geteuid() != 0 or platform.machine() != 'x86_64':
        raise RuntimeError('Requires root on the reviewed linux/amd64 host')
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', auth_image):
        raise RuntimeError('Use a fixed Docker image ID')
    manifest_file = release / 'round12-overlay-manifest.json'
    if not manifest_file.is_file() or any((release / name).exists() for name in ('compose.yaml', '.env', 'brand-release-lock.json')):
        raise RuntimeError('Candidate overlay missing or already finalized')
    if run('git', '-C', str(source), 'status', '--porcelain'):
        raise RuntimeError('Source checkout is not clean')
    commit = run('git', '-C', str(source), 'rev-parse', 'HEAD')
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise RuntimeError('Invalid Git commit identity')
    auth, web = container('autolink-demo-auth-1'), container('autolink-demo-web-1')
    if auth['Image'] != OLD_AUTH or web['Image'] != WEB:
        raise RuntimeError('Running image IDs differ from approved baseline')
    mounts = {entry['Destination']: entry['Source'] for entry in web['Mounts']}
    if mounts.get('/srv') != str(BASELINE / 'site') or mounts.get('/etc/caddy/Caddyfile') != str(BASELINE / 'Caddyfile'):
        raise RuntimeError('Running site and Caddy mounts changed')
    image = json.loads(run('docker', 'image', 'inspect', auth_image))[0]
    if image['Id'] != auth_image or image['Architecture'] != 'amd64':
        raise RuntimeError('Candidate image identity or architecture failed')
    trade_hash = run('docker', 'run', '--rm', '--network', 'none', '--read-only',
                     auth_image, 'sha256sum', '/app/trade_service.py').split()[0]
    if trade_hash != sha(source / 'auth/trade_service.py'):
        raise RuntimeError('Auth image does not contain reviewed Sitemap code')
    overlay = json.loads(manifest_file.read_text())
    if overlay['caddySHA256'] != sha(release / 'Caddyfile') or overlay['sourceTradeServiceSHA256'] != trade_hash:
        raise RuntimeError('Overlay or image source changed')
    shutil.copy2(BASELINE / 'compose.yaml', release / 'compose.yaml')
    environment = (BASELINE / '.env').read_text()
    pattern = re.compile(r'^AUTOLINK_AUTH_IMAGE=.*$', re.MULTILINE)
    if len(pattern.findall(environment)) != 1:
        raise RuntimeError('Expected one fixed Auth image setting')
    (release / '.env').write_text(pattern.sub('AUTOLINK_AUTH_IMAGE=' + auth_image, environment))
    os.chmod(release / '.env', 0o600)
    archive = release / 'images/auth-amd64.tar'
    archive.parent.mkdir(mode=0o700)
    subprocess.run(['docker', 'save', '--output', str(archive), auth_image], check=True, timeout=240)
    if archive.stat().st_size < 1024:
        raise RuntimeError('Candidate Auth archive is incomplete')
    lock = {
        'gitCommit': commit,
        'sourceRoot': str(source),
        'releaseRoot': str(release),
        'baselineRoot': str(BASELINE),
        'authImageID': auth_image,
        'oldAuthImageID': OLD_AUTH,
        'webImageID': WEB,
        'authArchive': str(archive),
        'authArchiveSHA256': sha(archive),
        'authTradeServiceSHA256': trade_hash,
        'overlayManifestSHA256': sha(manifest_file),
        'siteIndexSHA256': sha(release / 'site/index.html'),
        'caddySHA256': sha(release / 'Caddyfile'),
        'composeSHA256': sha(release / 'compose.yaml'),
        'environmentSHA256': sha(release / '.env'),
    }
    (release / 'brand-release-lock.json').write_text(json.dumps(lock, sort_keys=True, indent=2) + '\n')
    return {key: value for key, value in lock.items() if key not in ('sourceRoot', 'releaseRoot', 'baselineRoot')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--auth-image', required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.source, arguments.release, arguments.auth_image), sort_keys=True))
