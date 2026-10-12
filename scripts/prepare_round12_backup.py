"""Run the previously verified full backup and restore checks on the live Round 12 baseline."""

from pathlib import Path

import prepare_brand_identity_backup as backup


backup.BASE = Path('/opt/autolink-backups/round12-20261012')
backup.OLD = Path('/opt/autolink-releases/52c6934-round11-20261012')
backup.OLD_AUTH = 'sha256:5dfea447ad82555952ec7cb037b3e877bf361cf162267f7b82e16822f8736049'
backup.WEB = 'sha256:bddc55c35abafbc75c8a765ac79991f221c9149fa943bf960217d50cf70323fb'


if __name__ == '__main__':
    backup.main()
