"""Run the previously verified full backup and restore checks on the live Round 11 baseline."""

from pathlib import Path

import prepare_brand_identity_backup as backup


backup.BASE = Path('/opt/autolink-backups/round11-20261012')
backup.OLD = Path('/opt/autolink-releases/d996b69-brand-20261012')
backup.OLD_AUTH = 'sha256:742d1f3e28b9f9adca7159f3f2c22afb4b540dd25900e7bf36186be05ee217cb'
backup.WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'


if __name__ == '__main__':
    backup.main()
