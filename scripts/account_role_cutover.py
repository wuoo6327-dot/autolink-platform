"""One-shot account-role release with fixed images, fresh backup and rollback.

Run in detached tmux as root on the reviewed linux/amd64 host. This script
does not build, pull, migrate, or replace production data volumes.
"""

import argparse
import fcntl
import json
import os
import platform
import shutil
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import brand_identity_cutover as engine


OLD = Path('/opt/autolink-releases/e7c48f2-round14-robots-20261013')
RELEASE = Path('/opt/autolink-releases/7fefb90-account-role-20261013')
STATE_ROOT = Path('/opt/autolink-release-state/account-role-20261013')
AUTH_OLD = 'sha256:87e19b1892d25bd79ccfce83f98e2658f20c9ad258db870f1224cd8434494afd'
AUTH_NEW = 'sha256:8c14559850ac1ebe5d778415adb6e1b5777e75b5424fe8677ae402ada81242e0'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'
COMMIT = 'b8502a8e7d2bee9879478f3c49728bea4a9ef6fe'
EXPECTED_SITE = {
    'admin/app.js', 'admin/bootstrap.js', 'admin/i18n/evidence-zh.js', 'admin/index.html',
    'assets/business-page-bootstrap.mjs', 'assets/password-security.js',
    'buyer/app.js', 'buyer/index.html', 'supplier/app.js', 'supplier/bootstrap.mjs',
    'supplier/company-fields.js', 'supplier/console.css', 'supplier/index.html',
}
IMAGE_SOURCES = ('app.py', 'email_auth.py', 'supplier_agreement_service.py',
                 'team_service.py', 'trade_service.py')
engine.OLD = OLD
engine.STATE_ROOT = STATE_ROOT


def assert_environment():
    if os.geteuid() or platform.machine() != 'x86_64':
        raise RuntimeError('Requires root on the reviewed linux/amd64 host')


def files(root):
    return {path.relative_to(root).as_posix(): engine.sha(path)
            for path in root.rglob('*') if path.is_file()}


