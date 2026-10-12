"""Freeze a brand SEO release after the AMD64 Auth image has been built.

Run as root on the production host. This prepares a new directory and image
archive, but does not alter any running container, database, or volume.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


BASELINE = Path('/opt/autolink-releases/5725b8b-seo-20261012')
OLD_AUTH = 'sha256:0fcb1f1c73a0d6b7b23c81355a9d48ca1e82e514705011d26c63a7cd5aaff815'
WEB_IMAGE = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect(name):
    result = json.loads(run('docker', 'inspect', name))
    if len(result) != 1:
        raise RuntimeError(f'Expected one container: {name}')
    return result[0]


def prepare(source, release, image):
    source, release = Path(source).resolve(), Path(release).resolve()
    if os.geteuid() != 0 or platform.machine() != 'x86_64':
        raise RuntimeError('Requires root on the linux/amd64 production host')
    if not image.startswith('sha256:') or len(image) != 71:
        raise RuntimeError('Use a fixed Docker image ID, not a mutable tag')
    if not release.is_dir() or not (release / 'brand-overlay-manifest.json').is_file():
        raise RuntimeError('Verified new site overlay is missing')
    if any((release / name).exists() for name in ('compose.yaml', '.env', 'brand-release-lock.json')):
        raise RuntimeError('Release was already finalized')
    if run('git', '-C', str(source), 'status', '--porcelain'):
        raise RuntimeError('Source checkout must be clean')
    commit = run('git', '-C', str(source), 'rev-parse', 'HEAD')
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise RuntimeError('Source commit is not fixed')
    auth, web = inspect('autolink-demo-auth-1'), inspect('autolink-demo-web-1')
    if auth['Image'] != OLD_AUTH or web['Image'] != WEB_IMAGE:
        raise RuntimeError('Running production image differs from reviewed baseline')
    mounts = {item['Destination']: item['Source'] for item in web['Mounts']}
    if mounts.get('/srv') != str(BASELINE / 'site') or mounts.get('/etc/caddy/Caddyfile') != str(BASELINE / 'Caddyfile'):
        raise RuntimeError('Running production files differ from reviewed baseline')
    information = json.loads(run('docker', 'image', 'inspect', image))[0]
    if information['Id'] != image or information['Architecture'] != 'amd64':
        raise RuntimeError('Candidate Auth image identity or architecture failed')
    actual_trade_hash = run('docker', 'run', '--rm', '--network', 'none', '--read-only', image,
                            'sha256sum', '/app/trade_service.py').split()[0]
    if actual_trade_hash != sha(source / 'auth/trade_service.py'):
        raise RuntimeError('Candidate Auth image does not contain reviewed trade_service.py')
    overlay = json.loads((release / 'brand-overlay-manifest.json').read_text())
    if overlay['caddySHA256'] != sha(release / 'Caddyfile'):
        raise RuntimeError('Caddyfile changed after overlay construction')
    shutil.copy2(BASELINE / 'compose.yaml', release / 'compose.yaml')
    original_env = (BASELINE / '.env').read_text()
    pattern = re.compile(r'^AUTOLINK_AUTH_IMAGE=.*$', re.MULTILINE)
    if len(pattern.findall(original_env)) != 1:
        raise RuntimeError('Expected one Auth image setting in the running .env')
    final_env = pattern.sub('AUTOLINK_AUTH_IMAGE=' + image, original_env)
    (release / '.env').write_text(final_env)
    os.chmod(release / '.env', 0o600)
    image_dir = release / 'images'
    image_dir.mkdir(mode=0o700)
    archive = image_dir / 'auth-amd64.tar'
    subprocess.run(['docker', 'save', '--output', str(archive), image], check=True, timeout=240)
    if archive.stat().st_size < 1024:
        raise RuntimeError('Candidate Auth image archive is incomplete')
    lock = {
        'gitCommit': commit,
        'sourceRoot': str(source),
        'releaseRoot': str(release),
        'baselineRoot': str(BASELINE),
        'authImageID': image,
        'webImageID': WEB_IMAGE,
        'oldAuthImageID': OLD_AUTH,
        'authArchive': str(archive),
        'authArchiveSHA256': sha(archive),
        'authTradeServiceSHA256': actual_trade_hash,
        'overlayManifestSHA256': sha(release / 'brand-overlay-manifest.json'),
        'siteIndexSHA256': sha(release / 'site/index.html'),
        'businessSEOSHA256': sha(release / 'site/assets/business-seo.js'),
        'aboutSHA256': sha(release / 'site/about.html'),
        'caddySHA256': sha(release / 'Caddyfile'),
        'composeSHA256': sha(release / 'compose.yaml'),
        'environmentSHA256': sha(release / '.env'),
    }
    (release / 'brand-release-lock.json').write_text(json.dumps(lock, sort_keys=True, indent=2) + '\n')
    os.chmod(release / 'brand-release-lock.json', 0o644)
    return {key: value for key, value in lock.items() if key not in ('sourceRoot', 'releaseRoot', 'baselineRoot')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--auth-image', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.release, args.auth_image), sort_keys=True))
