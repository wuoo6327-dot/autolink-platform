"""Copy missing PUBLIC static assets into QA only when candidate hashes match."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--root',required=True);args=p.parse_args()
root=Path(args.root).resolve()
assert 'autolink-round3-stage-native' in str(root)
manifest=json.loads((root/'public-assets.json').read_text())
copied=0
for name, expected in manifest.items():
    relative=Path(name)
    assert not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='site'
    destination=root/'source'/relative
    if not destination.exists():
        source=Path('/opt/autolink-demo')/relative
        assert source.is_file() and not source.is_symlink(), 'Missing public candidate asset: '+name
        assert hashlib.sha256(source.read_bytes()).hexdigest()==expected, 'Production asset differs: '+name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination);copied+=1
    assert hashlib.sha256(destination.read_bytes()).hexdigest()==expected, 'Candidate asset mismatch: '+name
proof=root/'evidence';proof.mkdir(mode=0o700,exist_ok=True)
(proof/'public-assets-proof.json').write_text(json.dumps({'publicCandidateFilesVerified':len(manifest),'copiedFromProductionReadOnly':copied,'productionFilesModified':False},indent=2))
print('Public candidate assets verified:',len(manifest),'copied read-only:',copied)
