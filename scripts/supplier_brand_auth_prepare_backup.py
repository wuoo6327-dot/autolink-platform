"""Restore-checked production backup before supplier authorization release."""
from pathlib import Path
import prepare_notification_backup as backup

backup.BASE = Path('/opt/autolink-backups/brand-auth-20261014')
backup.OLD = Path('/opt/autolink-releases/16f65c8-afme-20261014')
backup.OLD_AUTH = 'sha256:dd5523c9fe02eab7b7915c90444c95fef1b36a0d99a557b7fda8b0c9f423e148'
backup.WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'

if __name__ == '__main__':
    backup.main()
