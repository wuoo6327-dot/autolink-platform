"""Rehearse notification release and rollback on an isolated SQLite copy.

The QA container has no network and never mounts the production data volume.
"""

import argparse
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path


OLD = Path('/opt/autolink-releases/7fefb90-account-role-20261013')
RELEASE = Path('/opt/autolink-releases/c215c54-notifications-20261014')
AUTH_OLD = 'sha256:8c14559850ac1ebe5d778415adb6e1b5777e75b5424fe8677ae402ada81242e0'
AUTH_NEW = 'sha256:23e88a9bc8b84bd5baa07f8ecb2a970ca99a90b5404b887567f6ed651a080052'
CONTAINER = 'autolink-notification-isolated-qa'


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True, timeout=45)


def database_counts(path):
    with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        models = db.execute('SELECT count(*) FROM catalog_models').fetchone()[0]
        brands = db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0]
    return integrity, models, brands


def inspect():
    return json.loads(run('docker', 'inspect', CONTAINER).stdout)[0]


def request(path):
    script = (
        'import urllib.request,urllib.error; '
        f'u="http://127.0.0.1:8080{path}"; '
        'r=urllib.request.urlopen(u,timeout=3); print(r.status); print(r.read(160).decode())'
    )
    try:
        return run('docker', 'exec', CONTAINER, 'python', '-c', script).stdout
    except subprocess.CalledProcessError as error:
        if 'HTTP Error 401' in error.stderr:
            return '401\n'
        if 'HTTP Error 501' in error.stderr:
            return '501\n'
        raise RuntimeError(error.stderr[-1000:]) from error


def phase(label, image, site, db_path, expected_counts):
    run('docker', 'run', '-d', '--name', CONTAINER, '--network', 'none',
        '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
        '--tmpfs', '/tmp:size=32m,mode=1777', '-e', 'AUTH_DB_PATH=/data/autolink-auth.sqlite3',
        '-e', 'GOOGLE_CLIENT_ID=919734262669-4csunht5tjcdlj2oojcilidn4utpfskl.apps.googleusercontent.com',
        '-e', 'MAIL_PROVIDER=', '-e', 'RESEND_API_KEY=',
        '-v', f'{db_path.parent}:/data', '-v', f'{site}:/srv:ro', image)
    try:
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            state = inspect()
            if state['Image'] == image and state['State']['Status'] == 'running' and \
                    state['State'].get('Health', {}).get('Status') == 'healthy':
                break
            if state['State']['Status'] == 'exited':
                logs = run('docker', 'logs', CONTAINER)
                raise RuntimeError(f'{label} exited: {logs.stdout[-1000:]} {logs.stderr[-1000:]}')
            time.sleep(2)
        else:
            logs = run('docker', 'logs', CONTAINER)
            raise RuntimeError(f'{label} did not become healthy: {logs.stdout[-1000:]} {logs.stderr[-1000:]}')
        state = inspect()
        mounts = {mount['Destination']: mount['Source'] for mount in state['Mounts']}
        if state['HostConfig']['NetworkMode'] != 'none' or mounts.get('/data') != str(db_path.parent) \
                or mounts.get('/srv') != str(site):
            raise RuntimeError(f'{label} is not isolated')
        if not request('/healthz').startswith('200\n'):
            raise RuntimeError(f'{label} health HTTP failed')
        expected_summary = '401\n' if image == AUTH_NEW else '501\n'
        if request('/autolink/notifications/summary') != expected_summary:
            raise RuntimeError(f'{label} notification authorization failed')
        if not request('/autolink/public/models?limit=1').startswith('200\n'):
            raise RuntimeError(f'{label} public model API failed')
        integrity, models, brands = database_counts(db_path)
        if (integrity, models, brands) != ('ok', *expected_counts):
            raise RuntimeError(f'{label} changed the isolated database')
        return {'phase': label, 'authImageId': image, 'sqliteIntegrity': integrity,
                'databaseModels': models, 'databaseBrands': brands,
                'notificationUnauthenticatedStatus': int(expected_summary.strip())}
    finally:
        run('docker', 'rm', '-f', CONTAINER)


def main():
    if os.geteuid() or platform.machine() != 'x86_64':
        raise RuntimeError('Run as root on the native AMD64 host')
    args = argparse.ArgumentParser()
    args.add_argument('--backup-manifest', required=True, type=Path)
    backup = json.loads(args.parse_args().backup_manifest.read_text())
    root = RELEASE / 'notification-isolated-qa'
    root.mkdir(mode=0o700, exist_ok=True)
    data = root / 'data'
    data.mkdir(mode=0o700, exist_ok=True)
    db_path = data / 'autolink-auth.sqlite3'
    if db_path.exists():
        raise RuntimeError('QA database already exists; use a new release directory')
    shutil.copy2(backup['sqliteBackup'], db_path)
    os.chown(data, 10001, 10001)
    os.chown(db_path, 10001, 10001)
    expected = backup['databaseModels'], backup['databaseBrands']
    if database_counts(db_path) != ('ok', *expected):
        raise RuntimeError('Restored QA database differs from the backup')
    output = RELEASE / 'notification-rollback-rehearsal.jsonl'
    with output.open('w') as log:
        for label, image, site in (
            ('candidate', AUTH_NEW, RELEASE / 'site'),
            ('rollback', AUTH_OLD, OLD / 'site'),
            ('restored_candidate', AUTH_NEW, RELEASE / 'site'),
        ):
            result = phase(label, image, site, db_path, expected)
            log.write(json.dumps(result, sort_keys=True) + '\n')
            log.flush()
    print(json.dumps({'result': 'passed', 'phases': 3, 'evidence': str(output)}))


if __name__ == '__main__':
    main()
