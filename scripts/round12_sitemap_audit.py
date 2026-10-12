"""Read-only public sitemap and URL consistency audit.

Stores status and metadata, never customer data or full page bodies.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from pathlib import Path

ORIGIN = "https://autolinkglobal.com"
# For isolated QA, fetch the same logical production URLs through loopback.
# Canonical and Sitemap origins are still checked against the public domain.
FETCH_BASE = os.environ.get('SITEMAP_FETCH_BASE', ORIGIN).rstrip('/')
NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9",
      "x": "http://www.w3.org/1999/xhtml"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def get(url: str):
    transport = FETCH_BASE + url[len(ORIGIN):] if url.startswith(ORIGIN + '/') else url
    request = urllib.request.Request(transport, headers={"User-Agent": "AUTOLINK-Sitemap-QA/1.0", "Accept-Encoding": "identity"})
    try:
        with OPENER.open(request, timeout=20) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers.items()), error.read(4096)


class Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonical = []
        self.robots = []
        self.alternates = {}
        self.lang = ""

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "html":
            self.lang = attrs.get("lang", "")
        if tag == "link":
            rel = attrs.get("rel", "").lower().split()
            if "canonical" in rel:
                self.canonical.append(attrs.get("href", ""))
            if "alternate" in rel and attrs.get("hreflang"):
                self.alternates[attrs["hreflang"]] = attrs.get("href", "")
        if tag == "meta" and attrs.get("name", "").lower() == "robots":
            self.robots.append(attrs.get("content", ""))


def check_url(url: str):
    result = {"url": url, "issues": []}
    try:
        status, headers, body = get(url)
        result.update(status=status, contentType=headers.get("Content-Type", ""),
                      responseBytes=len(body), xRobotsTag=headers.get("X-Robots-Tag", ""))
        if status != 200:
            result["issues"].append("http_" + str(status))
            return result
        if "text/html" not in result["contentType"].lower():
            result["issues"].append("non_html")
        parser = Head()
        parser.feed(body.decode("utf-8", "replace"))
        result.update(canonical=parser.canonical, robots=parser.robots,
                      htmlLang=parser.lang, hreflang=parser.alternates)
        if parser.canonical != [url]:
            result["issues"].append("canonical_mismatch")
        if "noindex" in (" ".join(parser.robots) + " " + result["xRobotsTag"]).lower():
            result["issues"].append("noindex")
    except Exception as error:
        result["issues"].append("request_" + type(error).__name__)
    return result


def run(output: Path):
    index_status, index_headers, index_body = get(ORIGIN + "/sitemap.xml")
    if (index_status != 200 or 'xml' not in index_headers.get('Content-Type', '').lower()
            or len(index_body) > 50 * 1024 * 1024):
        raise RuntimeError('Root Sitemap HTTP, type or size is invalid')
    index = ET.fromstring(index_body)
    if index.tag != "{" + NS["s"] + "}sitemapindex":
        raise RuntimeError("root is not a sitemapindex")
    children = [item.findtext("s:loc", namespaces=NS) for item in index.findall("s:sitemap", NS)]
    if (not children or len(children) > 50000 or len(children) != len(set(children))
            or any(not child or not child.startswith(ORIGIN + '/sitemaps/') for child in children)):
        raise RuntimeError('Root Sitemap child locations are invalid')
    rows = []
    xml_alternates = {}
    child_results = []
    for child in children:
        status, headers, body = get(child)
        if status != 200 or 'xml' not in headers.get('Content-Type', '').lower() or len(body) > 50 * 1024 * 1024:
            raise RuntimeError(f'Child Sitemap HTTP, type or size invalid: {child}')
        tree = ET.fromstring(body)
        urls = []
        for node in tree.findall("s:url", NS):
            url = node.findtext("s:loc", namespaces=NS)
            urls.append(url)
            xml_alternates[url] = {link.get("hreflang"): link.get("href")
                                   for link in node.findall("x:link", NS)}
        child_results.append({"url": child, "status": status,
                              "contentType": headers.get("Content-Type", ""),
                              "bytes": len(body), "urlCount": len(urls),
                              "rootTag": tree.tag})
        if tree.tag != "{" + NS["s"] + "}urlset":
            raise RuntimeError(child + " is not a urlset")
        if not urls or len(urls) > 50000:
            raise RuntimeError(f'Child Sitemap URL count invalid: {child}')
        rows.extend(urls)
    issues = []
    duplicates = [url for url, count in Counter(rows).items() if count > 1]
    if duplicates:
        issues.append({"type": "duplicate_urls", "count": len(duplicates), "examples": duplicates[:10]})
    model_status, _, model_body = get(ORIGIN + '/autolink/public/models?limit=500')
    brand_status, _, brand_body = get(ORIGIN + '/autolink/public/brands')
    if model_status != 200 or brand_status != 200:
        raise RuntimeError('Public catalog could not be checked against Sitemap')
    models = json.loads(model_body)['data']
    brands = json.loads(brand_body)['data']
    model_ids = {item['id'] for item in models}
    brand_ids = {item['id'] for item in brands}
    for url in rows:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "autolinkglobal.com":
            issues.append({"type": "invalid_origin", "url": url})
        if re.search(r"%(?![0-9a-fA-F]{2})|[\s\x00-\x1f]", url):
            issues.append({"type": "invalid_encoding", "url": url})
        for prefix, known in (('/trade/models/', model_ids), ('/trade/brands/', brand_ids)):
            if parsed.path.startswith(prefix) and urllib.parse.unquote(parsed.path[len(prefix):]) not in known:
                issues.append({"type": "unpublished_entity", "url": url})
        for language, alternate in xml_alternates[url].items():
            if alternate not in rows:
                issues.append({"type": "xml_alternate_outside_sitemap", "url": url,
                               "language": language, "alternate": alternate})
    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(check_url, url) for url in rows]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["url"])
    url_set = set(rows)
    for item in results:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(item["url"]).query)
        language = query.get("lang", ["en"])[0]
        expected = "zh-CN" if language == "zh" else language
        if item.get("htmlLang") and item["htmlLang"] != expected:
            item["issues"].append("html_lang_mismatch")
        if any(alternate not in url_set for alternate in item.get("hreflang", {}).values()):
            item["issues"].append("html_alternate_outside_sitemap")
    counts = Counter(issue for item in results for issue in item["issues"])
    summary = {"origin": ORIGIN, "fetchBase": FETCH_BASE,
               "publicCatalogCounts": {"models": len(models), "brands": len(brands)},
               "index": {"status": index_status,
                 "contentType": index_headers.get("Content-Type", ""),
                 "bytes": len(index_body), "rootTag": index.tag},
               "children": child_results, "urlCount": len(rows),
               "uniqueUrlCount": len(set(rows)), "issueCounts": dict(counts),
               "structureIssues": issues, "urlChecks": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key != "urlChecks"}, indent=2))
    if issues or counts:
        print("Examples:", json.dumps([item for item in results if item["issues"]][:12], ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run(Path(sys.argv[1] if len(sys.argv) > 1 else "tests/results/round12/sitemap-audit.json")))