def preflight(backup_path):
    assert_environment()
    lock = json.loads((RELEASE / 'account-role-release-lock.json').read_text())
    if (lock['gitCommit'] != COMMIT or lock['releaseRoot'] != str(RELEASE)
            or lock['baselineRoot'] != str(OLD) or lock['authImageId'] != AUTH_NEW
            or lock['oldAuthImageId'] != AUTH_OLD or lock['webImageId'] != WEB):
        raise RuntimeError('Release lock does not identify this candidate')
    old, new = files(OLD / 'site'), files(RELEASE / 'site')
    changed = {name for name in old.keys() | new.keys() if old.get(name) != new.get(name)}
    if changed != EXPECTED_SITE or set(lock['siteFiles']) != EXPECTED_SITE:
        raise RuntimeError('Candidate site differs from reviewed overlay')
    if old['index.html'] != new['index.html']:
        raise RuntimeError('Homepage changed outside release scope')
    for name, digest in lock['siteFiles'].items():
        if new[name] != digest:
            raise RuntimeError('Locked site file changed: ' + name)
    for name, digest in lock['releaseFiles'].items():
        if engine.sha(RELEASE / name) != digest:
            raise RuntimeError('Locked release file changed: ' + name)
    if engine.sha(RELEASE / 'account-role-auth-amd64.tar') != lock['authArchiveSHA256']:
        raise RuntimeError('Auth image archive changed')
    image = json.loads(engine.run(['docker', 'image', 'inspect', AUTH_NEW], output=False).stdout)[0]
    if image['Id'] != AUTH_NEW or image['Architecture'] != 'amd64':
        raise RuntimeError('Candidate Auth image identity or architecture changed')
    for name in IMAGE_SOURCES:
        expected = lock['authSources'][name]
        if engine.sha(RELEASE / 'auth' / name) != expected:
            raise RuntimeError('Staged Auth source changed: ' + name)
        actual = engine.run(['docker', 'run', '--rm', '--network', 'none', '--read-only',
                             AUTH_NEW, 'sha256sum', '/app/' + name], output=False).stdout.split()[0]
        if actual != expected:
            raise RuntimeError('Image Auth source changed: ' + name)
    engine.compose(RELEASE, 'config', '-q')
    engine.compose(OLD, 'config', '-q')
    refs = engine.compose(RELEASE, 'config', '--images').stdout.splitlines()
    rollback_refs = engine.compose(OLD, 'config', '--images').stdout.splitlines()
    if (AUTH_NEW not in refs or not any(WEB in item for item in refs)
            or AUTH_OLD not in rollback_refs or not any(WEB in item for item in rollback_refs)):
        raise RuntimeError('Compose image references are not pinned')
    auth, web = engine.container('autolink-demo-auth-1'), engine.container('autolink-demo-web-1')
    if (auth['Image'], web['Image']) != (AUTH_OLD, WEB):
        raise RuntimeError('Production image changed before cutover')
    mounts_a = {item['Destination']: item['Source'] for item in auth['Mounts']}
    mounts_w = {item['Destination']: item['Source'] for item in web['Mounts']}
    if (mounts_a.get('/srv') != str(OLD / 'site') or mounts_w.get('/srv') != str(OLD / 'site')
            or mounts_w.get('/etc/caddy/Caddyfile') != str(OLD / 'Caddyfile')):
        raise RuntimeError('Production site or Caddy mount changed')
    engine.health('autolink-demo-auth-1', AUTH_OLD, time.monotonic() + 8)
    engine.health('autolink-demo-web-1', WEB, time.monotonic() + 8)
    backup = json.loads(backup_path.read_text())
    age = time.time() - datetime.fromisoformat(backup['createdAtUTC']).timestamp()
    if not backup.get('isolatedRestoreVerified') or age < 0 or age > 15 * 60:
        raise RuntimeError('Fresh, restored production backup required')
    if (backup['sqliteSource'] != mounts_a.get('/data') + '/autolink-auth.sqlite3'
            or engine.sha(backup['sqliteBackup']) != backup['sqliteSHA256']
            or engine.sha(backup['publicCatalog']) != backup['publicCatalogSHA256']):
        raise RuntimeError('Production SQLite or catalog backup changed')
    for item in backup['files'].values():
        if not item['restored'] or engine.sha(item['archive']) != item['sha256']:
            raise RuntimeError('Production archive failed restore or hash validation')
    for item in backup['images'].values():
        if engine.sha(item['archive']) != item['sha256']:
            raise RuntimeError('Old image archive hash mismatch')
    if (backup['images']['oldAuth']['imageID'], backup['images']['oldWeb']['imageID']) != (AUTH_OLD, WEB):
        raise RuntimeError('Rollback images changed')
    with sqlite3.connect('file:' + backup['sqliteBackup'] + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('SQLite backup integrity failed')
        counts = (db.execute('SELECT count(*) FROM catalog_models').fetchone()[0],
                  db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0])
    if counts != (backup['databaseModels'], backup['databaseBrands']):
        raise RuntimeError('Backup database counts changed')
    if engine.catalog_probe(backup) != (backup['publicModels'], backup['publicBrands']):
        raise RuntimeError('Current public catalog differs from fresh backup')
    if (RELEASE / 'account-role-native-tests.exit').read_text().strip() != '0' or \
            'OK (skipped=5)' not in (RELEASE / 'account-role-native-tests.log').read_text():
        raise RuntimeError('Native AMD64 backend suite not passed')
    if (RELEASE / 'isolated-rollback-rehearsal.exit').read_text().strip() != '0':
        raise RuntimeError('Isolated rollback rehearsal not passed')
    phases = [json.loads(line) for line in (RELEASE / 'isolated-rollback-rehearsal.jsonl').read_text().splitlines()]
    if ([item['phase'] for item in phases] != ['candidate', 'rollback', 'restored_candidate']
            or [item['authImageId'] for item in phases] != [AUTH_NEW, AUTH_OLD, AUTH_NEW]
            or any(item['sqliteIntegrity'] != 'ok' or item['databaseModels'] != backup['databaseModels']
                   or item['databaseBrands'] != backup['databaseBrands'] for item in phases)):
        raise RuntimeError('Rollback phases or isolated database counts differ')
    scan = json.loads((RELEASE / 'account-role-image-trivy.json').read_text())
    if (any(v.get('Severity') in ('HIGH', 'CRITICAL') for result in scan.get('Results', [])
            for v in result.get('Vulnerabilities', [])) or
            any(result.get('Secrets') for result in scan.get('Results', []))):
        raise RuntimeError('Candidate image security scan has blocking findings')
    engine.run(['docker', 'run', '--rm', '--entrypoint', 'caddy', '-e', 'SITE_ADDRESS=localhost',
                '-v', str(RELEASE / 'Caddyfile') + ':/etc/caddy/Caddyfile:ro', WEB,
                'validate', '--config', '/etc/caddy/Caddyfile'], timeout=20)
    print(engine.now(), 'PREFLIGHT_OK', COMMIT, flush=True)
    return backup


