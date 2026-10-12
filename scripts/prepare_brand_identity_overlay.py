"""Build a brand SEO site overlay from the *running* public release.

This script refuses unfamiliar production files and never modifies its input.
Only index.html, business-seo.js, about.html and Caddyfile may change.
The production homepage's existing asset versions remain byte-for-byte intact.
"""

import argparse
import hashlib
import json
import shutil
from pathlib import Path


PRODUCTION_INDEX = 'c26f2d7f8191ef3614539a448ea476c334f2fd0f329774ed27bd5ae354ec1d49'
PRODUCTION_BUSINESS_SEO = '8d8783447c0301e6e3875a1c2c80ab51d70e39f6f2e2a77a314e5c23dc768d06'
PRODUCTION_CADDY = '7c295e23c6fcc1a76b54fa73827397de222f162e95cfad873f0a0cf05bffe65f'
OLD_ASSET_VERSION = '20261011-mobile-ad'
SOURCE_ASSET_VERSION = '20261012-home-fast'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*') if p.is_file()}


def prepare(production, source, destination):
    production, source, destination = map(Path, (production, source, destination))
    if destination.exists():
        raise RuntimeError('Destination already exists; choose a fresh immutable release path')
    site = production / 'site'
    expected = {
        site / 'index.html': PRODUCTION_INDEX,
        site / 'assets/business-seo.js': PRODUCTION_BUSINESS_SEO,
        production / 'Caddyfile': PRODUCTION_CADDY,
    }
    for path, known in expected.items():
        if not path.is_file() or digest(path) != known:
            raise RuntimeError(f'Running production baseline changed: {path}')
    if (site / 'about.html').exists():
        raise RuntimeError('Production already has About; review it before replacing')
    original = inventory(site)
    old_index = (site / 'index.html').read_text()
    source_index = (source / 'site/index.html').read_text()
    if old_index.count(OLD_ASSET_VERSION) != 4 or source_index.count(SOURCE_ASSET_VERSION) != 4:
        raise RuntimeError('Homepage asset references differ from the reviewed release')
    if source_index.replace(SOURCE_ASSET_VERSION, OLD_ASSET_VERSION).count(OLD_ASSET_VERSION) != 4:
        raise RuntimeError('Homepage source asset preservation failed')
    # The source branch differs from the public production page only in its
    # older asset query versions before the brand edits. Keep those versions.
    baseline = (source / 'site/index.html').read_text().replace(SOURCE_ASSET_VERSION, OLD_ASSET_VERSION)
    if 'AUTOLINK | Chinese Vehicle Sourcing &amp; B2B Supplier Platform' not in baseline:
        raise RuntimeError('Brand title is absent from reviewed source')
    destination.mkdir(parents=True)
    shutil.copytree(site, destination / 'site')
    (destination / 'site/index.html').write_text(baseline)
    shutil.copy2(source / 'site/assets/business-seo.js', destination / 'site/assets/business-seo.js')
    shutil.copy2(source / 'site/about.html', destination / 'site/about.html')
    shutil.copy2(source / 'Caddyfile', destination / 'Caddyfile')
    final = inventory(destination / 'site')
    changed = sorted(name for name in set(original) | set(final) if original.get(name) != final.get(name))
    allowed = ['about.html', 'assets/business-seo.js', 'index.html']
    if changed != allowed or inventory(site) != original:
        raise RuntimeError(f'Overlay changed unexpected files: {changed}')
    manifest = {
        'productionRoot': str(production),
        'sourceRoot': str(source),
        'productionIndexSHA256': PRODUCTION_INDEX,
        'productionBusinessSEOSHA256': PRODUCTION_BUSINESS_SEO,
        'productionCaddySHA256': PRODUCTION_CADDY,
        'changedSiteFiles': {name: final[name] for name in changed},
        'caddySHA256': digest(destination / 'Caddyfile'),
        'preservedSiteFiles': len(original) - 2,
        'productionSiteFileCount': len(original),
        'candidateSiteFileCount': len(final),
        'productionAssetVersion': OLD_ASSET_VERSION,
    }
    (destination / 'brand-overlay-manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--production', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.production, args.source, args.destination), sort_keys=True))
