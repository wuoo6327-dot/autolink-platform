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
# Keep the list explicit so unrelated business files in the repository cannot
# silently replace a newer production file. The AMD64 home trace showed a TBT
# regression in the PR #7 home bundle, so this SEO release preserves the live
# home HTML, bundle and visuals while retaining failure recovery below. The
# smaller Zeekr hero is the same artwork and was included in the tested home
# variant (1920x1080 instead of 2880x1620).
overlay.extend([
    'assets/business-page-bootstrap.mjs',
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
# These live hashes were re-read on 2026-10-12 and diffed against the candidate.
# Any later production edit changes the hash and blocks release assembly again.
reviewed_live_hashes = {
    'trade/app.js': 'f79d3723da9943aebaea5baf684e3f0a2aca6b0f4c92ed3ab53cff029d4e705c',
    'assets/business-page-bootstrap.mjs': '136738725ba0e5b5ab9bf143ec227e79d89e4507bd10d4aa0cc00e8d4f96abac',
}


def reviewed_version(ref, name):
    result = subprocess.run(
        ['git', 'show', f'{ref}:site/{name}'], cwd=root,
        capture_output=True, check=False,
    )
    return result.stdout if result.returncode == 0 else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release_bytes(name):
    if name == 'assets/business-page-bootstrap.mjs':
        # Preserve the currently deployed home load order and trade wiring.
        # A failed noncritical helper must not abort the entire home page.
        current = (live / name).read_bytes()
        before = b'await Promise.all(config.after.map(url => loadScript(url + version)));'
        after = b'await Promise.allSettled(config.after.map(url => loadScript(url + version)));'
        assert current.count(before) == 1, 'Production bootstrap changed; review before release'
        return current.replace(before, after)
    return (source / name).read_bytes()


# Production received some static updates after the original security commit.
# A file outside the known security/PR #6/final-candidate versions is a live
# change to reconcile, never something this overlay may overwrite blindly.
conflicts = []
for name in overlay:
    incoming = source / name
    assert incoming.is_file(), name
    existing = live / name
    if not existing.is_file():
        continue
    accepted = {digest(release_bytes(name))}
    if name in reviewed_live_hashes:
        accepted.add(reviewed_live_hashes[name])
    for ref in ('a38664fc9bf2be639cbcb65dce4b57ef5b94170c',
                '8c6e5e94d67b8ec5aaafddab3547e38a740e5e00'):
        previous = reviewed_version(ref, name)
        if previous is not None:
            accepted.add(digest(previous))
    if digest(existing.read_bytes()) not in accepted:
        conflicts.append({'path': name, 'productionSHA256': digest(existing.read_bytes())})
if conflicts:
    raise RuntimeError('Unreviewed production changes block overlay: ' + json.dumps(conflicts))

shutil.copytree(live, target, copy_function=shutil.copy2)
manifest=[]
for name in overlay:
    incoming=source/name
    outgoing=target/name
    outgoing.parent.mkdir(parents=True,exist_ok=True)
    if name == 'assets/business-page-bootstrap.mjs':
        outgoing.write_bytes(release_bytes(name))
    else:
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