def probe(backup, candidate):
    if engine.http('/healthz')[0] != 200:
        raise RuntimeError('Production HTTPS health failed')
    models, brands = engine.catalog_probe(backup, strict=False)
    if models < backup['publicModels'] or brands < backup['publicBrands']:
        raise RuntimeError('Public catalog lost records')
    for path, expected in (('/', 200), ('/buyer/login', 200), ('/supplier', 200),
                           ('/trade/models', 200), ('/trade/brands', 200), ('/robots.txt', 200),
                           ('/autolink/admin/users', 401), ('/autolink/buyer/requests?page=1', 401),
                           ('/trade/models/not-a-current-model', 404)):
        if engine.http(path)[0] != expected:
            raise RuntimeError('Core HTTP route failed: ' + path)
    for path, needle in (('/trade/models/geely-monjaro-2026?lang=en', 'Geely Monjaro'),
                         ('/trade/brands/geely?lang=en', '<h1>Geely</h1>')):
        status, body = engine.http(path)
        if status != 200 or needle not in body:
            raise RuntimeError('Existing SEO page regressed: ' + path)
    if candidate:
        status, source = engine.http('/supplier/company-fields.js?v=20261013-multi-picker')
        if status != 200 or 'seller-multi-footer' not in source:
            raise RuntimeError('Supplier picker asset missing')
        status, source = engine.http('/supplier/bootstrap.mjs?v=20261013-multi-picker')
        if status != 200 or 'multi-picker' not in source:
            raise RuntimeError('Supplier picker bootstrap missing')
        for path in ('/autolink/supplier/application', '/autolink/supplier/documents'):
            if engine.http(path)[0] != 401:
                raise RuntimeError('Private supplier API exposed: ' + path)
    print(engine.now(), 'CORE_PROBE_OK', {'candidate':candidate,'models':models,'brands':brands}, flush=True)


def rollback(backup, state_dir, reason):
    engine.write_state(state_dir, 'rolling_back', reason=reason)
    engine.compose(OLD, 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never',
                   '--no-build', 'auth', timeout=50)
    engine.health('autolink-demo-auth-1', AUTH_OLD, time.monotonic() + 35)
    engine.compose(OLD, 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never',
                   '--no-build', 'web', timeout=50)
    engine.health('autolink-demo-web-1', WEB, time.monotonic() + 25)
    engine.wait_https(time.monotonic() + 20)
    probe(backup, False)
    engine.write_state(state_dir, 'rolled_back', reason=reason)


