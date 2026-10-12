"""Use the same full-resolution Zeekr hero in a smaller WebP encoding.

The JPEG remains the fallback and the mobile creative is unchanged. Exact
signatures protect the nine generated homepage documents and frozen bundle.
The 1784x1332 WebP was made from the existing JPEG with Pillow quality=86,
method=6; its 188736 bytes and hash below are an explicit build artifact.
"""
import hashlib
from pathlib import Path

site = Path(__file__).resolve().parent.parent / "site"
webp = site / 'images/zeekr9x-villa.webp'
if (not webp.is_file() or webp.stat().st_size != 188736 or
        hashlib.sha256(webp.read_bytes()).hexdigest() !=
        'a4e80f086ed3109e3de4515db5253d2ed56809b8370621fe15d17e00a0fd279b'):
    raise SystemExit('Expected reviewed full-resolution Zeekr WebP is missing')
pages = [site / "index.html", *(site / f"index.{lang}.html" for lang in
          ("zh", "ar", "ru", "kk", "uz", "ko", "fr", "sw"))]
old_picture = ('<source media="(max-width:680px)" '
               'srcset="/images/home-mobile/zeekr9x-city-ad.webp">'
               '<img src="/images/zeekr9x-villa.jpg"')
new_picture = ('<source media="(max-width:680px)" '
               'srcset="/images/home-mobile/zeekr9x-city-ad.webp?v=20261012-home-fast">'
               '<source media="(min-width:681px)" type="image/webp" '
               'srcset="/images/zeekr9x-villa.webp">'
               '<img src="/images/zeekr9x-villa.jpg"')
old_preload = ('<link rel="preload" as="image" '
               'href="/images/home-mobile/zeekr9x-city-ad.webp" '
               'media="(max-width:680px)" fetchpriority="high">')
new_preload = ('<link rel="preload" as="image" '
               'href="/images/home-mobile/zeekr9x-city-ad.webp?v=20261012-home-fast" '
               'media="(max-width:680px)" fetchpriority="high">'
               '<link rel="preload" as="image" '
               'href="/images/zeekr9x-villa.webp" '
               'media="(min-width:681px)" fetchpriority="high">')
old_modulepreload = ('/assets/index-autolink-membership-apply-pricing.js'
                     '?v=20261011-mobile-ad')
new_modulepreload = ('/assets/index-autolink-membership-apply-pricing.js'
                     '?v=20261012-home-fast')
for page in pages:
    content = page.read_text()
    if (content.count(old_picture) != 1 or content.count(old_preload) != 1
            or content.count(old_modulepreload) != 1):
        raise SystemExit(f"Unexpected homepage signature: {page}")
    page.write_text(content.replace(old_picture, new_picture, 1)
                    .replace(old_preload, new_preload, 1)
                    .replace(old_modulepreload, new_modulepreload, 1))

bundle = site / "assets/index-autolink-membership-apply-pricing.js"
content = bundle.read_text()
old_hero = 'zl={hero:"/images/zeekr9x-villa.jpg",film:'
new_hero = 'zl={hero:"/images/zeekr9x-villa.webp",film:'
if content.count(old_hero) != 1:
    raise SystemExit("Unexpected bundle hero signature")
bundle.write_text(content.replace(old_hero, new_hero, 1))
