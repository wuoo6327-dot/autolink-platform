"""Build a narrow Round 12 candidate from the actually mounted Round 11 site.

The live release is only read. The source checkout must be clean and locked to
a commit before this candidate is frozen. No historical catalog is copied.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

BASELINE = Path('/opt/autolink-releases/52c6934-round11-20261012')
BASE_BUNDLE_SHA256 = '744bcedd5caa4fd5ada2418410f26ee496da1db979eb32350d07f2cbe0b8fc02'
OVERLAY_FILES = {
    'index.html',
    *(f'index.{code}.html' for code in ('zh', 'ar', 'ru', 'kk', 'uz', 'ko', 'fr', 'sw')),
    'assets/index-autolink-membership-apply-pricing.js',
    'images/zeekr9x-villa.webp',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root):
    return {path.relative_to(root).as_posix(): sha(path)
            for path in root.rglob('*') if path.is_file()}


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise RuntimeError('Candidate release path already exists')
    old_lock_file = BASELINE / 'brand-release-lock.json'
    old_lock = json.loads(old_lock_file.read_text())
    if Path(old_lock['releaseRoot']) != BASELINE:
        raise RuntimeError('Published baseline lock points elsewhere')
    for relative, expected in (
        ('site/index.html', old_lock['siteIndexSHA256']),
        ('site/assets/index-autolink-membership-apply-pricing.js', BASE_BUNDLE_SHA256),
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
    changed = {name for name in set(before) | set(after)
               if before.get(name) != after.get(name)}
    if changed != OVERLAY_FILES or inventory(BASELINE / 'site') != before:
        raise RuntimeError(f'Unexpected site changes: {sorted(changed ^ OVERLAY_FILES)}')
    manifest = {
        'baselineRoot': str(BASELINE),
        'sourceRoot': str(source),
        'candidateRoot': str(destination),
        'baselineLockSHA256': sha(old_lock_file),
        'changedSiteFiles': {name: after[name] for name in sorted(changed)},
        'preservedSiteFiles': len(before) - len(changed & before.keys()),
        'caddySHA256': sha(destination / 'Caddyfile'),
        'sourceTradeServiceSHA256': sha(source / 'auth/trade_service.py'),
    }
    (destination / 'round12-overlay-manifest.json').write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.destination), sort_keys=True))
