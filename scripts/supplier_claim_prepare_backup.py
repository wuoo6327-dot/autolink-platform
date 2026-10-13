"""Restore-checked production backup for the public claim screening hotfix."""
from pathlib import Path
import prepare_notification_backup as backup

backup.BASE = Path('/opt/autolink-backups/brand-auth-claim-screen-20261014')
backup.OLD = Path('/opt/autolink-releases/brand-auth-20261014')
backup.OLD_AUTH = 'sha256:5b7d0823b5482e31c69dd56e765632ca895795d45f22005e7dbfcd75fd3d9288'
backup.WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'

if __name__ == '__main__':
    backup.main()
