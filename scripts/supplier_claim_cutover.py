"""One-shot fixed-image public claim screening hotfix on the reviewed brand auth release."""
import argparse
import json
from pathlib import Path

import supplier_brand_auth_cutover as release


release.OLD = Path('/opt/autolink-releases/brand-auth-20261014')
release.NEW = Path('/opt/autolink-releases/brand-auth-claim-screen-20261014')
release.STATE = Path('/opt/autolink-release-state/brand-auth-claim-screen-20261014')
release.AUTH_OLD = 'sha256:5b7d0823b5482e31c69dd56e765632ca895795d45f22005e7dbfcd75fd3d9288'
release.AUTH_NEW = 'sha256:e56bb2c05766aeda08db14db4a6931e6ba19f117926a9f24927b7edaccf3be2c'
release.SITE = set()
release.AUTH_FILES = {'trade_service.py', 'seo_service.py', 'test_brand_authorization.py'}
release.REQUIRE_NO_AUTH_TABLE = False


original_probe = release.probe


def claim_screen_probe(backup, candidate):
    original_probe(backup, candidate)
    if candidate:
        status, body = release.release.engine.http('/autolink/public/suppliers')
        if status != 200:
            raise RuntimeError('Public supplier directory failed')
        suppliers = json.loads(body)['data']
        for supplier in suppliers:
            description = supplier.get('description') or ''
            if any(term in description for term in ('一级经销商', '官方授权', '授权经销商',
                    'official dealer', 'authorized distributor')):
                raise RuntimeError('Unreviewed authorization claim remains in public supplier prose')


release.probe = claim_screen_probe


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('preflight', 'cutover', 'status'))
    parser.add_argument('--backup-manifest', type=Path)
    args = parser.parse_args()
    release.configure()
    if args.mode == 'status':
        path = release.STATE / release.NEW.name / 'status.json'
        print(path.read_text() if path.exists() else '{"state":"not_started"}')
    else:
        if args.backup_manifest is None:
            parser.error('--backup-manifest required')
        if args.mode == 'preflight':
            release.preflight(args.backup_manifest)
        else:
            release.release.cutover(args.backup_manifest)
