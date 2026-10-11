"""Build optional mobile thumbnails from a reviewed public catalog snapshot.

The source path and bytes are recorded so the renderer falls back to the live
catalog image if a photo changes without a matching thumbnail build.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--catalog', type=Path, default=ROOT/'tests/fixtures/production-public-catalog-20261012.json')
args = parser.parse_args()
models = json.loads(args.catalog.read_text(encoding='utf-8'))['models']
output = ROOT/'site/images/seo-heroes'
output.mkdir(parents=True, exist_ok=True)
manifest = {}
for model in models:
    ident, source = str(model['id']), str(model.get('image') or '')
    if not ident.replace('-', '').replace('_', '').isalnum() or not source.startswith('/images/'):
        continue
    path = ROOT/'site'/source.lstrip('/')
    if not path.is_file():
        continue
    target = output/(ident+'-640.webp')
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        if image.width > 640:
            image = image.resize((640, round(image.height*640/image.width)), Image.Resampling.LANCZOS)
        image.save(target, 'WEBP', quality=76, method=5)
    manifest[ident] = {'source': source, 'sourceSHA256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'mobile': '/images/seo-heroes/'+target.name}
(output/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n', encoding='utf-8')
print('thumbnails',len(manifest),'bytes',sum((output/(key+'-640.webp')).stat().st_size for key in manifest))
