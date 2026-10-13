"""One-shot fixed-image supplier brand authorization release on the SEO baseline."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sqlite3
import time

import notification_cutover as release

OLD = Path('/opt/autolink-releases/16f65c8-afme-20261014')
NEW = Path('/opt/autolink-releases/brand-auth-20261014')
STATE = Path('/opt/autolink-release-state/brand-auth-20261014')
AUTH_OLD = 'sha256:dd5523c9fe02eab7b7915c90444c95fef1b36a0d99a557b7fda8b0c9f423e148'
AUTH_NEW = 'sha256:5b7d0823b5482e31c69dd56e765632ca895795d45f22005e7dbfcd75fd3d9288'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'
SITE = {'admin/app.js', 'supplier/app.js'}
AUTH_FILES = {'Dockerfile', 'app.py', 'brand_authorization_service.py',
              'seo_service.py', 'trade_service.py', 'test_brand_authorization.py'}
IMAGE_SOURCES = ('app.py', 'brand_authorization_service.py', 'seo_service.py', 'trade_service.py')


def source_files(root):
    """Ignore legacy macOS sidecar metadata in copied release trees."""
    return {path.relative_to(root).as_posix(): release.engine.sha(path)
            for path in root.rglob('*') if path.is_file()
            and '__pycache__' not in path.relative_to(root).parts
            and not path.name.startswith('._')}


def commit():
    value = (NEW / 'git-commit.txt').read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{40}', value):
        raise RuntimeError('Release Git commit identity missing')
    return value


def configure():
    release.OLD = OLD
    release.RELEASE = NEW
    release.STATE_ROOT = STATE
    release.AUTH_OLD = AUTH_OLD
    release.AUTH_NEW = AUTH_NEW
    release.WEB = WEB
    release.COMMIT = commit()
    release.EXPECTED_SITE = SITE
    release.IMAGE_SOURCES = IMAGE_SOURCES
    release.engine.OLD = OLD
    release.engine.STATE_ROOT = STATE
    release.preflight = preflight
    release.probe = probe


def preflight(backup_path):
    if os.geteuid() or platform.machine() != 'x86_64':
        raise RuntimeError('Root on native AMD64 required')
    lock = json.loads((NEW / 'brand-auth-release-lock.json').read_text())
    if (lock['gitCommit'] != commit() or lock['releaseRoot'] != str(NEW)
            or lock['baselineRoot'] != str(OLD) or lock['authImageId'] != AUTH_NEW
            or lock['oldAuthImageId'] != AUTH_OLD or lock['webImageId'] != WEB):
        raise RuntimeError('Release lock identifies a different candidate')
    before, after = source_files(OLD / 'site'), source_files(NEW / 'site')
    changed = {name for name in before.keys() | after.keys() if before.get(name) != after.get(name)}
    if changed != SITE or before['index.html'] != after['index.html']:
        raise RuntimeError('Candidate site differs from reviewed authorization scope')
    if set(lock['siteFiles']) != SITE:
        raise RuntimeError('Locked site file set differs')
    for name, digest in lock['siteFiles'].items():
        if after[name] != digest:
            raise RuntimeError('Locked site file changed: ' + name)
    old_auth, new_auth = source_files(OLD / 'auth'), source_files(NEW / 'auth')
    auth_changed = {name for name in old_auth.keys() | new_auth.keys()
                    if old_auth.get(name) != new_auth.get(name)}
    if auth_changed != AUTH_FILES:
        raise RuntimeError('Auth overlay differs from reviewed scope: ' + str(sorted(auth_changed)))
    for name, digest in lock['releaseFiles'].items():
        if release.engine.sha(NEW / name) != digest:
            raise RuntimeError('Locked release file changed: ' + name)
    archive = NEW / 'brand-auth-image.tar'
    if release.engine.sha(archive) != lock['authArchiveSHA256']:
        raise RuntimeError('Candidate image archive changed')
    image = json.loads(release.engine.run(['docker', 'image', 'inspect', AUTH_NEW], output=False).stdout)[0]
    if image['Id'] != AUTH_NEW or image['Architecture'] != 'amd64':
        raise RuntimeError('Candidate image identity/architecture differs')
    for name in IMAGE_SOURCES:
        expected = lock['authSources'][name]
        if release.engine.sha(NEW / 'auth' / name) != expected:
            raise RuntimeError('Staged source changed: ' + name)
        embedded = release.engine.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
            AUTH_NEW, 'sha256sum', '/app/' + name], output=False).stdout.split()[0]
        if embedded != expected:
            raise RuntimeError('Image source differs: ' + name)
    release.engine.compose(NEW, 'config', '-q')
    release.engine.compose(OLD, 'config', '-q')
    refs = release.engine.compose(NEW, 'config', '--images').stdout.splitlines()
    old_refs = release.engine.compose(OLD, 'config', '--images').stdout.splitlines()
    if (AUTH_NEW not in refs or not any(WEB in item for item in refs)
            or AUTH_OLD not in old_refs or not any(WEB in item for item in old_refs)):
        raise RuntimeError('Compose images are not fixed to reviewed IDs')
    auth, web = release.engine.container('autolink-demo-auth-1'), release.engine.container('autolink-demo-web-1')
    if (auth['Image'], web['Image']) != (AUTH_OLD, WEB):
        raise RuntimeError('Production image changed before cutover')
    mounts_a = {item['Destination']: item['Source'] for item in auth['Mounts']}
    mounts_w = {item['Destination']: item['Source'] for item in web['Mounts']}
    if (mounts_a.get('/srv') != str(OLD / 'site') or mounts_w.get('/srv') != str(OLD / 'site')
            or mounts_w.get('/etc/caddy/Caddyfile') != str(OLD / 'Caddyfile')):
        raise RuntimeError('Production site/config mounts changed')
    release.engine.health('autolink-demo-auth-1', AUTH_OLD, time.monotonic() + 8)
    release.engine.health('autolink-demo-web-1', WEB, time.monotonic() + 8)
    backup = json.loads(backup_path.read_text())
    age = time.time() - datetime.fromisoformat(backup['createdAtUTC']).timestamp()
    if not backup.get('isolatedRestoreVerified') or not 0 <= age <= 15 * 60:
        raise RuntimeError('Fresh complete backup with isolated restore required')
    if (backup['sqliteSource'] != mounts_a.get('/data') + '/autolink-auth.sqlite3'
            or release.engine.sha(backup['sqliteBackup']) != backup['sqliteSHA256']
            or release.engine.sha(backup['publicCatalog']) != backup['publicCatalogSHA256']):
        raise RuntimeError('Current database/catalog backup identity changed')
    for item in backup['files'].values():
        if not item['restored'] or release.engine.sha(item['archive']) != item['sha256']:
            raise RuntimeError('Production archive restore/hash verification failed')
    for item in backup['images'].values():
        if release.engine.sha(item['archive']) != item['sha256']:
            raise RuntimeError('Rollback image archive changed')
    if (backup['images']['oldAuth']['imageID'], backup['images']['oldWeb']['imageID']) != (AUTH_OLD, WEB):
        raise RuntimeError('Backup image identity differs from production')
    with sqlite3.connect('file:' + backup['sqliteBackup'] + '?mode=ro', uri=True) as db:
        if (db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok'
                or db.execute('PRAGMA foreign_key_check').fetchone() is not None
                or db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_brand_authorizations'").fetchone()):
            raise RuntimeError('Current database contains unexpected authorization state')
        counts = (db.execute('SELECT count(*) FROM catalog_models').fetchone()[0],
                  db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0])
    if counts != (backup['databaseModels'], backup['databaseBrands']):
        raise RuntimeError('Database totals differ from backup')
    if release.engine.catalog_probe(backup) != (backup['publicModels'], backup['publicBrands']):
        raise RuntimeError('Public catalog differs from backup')
    if (NEW / 'native-container-tests.exit').read_text().strip() != '0' or \
       (NEW / 'isolated-qa.exit').read_text().strip() != '0' or \
       (NEW / 'brand-auth-trivy.exit').read_text().strip() != '0':
        raise RuntimeError('Native tests, isolated rollback or image scan failed')
    if not json.loads((NEW / 'isolated-overseas-seo-http.json').read_text()).get('pass'):
        raise RuntimeError('Public SEO regression crawl failed')
    scan = json.loads((NEW / 'brand-auth-trivy.json').read_text())
    if any(v.get('Severity') in ('HIGH', 'CRITICAL') for r in scan.get('Results', [])
           for v in r.get('Vulnerabilities', []) or []) or \
       any(r.get('Secrets') for r in scan.get('Results', [])):
        raise RuntimeError('Candidate image has blocking security findings')
    release.engine.run(['docker', 'run', '--rm', '--entrypoint', 'caddy', '-e', 'SITE_ADDRESS=localhost',
        '-v', str(NEW / 'Caddyfile') + ':/etc/caddy/Caddyfile:ro', WEB,
        'validate', '--config', '/etc/caddy/Caddyfile'], timeout=20)
    if shutil.disk_usage('/').free < 2 * 1024**3:
        raise RuntimeError('Insufficient free disk for safe cutover/rollback')
    print(release.engine.now(), 'BRAND_AUTH_PREFLIGHT_OK', commit(), flush=True)
    return backup


def probe(backup, candidate):
    if release.engine.http('/healthz')[0] != 200:
        raise RuntimeError('HTTPS health failed')
    models, brands = release.engine.catalog_probe(backup, strict=False)
    if models < backup['publicModels'] or brands < backup['publicBrands']:
        raise RuntimeError('Public catalog lost records')
    for path, expected in (('/', 200), ('/buyer/login', 200), ('/supplier', 200),
            ('/trade/models', 200), ('/trade/brands', 200), ('/robots.txt', 200),
            ('/sitemap.xml', 200), ('/guide/african-importers', 200),
            ('/autolink/supplier/brand-authorizations', 401),
            ('/autolink/admin/suppliers/unknown/brand-authorizations', 401),
            ('/autolink/admin/users', 401), ('/autolink/supplier/documents', 401),
            ('/trade/models/unknown-model', 404)):
        if release.engine.http(path)[0] != expected:
            raise RuntimeError('Core HTTP route failed: ' + path)
    status, body = release.engine.http('/trade/models/haval-catalog-1')
    if status != 200 or 'Haval H6' not in body:
        raise RuntimeError('Existing English SEO page regressed')
    if candidate:
        for path, marker in (('/admin/app.js', 'data-brand-auth-review'),
                ('/supplier/app.js', 'brand-authorization-form')):
            status, body = release.engine.http(path)
            if status != 200 or marker not in body:
                raise RuntimeError('Authorization UI asset missing: ' + path)
    print(release.engine.now(), 'BRAND_AUTH_PROBE_OK',
          {'candidate': candidate, 'models': models, 'brands': brands}, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'cutover', 'status'))
    parser.add_argument('--backup-manifest', type=Path)
    args = parser.parse_args()
    configure()
    if args.mode == 'status':
        path = STATE / NEW.name / 'status.json'
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if args.backup_manifest is None:
            parser.error('--backup-manifest required')
        if args.mode == 'preflight':
            preflight(args.backup_manifest)
        else:
            release.cutover(args.backup_manifest)
