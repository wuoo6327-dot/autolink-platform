"""Prepare an SEO-only public site from a read-only copy of current production.

Never replace the full production site with the repository snapshot. The allowlist
contains only files needed by the current catalog SEO renderer and public
directory. Existing model references, images, legal pages, home UI and account
pages stay exactly as they are in the production copy.
"""
import hashlib
import json
import shutil
import subprocess
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
# PR #7 home performance and PR #8 reviewed English SEO must travel with the
# PR #6 renderer. Keep the list explicit so unrelated business files in the
# repository cannot silently replace a newer production file.
overlay.extend([
    'index.html',
    'assets/business-page-bootstrap.mjs',
    'assets/home-suv-visuals.js',
    'assets/index-autolink-membership-apply-pricing.js',
    'images/home-mobile/zeekr9x-city-ad.webp',
    'admin/app.js',
    'admin/bootstrap.js',
    'admin/index.html',
    'guide/middle-east-importers.fallback.html',
    'guide/middle-east-importers.html',
    'guide/render.mjs',
    'guide/supplier-verification.html',
    'guide/trade-process.html',
    'guide/vehicle-sourcing.html',
    'locales/seo-brand-en-reviewed.json',
])
overlay.extend(str(path.relative_to(source)) for path in sorted((source/'images/seo-heroes').glob('*')) if path.is_file())
overlay = list(dict.fromkeys(overlay))


def reviewed_version(ref, name):
    result = subprocess.run(
        ['git', 'show', f'{ref}:site/{name}'], cwd=root,
        capture_output=True, check=False,
    )
    return result.stdout if result.returncode == 0 else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


# Production received some static updates after the original security commit.
# A file outside the known security/PR #6/final-candidate versions is a live
# change to reconcile, never something this overlay may overwrite blindly.
for name in overlay:
    incoming = source / name
    assert incoming.is_file(), name
    existing = live / name
    if not existing.is_file():
        continue
    accepted = {digest(incoming.read_bytes())}
    for ref in ('a38664fc9bf2be639cbcb65dce4b57ef5b94170c',
                '8c6e5e94d67b8ec5aaafddab3547e38a740e5e00'):
        previous = reviewed_version(ref, name)
        if previous is not None:
            accepted.add(digest(previous))
    if digest(existing.read_bytes()) not in accepted:
        raise RuntimeError(f'Unreviewed production change blocks overlay: {name}')

shutil.copytree(live, target, copy_function=shutil.copy2)
manifest=[]
for name in overlay:
    incoming=source/name
    outgoing=target/name
    outgoing.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(incoming,outgoing)
    manifest.append({'path':name,'sha256':digest(outgoing.read_bytes())})
untouched=0
for path in live.rglob('*'):
    if not path.is_file() or str(path.relative_to(live)) in overlay:continue
    other=target/path.relative_to(live)
    assert other.is_file() and hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(other.read_bytes()).digest(),str(path)
    untouched+=1
(root/'release-public/overlay-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'overlaid':len(manifest),'untouchedProductionFiles':untouched,'releaseSite':str(target)}))
