"""All maintained public catalog URLs over native loopback HTTPS; no production writes."""
import argparse,json,subprocess,concurrent.futures,time
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit
from xml.etree import ElementTree
p=argparse.ArgumentParser();p.add_argument('--ca',required=True);p.add_argument('--output',required=True);p.add_argument('--site',required=True);p.add_argument('--port',default='19445');a=p.parse_args()
origin='https://autolinkglobal.com';languages=('en','zh','ar','ru','kk','uz','ko','fr','sw')
def fetch(path,head=False):
 cmd=['curl','-sS','--noproxy','*','--max-time','15','--http2','--cacert',a.ca,'--resolve','autolinkglobal.com:'+a.port+':127.0.0.1']
 if head:cmd+=['-I']
 cmd+=['-w','\n%{http_code} %{http_version}',origin+':'+a.port+path]
 r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True);b,code=r.stdout.rsplit(b'\n',1);status,version=code.decode().split();assert version=='2';return int(status),b
class Doc(HTMLParser):
 def __init__(self,body):super().__init__();self.html={};self.metas={};self.links=[];self.tag=None;self.title='';self.h1=[];self.text=[];self.feed(body)
 def handle_starttag(self,tag,attrs):
  v=dict(attrs)
  if tag=='html':self.html=v
  if tag=='meta':self.metas[v.get('name')]=v.get('content')
  if tag=='link':self.links.append(v)
  if tag=='title':self.tag='title'
  if tag=='h1':self.tag='h1';self.h1.append('')
 def handle_endtag(self,tag):
  if tag in ('title','h1'):self.tag=None
 def handle_data(self,text):
  if self.tag=='title':self.title+=text
  if self.tag=='h1':self.h1[-1]+=text
  self.text.append(text)
site=Path(a.site);models=json.loads(fetch('/autolink/public/models')[1])['data'];brands=json.loads(fetch('/autolink/public/brands')[1])['data'];assert len(models)==234 and len(brands)==53
start=time.monotonic();details=[];missing_years=[];missing_configs=[]
for m in models:
 ref=site/'model-reference'/(m['id']+'.json');d=json.loads(ref.read_text()) if ref.is_file() else {}
 if not m.get('year') and not d.get('availableYears'):missing_years.append(m['id'])
 if not d.get('variants') or not d.get('groups'):missing_configs.append(m['id'])
def check(pair):
 kind,row,lang=pair;path='/trade/'+kind+'/'+row['id'];url=path+('' if lang=='en' else '?lang='+lang);code,body=fetch(url);assert code==200,(url,code)
 text=body.decode();doc=Doc(text);assert doc.title and len(doc.h1)==1 and doc.metas.get('description') and doc.metas.get('robots')=='index, follow',url
 canonical=next(x['href'] for x in doc.links if x.get('rel')=='canonical');assert canonical==origin+url,(url,canonical)
 links={x['hreflang']:x['href'] for x in doc.links if x.get('rel')=='alternate'}
 expected={('zh-CN' if language=='zh' else language):origin+path+('' if language=='en' else '?lang='+language) for language in languages};expected['x-default']=origin+path;assert links==expected,url
 assert doc.html.get('lang')==('zh-CN' if lang=='zh' else lang);assert doc.html.get('dir')==('rtl' if lang=='ar' else 'ltr')
 if kind=='models':
  assert row['brand'] in doc.h1[0] and row['model'] in doc.h1[0]
  assert row['energy'] in text or row['bodyType'] in text or 'trade-fields' in text
  ref=site/'model-reference'/(row['id']+'.json');d=json.loads(ref.read_text()) if ref.is_file() else {}
  for year in ([row['year']] if row.get('year') else d.get('availableYears',[])):assert str(year) in ''.join(doc.text),url
  if row['id'] not in missing_configs:assert 'data-ssr-reference' in text and '<td>' in text,url
  assert '"Offer"' not in text and 'review_reason' not in text and 'password_hash' not in text
 else:assert row['name'] in doc.h1[0]
 return {'kind':kind,'id':row['id'],'lang':lang,'status':code,'title':doc.title,'canonical':canonical}
jobs=[(kind,row,language) for kind,rows in [('models',models),('brands',brands)] for row in rows for language in languages]
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:details=list(pool.map(check,jobs))
for kind,total in [('models',2106),('brands',477)]:
 code,xml=fetch('/sitemaps/'+kind+'-1.xml');assert code==200;tree=ElementTree.fromstring(xml);ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','x':'http://www.w3.org/1999/xhtml'};nodes=tree.findall('s:url',ns);assert len(nodes)==total
 for node in nodes:assert len(node.findall('x:link',ns))==10
assert fetch('/trade/models/nonexistent')[0]==404
assert b'noindex' in fetch('/trade/models/nonexistent')[1]
assert b'noindex' in fetch('/trade/compare')[1]
assert b'noindex' in fetch('/trade/models?keyword=x')[1]
assert b'x-robots-tag: noindex' in fetch('/buyer/login',True)[1].lower()
assert b'x-robots-tag: noindex' in fetch('/admin',True)[1].lower()
assert fetch('/autolink/merchants')[0]==200 and json.loads(fetch('/autolink/merchants')[1])['data']==[] # synthetic merchant was closed by preceding security tests
social=json.loads(fetch('/autolink/auth/social/config')[1])['data'];assert social=={'google':True}
robots=fetch('/robots.txt')[1].decode();assert 'Allow: /autolink/public/models/' in robots and 'Disallow: /buyer$' in robots
code,headers=fetch('/trade/models/zeekr-9x-2026?lang=zh',True);assert code==200 and b'content-type: text/html' in headers.lower()
# All resource URLs used by SSR remain public and route to real files.
for file in ['/assets/business-page-bootstrap.mjs','/assets/business-seo.js','/trade/app.js','/trade/trade.css','/trade/model-reference.css','/assets/public-directory.js']:
 assert fetch(file)[0]==200,file
result={'passed':True,'environment':'Aliyun native AMD64 isolated loopback HTTPS','certificateValidated':True,'http2':True,'models':234,'brands':53,'modelLanguagePages':2106,'brandLanguagePages':477,'pageChecks':len(details),'durationSeconds':round(time.monotonic()-start,2),'missingDetailedParameters':missing_configs,'missingYears':missing_years,'contentComplete':not(missing_years or missing_configs),'productionWrites':False,'details':details}
Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False))
