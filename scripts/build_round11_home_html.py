"""Use existing UI translations to create crawlable homepage fallbacks.

Only English and the existing Chinese homepage remain indexable. Other UI
languages remain accessible with noindex pending editorial review.
"""
from __future__ import annotations

import ast
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
ORIGIN = "https://autolinkglobal.com"
LANGUAGES = ("en", "zh", "ar", "ru", "kk", "uz", "ko", "fr", "sw")
INDEXED = ("en", "zh")
VAR_NAMES = {"zh": "mb", "ar": "ub", "fr": "hb", "ru": "pb", "ko": "db", "kk": "gb", "uz": "wb", "sw": "xb"}
INTRO_KEY = "AUTOLINK connects international vehicle buyers with Chinese automotive suppliers on a global B2B platform."
REVIEWED_TITLE = "AUTOLINK | Chinese Vehicle Sourcing & B2B Supplier Platform"
REVIEWED_DESCRIPTION = "AUTOLINK connects international vehicle buyers with Chinese automotive suppliers. Explore vehicle specifications, browse approved supplier listings, and submit sourcing inquiries."


def replace_one(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"Expected one source signature: {old[:100]}")
    return source.replace(old, new, 1)


def translations() -> dict[str, dict[str, str]]:
    bundle = (SITE / "assets/index-autolink-membership-apply-pricing.js").read_text()
    app = {"en": {}}
    for code, name in VAR_NAMES.items():
        match = re.search(r"\b" + name + r"=JSON.parse\('((?:\\.|[^'])*)'\)", bundle)
        if not match:
            raise RuntimeError(f"Missing existing UI translations: {code}")
        app[code] = json.loads(ast.literal_eval("'" + match.group(1) + "'"))
    business = {}
    for code in LANGUAGES:
        files = list((SITE / "i18n/chunks").glob(f"business-{code}-*.js"))
        if len(files) != 1:
            raise RuntimeError(f"Expected one business translation chunk: {code}")
        source = files[0].read_text()
        prefix = 'window.AUTOLINK_BUSINESS_RESOURCES=Object.assign(window.AUTOLINK_BUSINESS_RESOURCES||{},'
        if not source.startswith(prefix) or not source.endswith(');\n'):
            raise RuntimeError(f"Unexpected business translation format: {code}")
        business[code] = json.loads(source[len(prefix):-3])[code]["translation"]
    return {code: app[code] | business[code] for code in LANGUAGES}


def localized_url(code: str) -> str:
    return ORIGIN + "/" + ("?lang=" + code if code != "en" else "")


def fallback(code: str, t: dict[str, str]) -> str:
    def tr(key: str) -> str:
        return html.escape(t.get(key, key), quote=True)

    form_language = f'<input type="hidden" name="lang" value="{code}">' if code != "en" else ""
    return f'''<!-- round11-home-fallback-start --><div id="root"><div class="home-static">
<nav class="home-static-nav" aria-label="{tr('Main navigation')}"><a href="/">AUTOLINK</a><a href="/trade/vehicles">{tr('Vehicles')}</a><a href="/trade/brands">{tr('Brands')}</a><a href="/trade/models">{tr('Model references')}</a><a href="/about">About AUTOLINK</a></nav>
<main id="main-content"><section class="home-static-hero" aria-label="AUTOLINK vehicle sourcing">
<picture><source media="(max-width:680px)" srcset="/images/home-mobile/zeekr9x-city-ad.webp"><img src="/images/zeekr9x-villa.jpg" width="1920" height="1080" fetchpriority="high" alt="Zeekr 9X model illustration"></picture>
<div class="home-static-copy"><p class="home-static-kicker">{tr('FROM CHINA. TO YOUR WORLD.')}</p><h1>{tr('Source China.')}<br>{tr('Drive Global.')}</h1><p class="home-static-intro">{tr(INTRO_KEY)}</p>
<form class="home-static-search" method="get" action="/trade/vehicles"><label class="sr-only" for="home-static-keyword">{tr('Search brand or model')}</label><input id="home-static-keyword" name="keyword" type="search" maxlength="80" placeholder="{tr('Search brand or model')}">{form_language}<button type="submit">{tr('Search Vehicles')}</button></form>
<div class="home-static-actions"><a href="/trade/vehicles">{tr('Explore vehicles')}</a><a href="/trade/brands">{tr('Brands')}</a></div></div></section>
<section class="home-static-discover"><h2>{tr('Model references')}</h2><p>{tr('Model references do not prove stock or availability. Confirm exact specifications and trade terms directly with the supplier.')}</p>
<a href="/trade/brands/geely">Geely</a><a href="/trade/brands/byd">BYD</a><a href="/trade/brands/zeekr">Zeekr</a><a href="/trade/models">{tr('Model references')}</a><a href="/about">About AUTOLINK</a></section></main></div></div><!-- round11-home-fallback-end -->'''


