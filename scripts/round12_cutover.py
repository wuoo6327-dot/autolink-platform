"""Round 12 probes around the already proven timed cutover and rollback engine."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from xml.etree import ElementTree

import brand_identity_cutover as runbook


BASELINE = Path('/opt/autolink-releases/52c6934-round11-20261012')
runbook.OLD = BASELINE
runbook.STATE_ROOT = Path('/opt/autolink-release-state/round12-20261012')
ORIGINAL_PROBE = runbook.core_probe
EXPECTED = {
    'index.html',
    *(f'index.{code}.html' for code in ('zh', 'ar', 'ru', 'kk', 'uz', 'ko', 'fr', 'sw')),
    'assets/index-autolink-membership-apply-pricing.js',
    'images/zeekr9x-villa.webp',
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_site_overlay(release, lock):
    manifest_file = release / 'round12-overlay-manifest.json'
    if sha(manifest_file) != lock['overlayManifestSHA256']:
        raise RuntimeError('Round 12 overlay manifest changed')
    manifest = json.loads(manifest_file.read_text())
    if set(manifest['changedSiteFiles']) != EXPECTED:
        raise RuntimeError('Round 12 overlay file scope changed')
    original = {path.relative_to(BASELINE / 'site').as_posix(): sha(path)
                for path in (BASELINE / 'site').rglob('*') if path.is_file()}
    current = {path.relative_to(release / 'site').as_posix(): sha(path)
               for path in (release / 'site').rglob('*') if path.is_file()}
    changed = {name for name in set(original) | set(current) if original.get(name) != current.get(name)}
    if changed != EXPECTED:
        raise RuntimeError(f'Unreviewed site change: {sorted(changed ^ EXPECTED)}')
    for name, digest in manifest['changedSiteFiles'].items():
        if current[name] != digest:
            raise RuntimeError(f'Site file changed after lock: {name}')
    for relative, key in [('Caddyfile', 'caddySHA256'), ('compose.yaml', 'composeSHA256'),
                          ('.env', 'environmentSHA256')]:
        if sha(release / relative) != lock[key]:
            raise RuntimeError(f'Locked release file changed: {relative}')
    if current['index.html'] != lock['siteIndexSHA256']:
        raise RuntimeError('Locked homepage changed')


def core_probe(backup, candidate):
    ORIGINAL_PROBE(backup, candidate)
    if not candidate:
        return
    for code in ('en', 'zh', 'ar', 'ru', 'kk', 'uz', 'ko', 'fr', 'sw'):
        path = '/' if code == 'en' else '/?lang=' + code
        status, body = runbook.http(path)
        expected_lang = 'zh-CN' if code == 'zh' else code
        expected_robots = 'index, follow' if code in ('en', 'zh') else 'noindex, follow'
        if status != 200 or f'<html lang="{expected_lang}"' not in body or expected_robots not in body:
            raise RuntimeError(f'Homepage initial HTML failed: {code}')
        if '<div class="home-static">' not in body or '<form class="home-static-search"' not in body:
            raise RuntimeError(f'Homepage fallback missing: {code}')
    status, xml = runbook.http('/sitemap.xml')
    if status != 200:
        raise RuntimeError('Root Sitemap failed')
    root = ElementTree.fromstring(xml)
    names = [node.text.rsplit('/', 1)[-1] for node in root.iter('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
    if names != ['static-1.xml', 'brands-1.xml', 'models-1.xml']:
        raise RuntimeError(f'Root Sitemap contains unexpected shards: {names}')
    for name in names:
        status, child = runbook.http('/sitemaps/' + name)
        urls = list(ElementTree.fromstring(child).iter('{http://www.sitemaps.org/schemas/sitemap/0.9}url'))
        if status != 200 or not urls:
            raise RuntimeError(f'Invalid or empty child Sitemap: {name}')
        if name == 'static-1.xml':
            locations = [node.text for node in ElementTree.fromstring(child).iter(
                '{http://www.sitemaps.org/schemas/sitemap/0.9}loc')]
            if len(locations) != 40 or any('/membership' in url or '/support' in url for url in locations):
                raise RuntimeError('Static Sitemap still contains duplicate client shells')
    if runbook.http('/sitemaps/suppliers-1.xml')[0] != 404 or runbook.http('/sitemaps/vehicles-1.xml')[0] != 404:
        raise RuntimeError('Empty Sitemap shards are still public')
    for path, needle in [('/assets/home-public-fallback.css', '.home-static'),
                         ('/assets/business-language-loader.mjs', 'installHomeLanguageChoices')]:
        status, body = runbook.http(path)
        if status != 200 or needle not in body:
            raise RuntimeError(f'Required public asset failed: {path}')
    if 'index-autolink-membership-apply-pricing.js?v=20261011-mobile-ad' in runbook.http('/')[1]:
        raise RuntimeError('Homepage still preloads the old duplicate bundle URL')
    if 'index-autolink-membership-apply-pricing.js?v=20261012-home-fast' not in runbook.http('/')[1]:
        raise RuntimeError('Homepage does not preload its executing bundle URL')
    print(runbook.now(), 'ROUND12_PROBE_OK', json.dumps({'languages': 9, 'sitemapChildren': names}), flush=True)


runbook.verify_site_overlay = verify_site_overlay
runbook.core_probe = core_probe


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'cutover', 'status'))
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--backup-manifest', type=Path)
    arguments = parser.parse_args()
    release = arguments.release.resolve()
    if arguments.mode == 'status':
        path = runbook.STATE_ROOT / release.name / 'status.json'
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if not arguments.backup_manifest:
            parser.error('--backup-manifest is required')
        if arguments.mode == 'preflight':
            runbook.preflight(release, arguments.backup_manifest)
        else:
            runbook.cutover(release, arguments.backup_manifest)
