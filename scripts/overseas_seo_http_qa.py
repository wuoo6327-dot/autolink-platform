"""Isolated Caddy/HTTP crawl of all public detail pages and index gates."""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

BASE = sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:18181'
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('tests/results/overseas-seo-http-20261012.json')
LANGS = ('en','zh','ar','ru','kk','uz','ko','fr','sw')
ORIGIN = 'https://autolinkglobal.com'


def fetch(path, agent='AUTOLINK-isolated-QA/1.0'):
    request = urllib.request.Request(BASE+path,headers={'User-Agent':agent})
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            return response.status,response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code,error.read().decode()


class Page(HTMLParser):
    def __init__(self,source):
        super().__init__();self.h1='';self.in_h1=False;self.html_lang='';self.canonical='';self.robots='';self.alternates={}
        self.feed(source)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='html':self.html_lang=attrs.get('lang','')
        if tag=='h1':self.in_h1=True
        if tag=='meta' and attrs.get('name')=='robots':self.robots=attrs.get('content','')
        if tag=='link' and attrs.get('rel')=='canonical':self.canonical=attrs.get('href','')
        if tag=='link' and attrs.get('rel')=='alternate':self.alternates[attrs.get('hreflang','')]=attrs.get('href','')
    def handle_endtag(self,tag):
        if tag=='h1':self.in_h1=False
    def handle_data(self,data):
        if self.in_h1:self.h1+=data


def main():
    started=time.monotonic()
    models=json.loads(fetch('/autolink/public/models')[1])['data']
    brands=json.loads(fetch('/autolink/public/brands')[1])['data']
    jobs=[(kind,entry,lang) for kind,rows in (('models',models),('brands',brands)) for entry in rows for lang in LANGS]
    def check(job):
        kind,entry,lang=job;path='/trade/'+kind+'/'+entry['id'];url=path+('' if lang=='en' else '?lang='+lang)
        code,body=fetch(url);page=Page(body);issues=[]
        if code!=200:issues.append(f'http:{code}')
        if 'data-ssr="true"' not in body:issues.append('missing-ssr')
        name=entry['model'] if kind=='models' else entry['name']
        if name not in page.h1:issues.append('h1')
        if page.html_lang!=('zh-CN' if lang=='zh' else lang):issues.append('html-lang')
        if page.canonical!=ORIGIN+url:issues.append('canonical')
        allowed=lang in entry['seo']['indexLanguages']
        if page.robots!=('index, follow' if allowed else 'noindex, follow'):issues.append('robots')
        if bool(page.alternates)!=allowed:issues.append('alternates')
        if 'REG123' in body or 'PRIVATE_REVIEW_MARKER' in body:issues.append('private-marker')
        return url,issues
    with ThreadPoolExecutor(max_workers=12) as pool:
        results=list(pool.map(check,jobs))
    failures={path:issues for path,issues in results if issues}
    ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
    sitemap={}
    for section in ('models','brands','static'):
        code,body=fetch('/sitemaps/'+section+'-1.xml')
        sitemap[section]=[] if code!=200 else [node.text for node in ElementTree.fromstring(body).findall('.//s:loc',ns)]
    expected_models={ORIGIN+'/trade/models/'+item['id']+('' if lang=='en' else '?lang='+lang)
        for item in models for lang in item['seo']['indexLanguages']}
    expected_brands={ORIGIN+'/trade/brands/'+item['id']+('' if lang=='en' else '?lang='+lang)
        for item in brands for lang in item['seo']['indexLanguages']}
    agent='Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/131.0.0.0 Mobile Safari/537.36'
    parity={path:fetch(path)[1]==fetch(path,agent)[1] for path in
        ('/trade/models/geely-catalog-3','/trade/models/geely-catalog-3?lang=ar','/trade/brands/byd','/trade/brands/aion')}
    guide=Page(fetch('/guide/middle-east-importers')[1])
    arabic=Page(fetch('/guide/middle-east-importers?lang=ar')[1])
    africa=Page(fetch('/guide/african-importers')[1])
    africa_fallback=Page(fetch('/guide/african-importers?lang=fr')[1])
    eligible_by_language={lang:sum(lang in item['seo']['indexLanguages'] for item in models)
        for lang in LANGS}
    eligible_brands_by_language={lang:sum(lang in item['seo']['indexLanguages'] for item in brands)
        for lang in LANGS}
    output={'checkedAt':datetime.now(timezone.utc).isoformat(),'base':BASE,'models':len(models),'brands':len(brands),
        'detailLanguagePages':len(jobs),'detailFailures':failures,
        'indexableModels':len(expected_models),'indexableBrands':len(expected_brands),
        'indexableModelsByLanguage':eligible_by_language,
        'indexableBrandsByLanguage':eligible_brands_by_language,
        'sitemapCounts':{key:len(value) for key,value in sitemap.items()},
        'sitemapExact':set(sitemap['models'])==expected_models and set(sitemap['brands'])==expected_brands,
        'marketGuide':{'canonical':guide.canonical,'robots':guide.robots,
            'arabicRobots':arabic.robots,'arabicLang':arabic.html_lang,
            'africaCanonical':africa.canonical,'africaRobots':africa.robots,
            'unreviewedFrenchRobots':africa_fallback.robots,
            'inEnglishSitemap':ORIGIN+'/guide/middle-east-importers' in sitemap['static'],
            'africaInEnglishSitemap':ORIGIN+'/guide/african-importers' in sitemap['static']},
        'userAgentParity':parity,'unknownModelStatus':fetch('/trade/models/unknown-model')[0],
        'anonymousAdminStatus':fetch('/autolink/admin/seo/status')[0],
        'elapsedSeconds':round(time.monotonic()-started,2)}
    output['pass']=(not failures and len(models)==244 and len(brands)==53 and len(jobs)==2673
        and eligible_by_language['en']>=51 and eligible_by_language['zh']>=177
        and eligible_brands_by_language['en']>=11 and output['sitemapExact']
        and all(parity.values()) and output['unknownModelStatus']==404 and output['anonymousAdminStatus']==401
        and guide.robots=='index, follow' and arabic.robots=='noindex, follow'
        and arabic.html_lang=='ar' and not arabic.alternates
        and africa.robots=='index, follow' and africa_fallback.robots=='noindex, follow'
        and output['marketGuide']['inEnglishSitemap'] and output['marketGuide']['africaInEnglishSitemap'])
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({key:value for key,value in output.items() if key!='detailFailures'},ensure_ascii=False))
    return 0 if output['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
