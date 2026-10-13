"""Freeze the isolated public claim screening overlay and native image."""
from pathlib import Path
import supplier_brand_auth_release_lock as lock

lock.BASE = Path('/opt/autolink-releases/brand-auth-20261014')
lock.ROOT = Path('/opt/autolink-releases/brand-auth-claim-screen-20261014')
lock.OLD_AUTH = 'sha256:5b7d0823b5482e31c69dd56e765632ca895795d45f22005e7dbfcd75fd3d9288'
lock.SITE = set()
lock.AUTH_CHANGED = {'trade_service.py', 'seo_service.py', 'test_brand_authorization.py'}
lock.FILES = lock.FILES | {'scripts/supplier_claim_cutover.py',
    'scripts/supplier_claim_prepare_backup.py', 'scripts/supplier_claim_release_lock.py'}

if __name__ == '__main__':
    lock.main()