def main() -> None:
    data = translations()
    source = (SITE / "index.html").read_text()
    source = re.sub(r"<!-- round11-home-fallback-start -->.*?<!-- round11-home-fallback-end -->", '<div id="root"></div>', source, flags=re.S)
    source = re.sub(r"<!-- round11-home-head-start -->.*?<!-- round11-home-head-end -->", "", source, flags=re.S)
    source = replace_one(source, '<div id="root"></div>', '<!-- round11-home-fallback -->')
    source = source.replace('20261012-home-fast', '20261011-mobile-ad')
    source = source.replace('/assets/business-language-loader.mjs?v=20261009-gx', '/assets/business-language-loader.mjs?v=20261009-speed')
    for code in LANGUAGES:
        t = data[code]
        lang_tag = "zh-CN" if code == "zh" else code
        title = REVIEWED_TITLE if code == "en" else "AUTOLINK — " + t["Source China."] + " " + t["Drive Global."]
        description = REVIEWED_DESCRIPTION if code == "en" else t[INTRO_KEY]
        robots = "index, follow" if code in INDEXED else "noindex, follow"
        content = source
        content = re.sub(r'<html lang="[^"]+"(?: dir="[^"]+")?', f'<html lang="{lang_tag}" dir="{"rtl" if code == "ar" else "ltr"}"', content, count=1)
        content = re.sub(r'<title>.*?</title>', '<title>' + html.escape(title) + '</title>', content, count=1)
        content = re.sub(r'(<meta name="description" content=")[^"]*("/>)', lambda m: m[1] + html.escape(description, quote=True) + m[2], content, count=1)
        content = re.sub(r'(<meta name="robots" content=")[^"]*("/>)', lambda m: m[1] + robots + m[2], content, count=1)
        content = re.sub(r'(<link rel="canonical" href=")[^"]*("/>)', lambda m: m[1] + localized_url(code) + m[2], content, count=1)
        for property_name, value in (("og:title", title), ("og:description", description), ("og:url", localized_url(code))):
            content = re.sub(r'(<meta property="' + property_name + r'" content=")[^"]*("/>)', lambda m: m[1] + html.escape(value, quote=True) + m[2], content, count=1)
        alternates = ''.join(f'<link rel="alternate" hreflang="{("zh-CN" if other == "zh" else other)}" href="{localized_url(other)}">' for other in INDEXED)
        alternates += f'<link rel="alternate" hreflang="x-default" href="{ORIGIN}/">'
        head = '<!-- round11-home-head-start --><link rel="stylesheet" href="/assets/home-public-fallback.css?v=20261012-round11"><link rel="preload" as="image" href="/images/home-mobile/zeekr9x-city-ad.webp" media="(max-width:680px)" fetchpriority="high">' + alternates
        head += '<meta name="twitter:card" content="summary"><meta name="twitter:title" content="' + html.escape(title, quote=True) + '"><meta name="twitter:description" content="' + html.escape(description, quote=True) + '"><!-- round11-home-head-end -->'
        # Discover the mobile hero before the legacy styles and large module.
        icon = '<link rel="icon" type="image/svg+xml" href="/favicon.svg"/>'
        content = replace_one(content, icon, icon + head)
        content = replace_one(content, '<!-- round11-home-fallback -->', fallback(code, t))
        destination = SITE / ('index.html' if code == 'en' else f'index.{code}.html')
        destination.write_text(content)
        print(code, destination.relative_to(ROOT), len(content), robots)


if __name__ == '__main__':
    main()