def cutover(backup_path):
    assert_environment()
    os.umask(0o077)
    state_dir = STATE_ROOT / RELEASE.name
    state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (state_dir / 'lock').open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (state_dir / 'status.json').exists():
            raise RuntimeError('Cutover already attempted; inspect state before any retry')
        with (state_dir / 'cutover.log').open('a', buffering=1) as log:
            stdout, stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            started = False
            try:
                def interrupted(signum, _frame):
                    raise InterruptedError('Received signal ' + str(signum))
                signal.signal(signal.SIGHUP, interrupted)
                signal.signal(signal.SIGTERM, interrupted)
                backup = preflight(backup_path)
                probe(backup, False)
                engine.write_state(state_dir, 'cutover_started', gitCommit=COMMIT)
                started = True
                deadline = time.monotonic() + 110
                engine.compose(RELEASE, 'up', '-d', '--no-deps', '--force-recreate', '--pull',
                               'never', '--no-build', 'auth', timeout=50)
                engine.health('autolink-demo-auth-1', AUTH_NEW, min(deadline, time.monotonic() + 40))
                engine.compose(RELEASE, 'up', '-d', '--no-deps', '--force-recreate', '--pull',
                               'never', '--no-build', 'web', timeout=50)
                engine.health('autolink-demo-web-1', WEB, min(deadline, time.monotonic() + 30))
                engine.wait_https(min(deadline, time.monotonic() + 20))
                probe(backup, True)
                if time.monotonic() >= deadline:
                    raise TimeoutError('Switch exceeded 110 seconds; start rollback')
                engine.write_state(state_dir, 'live_core_verified', authImage=AUTH_NEW, gitCommit=COMMIT)
                failures = 0
                for minute in range(30):
                    time.sleep(60)
                    try:
                        engine.health('autolink-demo-auth-1', AUTH_NEW, time.monotonic() + 6)
                        engine.health('autolink-demo-web-1', WEB, time.monotonic() + 6)
                        probe(backup, True)
                        disk = shutil.disk_usage('/')
                        if disk.free < 1024**3:
                            raise RuntimeError('Less than 1 GiB disk remains')
                        if minute % 5 == 0:
                            with sqlite3.connect('file:' + backup['sqliteSource'] + '?mode=ro', uri=True) as db:
                                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                                    raise RuntimeError('Production SQLite quick_check failed')
                            stats = engine.run(['docker', 'stats', '--no-stream', '--format',
                                                '{{.Name}} {{.CPUPerc}} {{.MemUsage}}',
                                                'autolink-demo-auth-1', 'autolink-demo-web-1'], timeout=12)
                            print(engine.now(), 'RESOURCE_CHECK', stats.stdout.strip(),
                                  'diskFreeBytes', disk.free, flush=True)
                        failures = 0
                    except Exception as issue:
                        failures += 1
                        print(engine.now(), 'MONITOR_FAILURE', repr(issue), flush=True)
                        if failures >= 2:
                            raise
                    engine.write_state(state_dir, 'monitoring', minute=minute + 1, probeFailures=failures)
                engine.write_state(state_dir, 'completed', authImage=AUTH_NEW, gitCommit=COMMIT)
            except BaseException as issue:
                print(engine.now(), 'CUTOVER_FAILURE', repr(issue), flush=True)
                if started:
                    try:
                        rollback(backup, state_dir, repr(issue))
                    except BaseException as failure:
                        engine.write_state(state_dir, 'rollback_failed', error=repr(failure))
                        print(engine.now(), 'ROLLBACK_FAILURE', repr(failure), flush=True)
                raise
            finally:
                sys.stdout, sys.stderr = stdout, stderr


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'cutover', 'status'))
    parser.add_argument('--backup-manifest', type=Path)
    args = parser.parse_args()
    if args.mode == 'status':
        path = STATE_ROOT / RELEASE.name / 'status.json'
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if args.backup_manifest is None:
            parser.error('--backup-manifest is required')
        if args.mode == 'preflight':
            preflight(args.backup_manifest)
        else:
            cutover(args.backup_manifest)
