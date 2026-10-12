"""One-shot, logged AUTOLINK brand SEO cutover with automatic rollback.

Run from detached tmux on the reviewed linux/amd64 host. This script never
builds or pulls an image and never edits the production database or volumes.
"""

import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


OLD = Path('/opt/autolink-releases/5725b8b-seo-20261012')
STATE_ROOT = Path('/opt/autolink-release-state/brand-identity-20261012')
DOMAIN = 'autolinkglobal.com'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def run(args, timeout=45, check=True, output=True):
    print(now(), 'RUN', ' '.join(map(str, args)), flush=True)
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if output and result.stdout:
        print(result.stdout.strip(), flush=True)
    if output and result.stderr:
        print(result.stderr.strip(), file=sys.stderr, flush=True)
    if check and result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {args[0]}')
    return result


def compose(root, *args, timeout=60):
    return run(['docker', 'compose', '-p', 'autolink-demo', '--project-directory', str(root),
                '-f', str(root / 'compose.yaml'), *args], timeout=timeout)


def container(name):
    result = json.loads(run(['docker', 'inspect', name], timeout=10, output=False).stdout)
    if len(result) != 1:
        raise RuntimeError(f'Missing production container: {name}')
    return result[0]


def health(name, image, deadline):
    while time.monotonic() < deadline:
        item = container(name)
        state = item['State']
        if item['Image'] != image:
            raise RuntimeError(f'Unexpected running image for {name}')
        if state['Status'] == 'running' and state.get('Health', {}).get('Status') == 'healthy':
            return
        time.sleep(2)
    raise TimeoutError(f'Health timeout: {name}')


def http(path):
    result = run(['curl', '-sS', '--max-time', '5', '--resolve', f'{DOMAIN}:443:127.0.0.1',
                  '--write-out', '\n__STATUS__%{http_code}', f'https://{DOMAIN}{path}'],
                 timeout=6, output=False)
    body, status = result.stdout.rsplit('\n__STATUS__', 1)
    return int(status), body


def wait_https(deadline):
    while time.monotonic() < deadline:
        try:
            if http('/healthz')[0] == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError('Public HTTPS did not become healthy')


def read_lock(release):
    lock = json.loads((release / 'brand-release-lock.json').read_text())
    if Path(lock['releaseRoot']) != release or Path(lock['baselineRoot']) != OLD:
        raise RuntimeError('Release lock references a different path')
    return lock


def catalog_probe(backup, strict=True):
    saved = json.loads(Path(backup['publicCatalog']).read_text())
    status, models = http('/autolink/public/models?limit=500')
    status_b, brands = http('/autolink/public/brands')
    if (status, status_b) != (200, 200):
        raise RuntimeError('Public catalog API failed')
    models, brands = json.loads(models)['data'], json.loads(brands)['data']
    if strict and (models != saved['models'] or brands != saved['brands']):
        raise RuntimeError('Current public catalog differs from fresh backup')
    if not strict:
        if not {item['id'] for item in saved['models']} <= {item['id'] for item in models}:
            raise RuntimeError('A backed-up public model disappeared')
        if not {item['id'] for item in saved['brands']} <= {item['id'] for item in brands}:
            raise RuntimeError('A backed-up public brand disappeared')
    return len(models), len(brands)


def verify_site_overlay(release, lock):
    manifest_path = release / 'brand-overlay-manifest.json'
    if sha(manifest_path) != lock['overlayManifestSHA256']:
        raise RuntimeError('Overlay manifest changed')
    manifest = json.loads(manifest_path.read_text())
    expected = {'index.html', 'about.html', 'assets/business-seo.js'}
    if set(manifest['changedSiteFiles']) != expected:
        raise RuntimeError('Overlay changed files outside reviewed scope')
    previous = {p.relative_to(OLD / 'site').as_posix(): sha(p)
                for p in (OLD / 'site').rglob('*') if p.is_file()}
    current = {p.relative_to(release / 'site').as_posix(): sha(p)
               for p in (release / 'site').rglob('*') if p.is_file()}
    changed = {name for name in set(previous) | set(current) if previous.get(name) != current.get(name)}
    if changed != expected or current['index.html'] != lock['siteIndexSHA256']:
        raise RuntimeError('Candidate site differs from locked overlay')
    for name, digest in manifest['changedSiteFiles'].items():
        if current[name] != digest:
            raise RuntimeError(f'Candidate site file changed: {name}')
    for name, key in [('Caddyfile', 'caddySHA256'), ('compose.yaml', 'composeSHA256'),
                      ('.env', 'environmentSHA256')]:
        if sha(release / name) != lock[key]:
            raise RuntimeError(f'Candidate release file changed: {name}')


