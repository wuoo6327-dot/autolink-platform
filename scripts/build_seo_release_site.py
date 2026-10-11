"""Prepare an SEO-only public site from a read-only copy of current production.

Never replace the full production site with the repository snapshot. The allowlist
contains only files needed by the current catalog SEO renderer and public
directory. Existing model references, images, legal pages, home UI and account
pages stay exactly as they are in the production copy.
"""
import hashlib
import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
live = root / 'production-public/site'
source = root / 'site'
target = root / 'release-public/site'
assert live.is_dir() and source.is_dir() and not target.exists()
overlay = [
    'robots.txt',
    'locales/seo-index-reviews.json',
    'locales/seo-model-en-reviewed.json',
    'locales/seo-verified-terms.json',
    'trade/app.js',
    'trade/trade.css',
    'trade/model-reference.mjs',
    'assets/business-seo.js',
    'assets/public-directory.js',
]
overlay.extend(str(path.relative_to(source)) for path in sorted((source/'images/seo-heroes').glob('*')) if path.is_file())
shutil.copytree(live, target, copy_function=shutil.copy2)
manifest=[]
for name in overlay:
    incoming=source/name
    assert incoming.is_file(), name
    outgoing=target/name
    outgoing.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(incoming,outgoing)
    manifest.append({'path':name,'sha256':hashlib.sha256(outgoing.read_bytes()).hexdigest()})
untouched=0
for path in live.rglob('*'):
    if not path.is_file() or str(path.relative_to(live)) in overlay:continue
    other=target/path.relative_to(live)
    assert other.is_file() and hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(other.read_bytes()).digest(),str(path)
    untouched+=1
(root/'release-public/overlay-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'overlaid':len(manifest),'untouchedProductionFiles':untouched,'releaseSite':str(target)}))
