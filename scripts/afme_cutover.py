"""Fixed-image Africa/Middle East SEO cutover with the reviewed auto-rollback engine."""
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

OLD = Path('/opt/autolink-releases/c215c54-notifications-20261014')
NEW = Path('/opt/autolink-releases/16f65c8-afme-20261014')
STATE = Path('/opt/autolink-release-state/afme-20261014')
AUTH_OLD = 'sha256:23e88a9bc8b84bd5baa07f8ecb2a970ca99a90b5404b887567f6ed651a080052'
AUTH_NEW = 'sha256:dd5523c9fe02eab7b7915c90444c95fef1b36a0d99a557b7fda8b0c9f423e148'
WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'
SITE = {'guide/african-importers.fallback.html','guide/african-importers.html',
    'guide/middle-east-importers.ar.html','guide/vehicle-sourcing.html',
    'locales/seo-brand-en-reviewed.json','locales/seo-model-en-reviewed.json'}
AUTH = ('seo_service.py','trade_service.py')

def commit():
    value=(NEW/'git-commit.txt').read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{40}',value):
        raise RuntimeError('Release Git commit identity is missing')
    return value

def configure():
    release.OLD=OLD
    release.RELEASE=NEW
    release.STATE_ROOT=STATE
    release.AUTH_OLD=AUTH_OLD
    release.AUTH_NEW=AUTH_NEW
    release.WEB=WEB
    release.COMMIT=commit()
    release.EXPECTED_SITE=SITE
    release.IMAGE_SOURCES=AUTH
    release.engine.OLD=OLD
    release.engine.STATE_ROOT=STATE
    release.preflight=preflight
    release.probe=probe