def preflight(release, backup_path):
    if os.geteuid() != 0 or platform.machine() != 'x86_64':
        raise RuntimeError('Requires root on linux/amd64')
    lock = read_lock(release)
    source = Path(lock['sourceRoot'])
    if run(['git', '-C', str(source), 'rev-parse', 'HEAD'], output=False).stdout.strip() != lock['gitCommit']:
        raise RuntimeError('Source checkout changed after locking')
    if run(['git', '-C', str(source), 'status', '--porcelain'], output=False).stdout.strip():
        raise RuntimeError('Source checkout is not clean')
    verify_site_overlay(release, lock)
    if sha(lock['authArchive']) != lock['authArchiveSHA256']:
        raise RuntimeError('Candidate Auth archive changed')
    image = json.loads(run(['docker', 'image', 'inspect', lock['authImageID']], output=False).stdout)[0]
    if image['Id'] != lock['authImageID'] or image['Architecture'] != 'amd64':
        raise RuntimeError('Candidate Auth image identity failed')
    trade_hash = run(['docker', 'run', '--rm', '--network', 'none', '--read-only', lock['authImageID'],
                      'sha256sum', '/app/trade_service.py'], output=False).stdout.split()[0]
    if trade_hash != lock['authTradeServiceSHA256'] or trade_hash != sha(source / 'auth/trade_service.py'):
        raise RuntimeError('Candidate Auth source differs from locked image')
    compose(release, 'config', '-q')
    compose(OLD, 'config', '-q')
    # The fixed image IDs are checked below without remote pulls.
    image_refs = set(compose(release, 'config', '--images').stdout.splitlines())
    if lock['authImageID'] not in image_refs:
        raise RuntimeError('Candidate Compose does not reference fixed Auth image ID')
    if not any(lock['webImageID'] in reference for reference in image_refs):
        raise RuntimeError('Candidate Compose does not reference fixed Web image ID')
    rollback_refs = set(compose(OLD, 'config', '--images').stdout.splitlines())
    if not any(lock['oldAuthImageID'] in reference for reference in rollback_refs):
        raise RuntimeError('Rollback Compose does not reference the running Auth image')
    if not any(lock['webImageID'] in reference for reference in rollback_refs):
        raise RuntimeError('Rollback Compose does not reference the running Web image')
    auth, web = container('autolink-demo-auth-1'), container('autolink-demo-web-1')
    if auth['Image'] != lock['oldAuthImageID'] or web['Image'] != lock['webImageID']:
        raise RuntimeError('Running production images changed')
    auth_mounts = {item['Destination']: item['Source'] for item in auth['Mounts']}
    web_mounts = {item['Destination']: item['Source'] for item in web['Mounts']}
    if auth_mounts.get('/srv') != str(OLD / 'site') or web_mounts.get('/srv') != str(OLD / 'site'):
        raise RuntimeError('Production site mount changed')
    if web_mounts.get('/etc/caddy/Caddyfile') != str(OLD / 'Caddyfile'):
        raise RuntimeError('Production Caddy mount changed')
    health('autolink-demo-auth-1', lock['oldAuthImageID'], time.monotonic() + 5)
    if not backup_path.is_file():
        raise RuntimeError('Fresh production backup manifest is missing')
    backup = json.loads(backup_path.read_text())
    if not backup.get('isolatedRestoreVerified'):
        raise RuntimeError('Production backup restore verification failed')
    age = time.time() - datetime.fromisoformat(backup['createdAtUTC']).timestamp()
    if age < 0 or age > 15 * 60:
        raise RuntimeError('Production backup must be less than 15 minutes old')
    source_db = Path(auth_mounts['/data']) / 'autolink-auth.sqlite3'
    if Path(backup['sqliteSource']) != source_db or sha(backup['sqliteBackup']) != backup['sqliteSHA256']:
        raise RuntimeError('Production SQLite source or backup differs')
    if sha(backup['publicCatalog']) != backup['publicCatalogSHA256']:
        raise RuntimeError('Public catalog backup changed')
    for item in backup['files'].values():
        if not item['restored'] or sha(item['archive']) != item['sha256']:
            raise RuntimeError('Restored production archive changed')
    for item in backup['images'].values():
        if sha(item['archive']) != item['sha256']:
            raise RuntimeError('Saved production image changed')
    counts = catalog_probe(backup)
    if counts != (backup['publicModels'], backup['publicBrands']):
        raise RuntimeError('Public catalog count changed after backup')
    if not (release / 'isolated-qa-ok.json').is_file():
        raise RuntimeError('AMD64 isolated test and rollback marker is missing')
    qa = json.loads((release / 'isolated-qa-ok.json').read_text())
    if qa.get('gitCommit') != lock['gitCommit'] or qa.get('authImageID') != lock['authImageID']:
        raise RuntimeError('Isolated QA marker does not match candidate')
    run(['docker', 'run', '--rm', '--entrypoint', 'caddy', '-e', 'SITE_ADDRESS=localhost',
         '-v', str(release / 'Caddyfile') + ':/etc/caddy/Caddyfile:ro', lock['webImageID'],
         'validate', '--config', '/etc/caddy/Caddyfile'], timeout=20)
    print(now(), 'PREFLIGHT_OK', json.dumps({'publicModels': counts[0], 'publicBrands': counts[1],
                                           'candidateAuthImage': lock['authImageID']}), flush=True)
    return lock, backup


