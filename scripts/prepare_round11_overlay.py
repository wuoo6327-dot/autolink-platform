"""Create a narrow Round 11 site overlay from the verified live release.

This never modifies the running release. The published application bundle,
vehicle images, accounts and business pages remain byte-for-byte unchanged.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


BASELINE = Path('/opt/autolink-releases/d996b69-brand-20261012')
BASE_LOADER_SHA256 = 'a51e98266e18da4f2e42a4afa38ac023bbeb5c984cc2009df4e530bc1c199edb'
OVERLAY_FILES = {
    'index.html',
    *(f'index.{code}.html' for code in ('zh', 'ar', 'ru', 'kk', 'uz', 'ko', 'fr', 'sw')),
    'assets/business-language-loader.mjs',
    'assets/business-seo.js',
    'assets/home-public-fallback.css',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path)
            for path in root.rglob('*') if path.is_file()}


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise RuntimeError('Candidate release path already exists')
    old_lock = json.loads((BASELINE / 'brand-release-lock.json').read_text())
    if Path(old_lock['releaseRoot']) != BASELINE:
        raise RuntimeError('Published release lock points elsewhere')
    for relative, expected in (
        ('site/index.html', old_lock['siteIndexSHA256']),
        ('site/assets/business-seo.js', old_lock['businessSEOSHA256']),
        ('site/assets/business-language-loader.mjs', BASE_LOADER_SHA256),
        ('Caddyfile', old_lock['caddySHA256']),
    ):
        if sha(BASELINE / relative) != expected:
            raise RuntimeError(f'Production baseline changed: {relative}')
    before = inventory(BASELINE / 'site')
    destination.mkdir(parents=True)
    shutil.copytree(BASELINE / 'site', destination / 'site')
    for relative in sorted(OVERLAY_FILES):
        original = source / 'site' / relative
        if not original.is_file():
            raise RuntimeError(f'Missing reviewed source: {relative}')
        target = destination / 'site' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
    shutil.copy2(source / 'Caddyfile', destination / 'Caddyfile')
    after = inventory(destination / 'site')
    changed = {name for name in set(before) | set(after) if before.get(name) != after.get(name)}
    if changed != OVERLAY_FILES or inventory(BASELINE / 'site') != before:
        raise RuntimeError(f'Unexpected site changes: {sorted(changed ^ OVERLAY_FILES)}')
    if after['assets/index-autolink-membership-apply-pricing.js'] != before['assets/index-autolink-membership-apply-pricing.js']:
        raise RuntimeError('Existing homepage bundle changed unexpectedly')
    manifest = {
        'baselineRoot': str(BASELINE),
        'sourceRoot': str(source),
        'candidateRoot': str(destination),
        'baselineLockSHA256': sha(BASELINE / 'brand-release-lock.json'),
        'changedSiteFiles': {name: after[name] for name in sorted(changed)},
        'preservedSiteFiles': len(before) - len(changed & before.keys()),
        'caddySHA256': sha(destination / 'Caddyfile'),
        'sourceTradeServiceSHA256': sha(source / 'auth/trade_service.py'),
    }
    (destination / 'round11-overlay-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    arguments = parser.parse_args()
    print(json.dumps(prepare(arguments.source, arguments.destination), sort_keys=True))