def preflight(backup_path):
    if os.geteuid() or platform.machine()!='x86_64':
        raise RuntimeError('Root on native AMD64 required')
    lock=json.loads((NEW/'afme-release-lock.json').read_text())
    if (lock['gitCommit']!=commit() or lock['releaseRoot']!=str(NEW)
            or lock['baselineRoot']!=str(OLD) or lock['authImageId']!=AUTH_NEW
            or lock['oldAuthImageId']!=AUTH_OLD or lock['webImageId']!=WEB):
        raise RuntimeError('Release lock identifies a different candidate')
    old,new=release.files(OLD/'site'),release.files(NEW/'site')
    changed={name for name in old.keys()|new.keys() if old.get(name)!=new.get(name)}
    if changed!=SITE or old['index.html']!=new['index.html']:
        raise RuntimeError('SEO overlay differs from approved scope or homepage changed')
    for name,digest in lock['siteFiles'].items():
        if new[name]!=digest:
            raise RuntimeError('Locked site file changed: '+name)
    for name,digest in lock['releaseFiles'].items():
        if release.engine.sha(NEW/name)!=digest:
            raise RuntimeError('Locked release file changed: '+name)
    archive=NEW/'afme-auth-amd64.tar'
    if release.engine.sha(archive)!=lock['authArchiveSHA256']:
        raise RuntimeError('Auth image archive changed')
    image=json.loads(release.engine.run(['docker','image','inspect',AUTH_NEW],output=False).stdout)[0]
    if image['Id']!=AUTH_NEW or image['Architecture']!='amd64':
        raise RuntimeError('Candidate image ID or architecture differs')
    for name in AUTH:
        expected=lock['authSources'][name]
        if release.engine.sha(NEW/'auth'/name)!=expected:
            raise RuntimeError('Locked Auth source changed: '+name)
        embedded=release.engine.run(['docker','run','--rm','--network','none','--read-only',
            AUTH_NEW,'sha256sum','/app/'+name],output=False).stdout.split()[0]
        if embedded!=expected:
            raise RuntimeError('Running image source differs: '+name)
    release.engine.compose(NEW,'config','-q')
    release.engine.compose(OLD,'config','-q')
    refs=release.engine.compose(NEW,'config','--images').stdout.splitlines()
    old_refs=release.engine.compose(OLD,'config','--images').stdout.splitlines()
    if (AUTH_NEW not in refs or not any(WEB in item for item in refs)
            or AUTH_OLD not in old_refs or not any(WEB in item for item in old_refs)):
        raise RuntimeError('Compose images are not fixed to approved identities')
    auth,web=release.engine.container('autolink-demo-auth-1'),release.engine.container('autolink-demo-web-1')
    if (auth['Image'],web['Image'])!=(AUTH_OLD,WEB):
        raise RuntimeError('Current production image changed')
    mounts_a={m['Destination']:m['Source'] for m in auth['Mounts']}
    mounts_w={m['Destination']:m['Source'] for m in web['Mounts']}
    if (mounts_a.get('/srv')!=str(OLD/'site') or mounts_w.get('/srv')!=str(OLD/'site')
            or mounts_w.get('/etc/caddy/Caddyfile')!=str(OLD/'Caddyfile')):
        raise RuntimeError('Current production mounts changed')
    release.engine.health('autolink-demo-auth-1',AUTH_OLD,time.monotonic()+8)
    release.engine.health('autolink-demo-web-1',WEB,time.monotonic()+8)
    backup=json.loads(backup_path.read_text())
    age=time.time()-datetime.fromisoformat(backup['createdAtUTC']).timestamp()
    if not backup.get('isolatedRestoreVerified') or age<0 or age>15*60:
        raise RuntimeError('Fresh complete backup with isolated restore required')
    if (backup['sqliteSource']!=mounts_a.get('/data')+'/autolink-auth.sqlite3'
            or release.engine.sha(backup['sqliteBackup'])!=backup['sqliteSHA256']
            or release.engine.sha(backup['publicCatalog'])!=backup['publicCatalogSHA256']):
        raise RuntimeError('Current database/catalog backup identity changed')
    for item in backup['files'].values():
        if not item['restored'] or release.engine.sha(item['archive'])!=item['sha256']:
            raise RuntimeError('A production archive failed restore/hash verification')
    for item in backup['images'].values():
        if release.engine.sha(item['archive'])!=item['sha256']:
            raise RuntimeError('Rollback image archive hash differs')
    if (backup['images']['oldAuth']['imageID'],backup['images']['oldWeb']['imageID'])!=(AUTH_OLD,WEB):
        raise RuntimeError('Backup images differ from running production')
    with sqlite3.connect('file:'+backup['sqliteBackup']+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or \
                db.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise RuntimeError('Restored production SQLite integrity failed')
        counts=(db.execute('SELECT count(*) FROM catalog_models').fetchone()[0],
                db.execute('SELECT count(*) FROM catalog_brands').fetchone()[0])
    if counts!=(backup['databaseModels'],backup['databaseBrands']):
        raise RuntimeError('Restored catalog totals differ')
    if release.engine.catalog_probe(backup)!=(backup['publicModels'],backup['publicBrands']):
        raise RuntimeError('Current public catalog differs from fresh backup')
    if (NEW/'native-container-tests.exit').read_text().strip()!='0' or \
       (NEW/'isolated-qa.exit').read_text().strip()!='0' or \
       (NEW/'afme-trivy.exit').read_text().strip()!='0':
        raise RuntimeError('AMD64 test, rollback or image scan failed')
    audit=json.loads((NEW/'isolated-overseas-seo-http.json').read_text())
    if not audit.get('pass'):
        raise RuntimeError('Full isolated public URL crawl failed')
    scan=json.loads((NEW/'afme-trivy.json').read_text())
    if (any(item.get('Severity') in ('HIGH','CRITICAL') for result in scan.get('Results',[])
             for item in result.get('Vulnerabilities',[]) or []) or
        any(result.get('Secrets') for result in scan.get('Results',[]))):
        raise RuntimeError('Blocking image scan findings')
    release.engine.run(['docker','run','--rm','--entrypoint','caddy','-e','SITE_ADDRESS=localhost',
        '-v',str(NEW/'Caddyfile')+':/etc/caddy/Caddyfile:ro',WEB,
        'validate','--config','/etc/caddy/Caddyfile'],timeout=20)
    if shutil.disk_usage('/').free<2*1024**3:
        raise RuntimeError('Insufficient free space for safe cutover/rollback')
    print(release.engine.now(),'AFME_PREFLIGHT_OK',commit(),flush=True)
    return backup

def probe(backup,candidate):
    if release.engine.http('/healthz')[0]!=200:
        raise RuntimeError('HTTPS health failed')
    models,brands=release.engine.catalog_probe(backup,strict=False)
    if models<backup['publicModels'] or brands<backup['publicBrands']:
        raise RuntimeError('Public catalog lost entries')
    for path,expected in (('/',200),('/buyer/login',200),('/supplier',200),
        ('/trade/models',200),('/trade/brands',200),('/robots.txt',200),
        ('/autolink/admin/users',401),('/autolink/buyer/requests?page=1',401),
        ('/autolink/supplier/documents',401),('/trade/models/unknown-model',404)):
        if release.engine.http(path)[0]!=expected:
            raise RuntimeError('Core route failed: '+path)
    status,monjaro=release.engine.http('/trade/models/geely-monjaro-2026')
    if status!=200 or 'Geely Monjaro' not in monjaro:
        raise RuntimeError('Existing English model SSR regressed')
    if candidate:
        for path,needle in (('/trade/models/haval-catalog-1','Haval H6'),
            ('/trade/models/tank-catalog-1','Tank 300'),
            ('/trade/brands/haval','Brand and model information is provided for reference only'),
            ('/guide/african-importers','Chinese vehicle sourcing for African importers')):
            status,body=release.engine.http(path)
            if status!=200 or needle not in body or 'noindex' in body:
                raise RuntimeError('New English SEO content failed: '+path)
        status,arabic=release.engine.http('/guide/middle-east-importers?lang=ar')
        if status!=200 or 'noindex, follow' not in arabic or 'dir="rtl"' not in arabic:
            raise RuntimeError('Unreviewed Arabic page opened index or lost RTL')
        status,sitemap=release.engine.http('/sitemaps/static-1.xml')
        if status!=200 or '/guide/african-importers' not in sitemap:
            raise RuntimeError('Africa guide missing from current Sitemap')
    print(release.engine.now(),'AFME_PROBE_OK',{'candidate':candidate,'models':models,'brands':brands},flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('preflight','cutover','status'))
    parser.add_argument('--backup-manifest',type=Path)
    args=parser.parse_args()
    configure()
    if args.mode=='status':
        path=STATE/NEW.name/'status.json'
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if args.backup_manifest is None:
            parser.error('--backup-manifest required')
        if args.mode=='preflight':
            preflight(args.backup_manifest)
        else:
            release.cutover(args.backup_manifest)