def core_probe(backup, candidate):
    if http('/healthz')[0] != 200:
        raise RuntimeError('Public health endpoint failed')
    counts = catalog_probe(backup, strict=not candidate)
    for path, expected in [('/autolink/admin/users', 401), ('/buyer/login', 200),
                           ('/supplier', 200), ('/admin', 200), ('/robots.txt', 200)]:
        if http(path)[0] != expected:
            raise RuntimeError(f'Core route failed: {path}')
    status, home = http('/')
    if status != 200:
        raise RuntimeError('Homepage failed')
    if candidate:
        if 'Chinese Vehicle Sourcing &amp; B2B Supplier Platform' not in home:
            raise RuntimeError('New homepage metadata missing')
        if home.count('id="autolink-public-jsonld"') != 1:
            raise RuntimeError('Homepage identity JSON-LD missing or duplicated')
        status, about = http('/about')
        if status != 200 or '<h1>About AUTOLINK</h1>' not in about or 'index, follow' not in about:
            raise RuntimeError('Public About page failed')
        if http('/about.html')[0] not in (200, 308):
            raise RuntimeError('About canonical redirect failed')
        status, xml = http('/sitemaps/static-1.xml')
        ns = '{http://www.sitemaps.org/schemas/sitemap/0.9}loc'
        if status != 200 or [x.text for x in ElementTree.fromstring(xml).iter(ns)].count(
                'https://autolinkglobal.com/about') != 1:
            raise RuntimeError('About is not listed once in English Sitemap')
        for path, needle in [('/trade/models/geely-monjaro-2026', 'Geely Monjaro'),
                             ('/trade/brands/geely', 'Geely')]:
            status, html = http(path)
            if status != 200 or needle not in html:
                raise RuntimeError(f'Existing SEO page regressed: {path}')
        if http('/trade/models/not-a-model')[0] != 404:
            raise RuntimeError('Unknown model does not return 404')
        if 'noindex' not in http('/trade/models/aeolus-catalog-1')[1]:
            raise RuntimeError('Unreviewed English model lost noindex')
    print(now(), 'CORE_PROBE_OK', json.dumps({'candidate': candidate, 'models': counts[0],
                                             'brands': counts[1]}), flush=True)


def write_state(directory, state, **details):
    payload = {'state': state, 'atUTC': now(), **details}
    temporary = directory / '.status.json.tmp'
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    with temporary.open('rb') as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, directory / 'status.json')
    print(now(), 'STATE', state, flush=True)


def rollback(release, lock, backup, state_dir, reason):
    write_state(state_dir, 'rolling_back', reason=reason)
    compose(OLD, 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', '--no-build',
            'auth', timeout=50)
    health('autolink-demo-auth-1', lock['oldAuthImageID'], time.monotonic() + 35)
    compose(OLD, 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never', '--no-build',
            'web', timeout=50)
    health('autolink-demo-web-1', lock['webImageID'], time.monotonic() + 25)
    wait_https(time.monotonic() + 20)
    core_probe(backup, False)
    write_state(state_dir, 'rolled_back', reason=reason)


