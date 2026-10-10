"""Read-only initial HTML quality audit, not a Google index/ranking assertion."""
import argparse,collections,concurrent.futures,hashlib,json,re,subprocess,time
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET
p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args();R=Path(a.root);E=R/'evidence';port='19449';langs=('en','zh','ar','ru','kk','uz','ko','fr','sw');origin='https://autolinkglobal.com'
def fetch(path,bot=False):
 cmd=['curl','-sS','--noproxy','*','--max-time','15','--http2','--cacert',str(R/'tls/ca.crt'),'--resolve','autolinkglobal.com:'+port+':127.0.0.1']
 if bot:cmd+=['-A','Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)']
 result=subprocess.run(cmd+['-w','\n%{http_code} %{http_version}',origin+':'+port+path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);body,tail=result.stdout.rsplit(b'\n',1);code,version=tail.decode().split();assert code=='200' and version=='2',path;return body.decode()
class Visible(HTMLParser):
 def __init__(self,s):
  super().__init__();self.inmain=False;self.skip=0;self.refdepth=0;self.text=[];self.ref=[];self.h1=[];self.title=[];self.tag='';self.meta={};self.links=[];self.feed(s)
 def handle_starttag(self,tag,attrs):
  d=dict(attrs)
  if tag=='main':self.inmain=True
  if tag in ('script','style'):self.skip+=1
  if tag=='meta':self.meta[d.get('name')]=d.get('content')
  if tag=='link':self.links.append(d)
  if tag in ('h1','title'):self.tag=tag
  if tag=='section' and ('data-ssr-reference' in d or self.refdepth):self.refdepth+=1
 def handle_endtag(self,tag):
  if tag=='main':self.inmain=False
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
  if tag in ('h1','title'):self.tag=''
  if tag=='section' and self.refdepth:self.refdepth-=1
 def handle_data(self,text):
  if not text.strip() or self.skip:return
  if self.tag=='title':self.title.append(text)
  if self.tag=='h1':self.h1.append(text)
  if self.inmain:self.text.append(text)
  if self.refdepth:self.ref.append(text)
models=json.loads(fetch('/autolink/public/models'))['data'];brands=json.loads(fetch('/autolink/public/brands'))['data'];assert len(models)==234 and len(brands)==53
start=time.monotonic()
def check(job):
 kind,row,lang=job;path='/trade/'+kind+'/'+row['id'];url=path+('' if lang=='en' else '?lang='+lang);s=fetch(url);d=Visible(s)
 ref_file=R/'source/site/model-reference'/(row['id']+'.json')
 ref=json.loads(ref_file.read_text()) if kind=='models' and ref_file.is_file() else {}
 complete=bool(ref.get('variants') and ref.get('groups')) if kind=='models' else False
 indexable=kind=='models' and complete and lang=='zh'
 expected={'zh-CN':origin+path+'?lang=zh','x-default':origin+path+'?lang=zh'} if indexable else {}
 assert d.meta.get('robots')==('index, follow' if indexable else 'noindex, follow'),url
 assert next(x['href'] for x in d.links if x.get('rel')=='canonical')==origin+url,url
 assert d.title and len(d.h1)==1 and d.meta.get('description'),url
 assert (row['model'] in ' '.join(d.h1) and row['brand'] in ' '.join(d.h1)) if kind=='models' else row['name'] in ' '.join(d.h1),url
 if complete:assert d.ref,url
 alt={x['hreflang']:x['href'] for x in d.links if x.get('rel')=='alternate'};assert alt==expected,url
 text=' '.join(d.text);ref=' '.join(d.ref);cjk=re.findall(r'[\u3400-\u9fff]+',text);refcjk=re.findall(r'[\u3400-\u9fff]+',ref)
 return {'kind':kind,'id':row['id'],'lang':lang,'title':' '.join(d.title),'h1':' '.join(d.h1),'mainTextSHA256':hashlib.sha256(text.encode()).hexdigest(),'mainCharacters':len(text),'cjkCharacters':sum(map(len,cjk)),'cjkSamples':list(dict.fromkeys(cjk))[:12],'referenceCjkSamples':list(dict.fromkeys(refcjk))[:12],'referenceTable':bool(d.ref),'index':d.meta.get('robots'),'alternateLinks':alt,'description':d.meta.get('description')}
jobs=[(kind,row,lang) for kind,rows in [('models',models),('brands',brands)] for row in rows for lang in langs]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:details=list(pool.map(check,jobs))
missing=[]
for row in models:
 f=R/'source/site/model-reference'/(row['id']+'.json');ref=json.loads(f.read_text()) if f.is_file() else {}
 if not ref.get('variants') or not ref.get('groups'):
  page=next(d for d in details if d['kind']=='models' and d['id']==row['id'] and d['lang']=='en')
  missing.append({'id':row['id'],'name':row['brand']+' '+row['model'],'catalogYear':row['year'],'referenceYears':ref.get('availableYears',[]),'description':row.get('description'),'specifications':row.get('specifications'),'energy':row['energy'],'bodyType':row['bodyType'],'currentRobots':page['index'],'mainCharactersEN':page['mainCharacters'],'uniqueEditorialContent':bool(row.get('description') or row.get('specifications'))})
stats={}
duplicates={}
for lang in langs:
 rows=[d for d in details if d['lang']==lang];groups={}
 for field in ['title','description','h1','mainTextSHA256']:
  by=collections.defaultdict(list)
  for r in rows:by[r[field]].append(r['kind']+'/'+r['id'])
  groups[field]=[ids for ids in by.values() if len(ids)>1]
 duplicates[lang]=groups
 stats[lang]={'pages':len(rows),'modelsWithCJK':sum(r['kind']=='models' and r['cjkCharacters']>0 for r in rows),'brandsWithCJK':sum(r['kind']=='brands' and r['cjkCharacters']>0 for r in rows),'modelsWithReferenceCJK':sum(bool(r['referenceCjkSamples']) for r in rows if r['kind']=='models'),'maxCJKCharacters':max(r['cjkCharacters'] for r in rows),'exactDuplicateMainGroups':len(groups['mainTextSHA256'])}
# Reciprocal/self/canonical relationships checked across every fetched page and XML node.
index={origin+'/trade/'+d['kind']+'/'+d['id']+('' if d['lang']=='en' else '?lang='+d['lang']):d for d in details}
for r in details:
 for target in r['alternateLinks'].values():assert target in index and index[target]['alternateLinks']==r['alternateLinks']
xmlcounts={}
for kind,total in [('models',195),('brands',0)]:
 tree=ET.fromstring(fetch('/sitemaps/'+kind+'-1.xml'));ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','x':'http://www.w3.org/1999/xhtml'};nodes=tree.findall('s:url',ns);assert len(nodes)==total
 locations=[]
 for n in nodes:
  loc=n.findtext('s:loc',namespaces=ns);locations.append(loc);assert loc in index
  assert {l.attrib['hreflang']:l.attrib['href'] for l in n.findall('x:link',ns)}==index[loc]['alternateLinks']
 assert len(set(locations))==total
 if kind=='models':assert set(locations)=={url for url,d in index.items() if d['kind']=='models' and d['index']=='index, follow'}
 xmlcounts[kind]=total
bot=[]
for row in models[:1]+[r for r in models if r['id']=='omoda-catalog-1']:
 for lang in ('en','zh','ar','ru','fr','sw'):
  path='/trade/models/'+row['id']+('' if lang=='en' else '?lang='+lang);assert fetch(path,True)==fetch(path);bot.append(path)

assert len(missing)==39 and sum(d['index']=='index, follow' for d in details)==195
assert fetch('/autolink/merchants') and json.loads(fetch('/autolink/merchants'))['data']==[]
assert json.loads(fetch('/autolink/auth/social/config'))['data']=={'google':True}
robots=fetch('/robots.txt');assert 'Disallow: /trade/models' not in robots and 'Disallow: /trade/brands' not in robots
assert 'Allow: /autolink/public/models/' in robots
for file in ['/assets/business-page-bootstrap.mjs','/assets/business-seo.js','/trade/app.js','/trade/model-reference.mjs','/trade/trade.css','/locales/seo-verified-terms.json']:
 assert fetch(file)

result={'atUTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'nativeAMD64LoopbackHTTPS':True,'pageCount':len(details),'reciprocalAlternatesPassed':len(details),'sitemapCounts':xmlcounts,'languages':stats,'duplicates':duplicates,'thinModels':missing,'thinModelsWithNoUniqueEditorialOrSpecs':sum(not m['uniqueEditorialContent'] for m in missing),'thinModelsCurrentIndexable':sum(m['currentRobots']=='index, follow' for m in missing),'indexableDetailURLs':sum(d['index']=='index, follow' for d in details),'noindexDetailURLs':sum(d['index']=='noindex, follow' for d in details),'realCatalogModels':len(models),'realCatalogBrands':len(brands),'googlebotIdenticalHTMLRequests':len(bot),'elapsedSeconds':round(time.monotonic()-start,2),'details':details}
(E/'seo-http.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print('ROUND7_FULL_CONTENT_AND_INDEX_ACCEPTANCE',json.dumps({k:v for k,v in result.items() if k not in ('details','thinModels','duplicates')},ensure_ascii=False),flush=True)
