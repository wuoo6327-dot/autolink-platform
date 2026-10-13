"""Fresh, restore-checked backup for the Africa/Middle East SEO release."""
from pathlib import Path
import prepare_notification_backup as backup

backup.BASE = Path('/opt/autolink-backups/afme-20261014')
backup.OLD = Path('/opt/autolink-releases/c215c54-notifications-20261014')
backup.OLD_AUTH = 'sha256:23e88a9bc8b84bd5baa07f8ecb2a970ca99a90b5404b887567f6ed651a080052'
backup.WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'

if __name__ == '__main__':
    backup.main()
