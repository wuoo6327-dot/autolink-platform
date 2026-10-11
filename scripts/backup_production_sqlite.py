"""Create and restore-check a private, consistent SQLite production snapshot.

Run on the production host with an explicit source path and a root-only backup
directory. This reads the live database through SQLite's online backup API;
it never copies a possibly inconsistent live .sqlite3 file directly.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def verify(path):
    uri = path.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        integrity = db.execute('PRAGMA integrity_check').fetchone()[0]
        foreign_keys = db.execute('PRAGMA foreign_key_check').fetchall()
        result = {
            'integrity': integrity,
            'foreignKeyViolations': len(foreign_keys),
            'userVersion': db.execute('PRAGMA user_version').fetchone()[0],
            'models': db.execute('SELECT count(*) FROM catalog_models').fetchone()[0],
            'brands': db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0],
        }
    if integrity != 'ok' or foreign_keys:
        raise RuntimeError('SQLite integrity or foreign-key check failed')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('backup_dir', type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    backup_dir = args.backup_dir.resolve(strict=True)
    if not source.is_file() or not backup_dir.is_dir():
        raise RuntimeError('Source and private backup directory are required')
    if backup_dir.stat().st_mode & 0o077:
        raise RuntimeError('Backup directory must be inaccessible to group and others')
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = backup_dir / f'autolink-auth-{timestamp}.sqlite3'
    manifest = backup_dir / f'autolink-auth-{timestamp}.json'
    if destination.exists() or manifest.exists():
        raise RuntimeError('Backup path already exists')
    fd, temporary_name = tempfile.mkstemp(prefix='.autolink-backup-', suffix='.sqlite3', dir=backup_dir)
    os.close(fd)
    temporary = Path(temporary_name)
    restored = backup_dir / f'.autolink-restore-probe-{timestamp}.sqlite3'
    try:
        uri = source.as_uri() + '?mode=ro'
        with closing(sqlite3.connect(uri, uri=True)) as live, closing(sqlite3.connect(temporary)) as copy:
            live.backup(copy, pages=1000, sleep=0.1)
        snapshot = verify(temporary)
        shutil.copyfile(temporary, restored)
        restored_result = verify(restored)
        if restored_result != snapshot or sha256(restored) != sha256(temporary):
            raise RuntimeError('Isolated restore copy differs from consistent snapshot')
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        with destination.open('rb') as handle:
            os.fsync(handle.fileno())
        evidence = {
            'createdAtUTC': datetime.now(timezone.utc).isoformat(),
            'source': str(source),
            'backup': str(destination),
            'sha256': sha256(destination),
            'bytes': destination.stat().st_size,
            'sqlite': snapshot,
            'isolatedRestoreVerified': True,
        }
        with manifest.open('x', encoding='utf-8') as handle:
            os.chmod(manifest, 0o600)
            json.dump(evidence, handle, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        directory = os.open(backup_dir, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        print(json.dumps(evidence, sort_keys=True))
    finally:
        temporary.unlink(missing_ok=True)
        restored.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