def cutover(release, backup_path):
    os.umask(0o077)
    state_dir = STATE_ROOT / release.name
    state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    with (state_dir / 'lock').open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (state_dir / 'status.json').exists():
            raise RuntimeError('Cutover already attempted; inspect its state instead of repeating it')
        with (state_dir / 'cutover.log').open('a', buffering=1) as log:
            stdout, stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = log
            started = False
            try:
                def interrupted(signum, _frame):
                    raise InterruptedError(f'Received signal {signum}')
                signal.signal(signal.SIGTERM, interrupted)
                signal.signal(signal.SIGHUP, interrupted)
                lock, backup = preflight(release, backup_path)
                core_probe(backup, False)
                write_state(state_dir, 'cutover_started')
                started = True
                deadline = time.monotonic() + 120
                compose(release, 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never',
                        '--no-build', 'auth', timeout=45)
                health('autolink-demo-auth-1', lock['authImageID'], min(deadline, time.monotonic() + 35))
                compose(release, 'up', '-d', '--no-deps', '--force-recreate', '--pull', 'never',
                        '--no-build', 'web', timeout=45)
                health('autolink-demo-web-1', lock['webImageID'], min(deadline, time.monotonic() + 30))
                wait_https(min(deadline, time.monotonic() + 20))
                core_probe(backup, True)
                if time.monotonic() > deadline:
                    raise TimeoutError('Cutover exceeded its two-minute switching budget')
                write_state(state_dir, 'live_core_verified', authImage=lock['authImageID'],
                            webImage=lock['webImageID'])
                failures = 0
                for minute in range(30):
                    time.sleep(60)
                    try:
                        health('autolink-demo-auth-1', lock['authImageID'], time.monotonic() + 5)
                        if container('autolink-demo-web-1')['Image'] != lock['webImageID']:
                            raise RuntimeError('Web image changed during monitoring')
                        core_probe(backup, True)
                        disk = shutil.disk_usage('/')
                        if disk.free < 1024**3:
                            raise RuntimeError('Less than 1 GiB disk space remains')
                        if minute % 5 == 0:
                            with sqlite3.connect('file:' + backup['sqliteSource'] + '?mode=ro', uri=True) as db:
                                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                                    raise RuntimeError('Production SQLite quick_check failed')
                            stats = run(['docker', 'stats', '--no-stream', '--format',
                                         '{{.Name}} {{.CPUPerc}} {{.MemUsage}}',
                                         'autolink-demo-auth-1', 'autolink-demo-web-1'], timeout=12)
                            print(now(), 'RESOURCE_CHECK', stats.stdout.strip(),
                                  'diskFreeBytes', disk.free, flush=True)
                        failures = 0
                    except Exception as issue:
                        failures += 1
                        print(now(), 'MONITOR_FAILURE', repr(issue), flush=True)
                        if failures >= 2:
                            raise
                    write_state(state_dir, 'monitoring', minute=minute + 1, probeFailures=failures)
                write_state(state_dir, 'completed', authImage=lock['authImageID'],
                            webImage=lock['webImageID'])
            except BaseException as issue:
                print(now(), 'CUTOVER_FAILURE', repr(issue), flush=True)
                if started:
                    try:
                        rollback(release, lock, backup, state_dir, repr(issue))
                    except BaseException as rollback_issue:
                        write_state(state_dir, 'rollback_failed', error=repr(rollback_issue))
                        print(now(), 'ROLLBACK_FAILURE', repr(rollback_issue), flush=True)
                raise
            finally:
                sys.stdout, sys.stderr = stdout, stderr


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'cutover', 'status'))
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--backup-manifest', type=Path)
    arguments = parser.parse_args()
    release = arguments.release.resolve()
    if arguments.mode == 'status':
        path = STATE_ROOT / release.name / 'status.json'
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if not arguments.backup_manifest:
            parser.error('--backup-manifest is required')
        if arguments.mode == 'preflight':
            preflight(release, arguments.backup_manifest)
        else:
            cutover(release, arguments.backup_manifest)
