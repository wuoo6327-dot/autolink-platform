"""Public HTML and multilingual discovery; local temporary database only."""
import json
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request
from xml.etree import ElementTree

from app import Handler
from buyer_service import BuyerError
from buyer_service import BuyerService
from seo_service import PublicSEOService, LANGUAGES, LANGUAGE_TAGS, localized_url
import test_trade


class HTMLDocument(HTMLParser):
    def __init__(self, source):
        super().__init__();self.title='';self.h1=[];self.links=[];self.metas=[];self.script_sources=[];self.html={};self.apps=[];self.tag=None
        self.feed(source)
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=='html':self.html=values
        if tag=='title':self.tag='title'
        if tag=='h1':self.tag='h1';self.h1.append('')
        if tag=='link':self.links.append(values)
        if tag=='meta':self.metas.append(values)
        if tag=='script' and 'src' in values:self.script_sources.append(values['src'])
        if values.get('id')=='app':self.apps.append(values)
    def handle_endtag(self,tag):
        if tag in ('title','h1'):self.tag=None
    def handle_data(self,value):
        if self.tag=='title':self.title+=value
        if self.tag=='h1':self.h1[-1]+=value
    def alternates(self):
        return {item['hreflang']:item['href'] for item in self.links if item.get('rel')=='alternate'}
    def canonical(self):
        return next(item['href'] for item in self.links if item.get('rel')=='canonical')


class PublicSEOTests(unittest.TestCase):
    approved_vehicle=test_trade.TradeFlowTests.approved_vehicle
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        self.seo=PublicSEOService(self.trade,Path(__file__).resolve().parent.parent/'site')
    def snapshot(self):
        with self.auth.connect() as db:return '\n'.join(db.iterdump())
    def test_initial_model_directory_and_detail_work_without_javascript(self):
        before=self.snapshot()
        self.assertEqual(len(self.trade.catalog.models()),244)
        status,body=self.seo.render('/trade/models?lang=zh')
        document=HTMLDocument(body.decode())
        self.assertEqual(status,200);self.assertIn('车型',document.title)
        self.assertIn('探索中国汽车车型。',document.h1)
        self.assertIn('244',body.decode())
        status,body=self.seo.render('/trade/models/aeolus-catalog-1?lang=zh')
        document=HTMLDocument(body.decode())
        self.assertEqual(status,200);self.assertIn('Haohan',document.title)
        self.assertIn('Aeolus Haohan',document.h1)
        self.assertIn('配置参数',body.decode())
        self.assertIn('2026',body.decode())
        self.assertEqual(document.apps[0].get('data-ssr'),'true')
        self.assertTrue(any('/assets/business-page-bootstrap.mjs' in src for src in document.script_sources))
        self.assertEqual(self.snapshot(),before)
    def test_all_nine_language_canonical_and_only_reviewed_alternates(self):
        path='/trade/models/aeolus-catalog-1'
        expected={'zh-CN':localized_url(path,'zh'),'x-default':localized_url(path,'zh')}
        for language in LANGUAGES:
            with self.subTest(language=language):
                status,body=self.seo.render(path+'?lang='+language)
                document=HTMLDocument(body.decode())
                self.assertEqual(status,200)
                self.assertEqual(document.canonical(),localized_url(path,language))
                self.assertEqual(document.alternates(),expected if language=='zh' else {})
                self.assertIn('index, follow' if language=='zh' else 'noindex, follow',next(item['content'] for item in document.metas if item.get('name')=='robots'))
                self.assertEqual(document.html['lang'],LANGUAGE_TAGS[language])
                self.assertEqual(document.html['dir'],'rtl' if language=='ar' else 'ltr')

    def test_model_and_brand_show_only_current_approved_public_supply(self):
        model_path='/trade/models/zeekr-9x-2026'
        brand_path='/trade/brands/zeekr'
        self.assertIn('No approved vehicle listings yet.',self.seo.render(model_path)[1].decode())
        listing=self.approved_vehicle()
        for path in (model_path,brand_path):
            body=self.seo.render(path)[1].decode()
            self.assertIn('/trade/vehicles/'+listing,body)
            self.assertIn('China Export Co',body)
            for private in ('REG123','+8613800000000','buyer-a@example.com'):
                self.assertNotIn(private,body)
        self.trade.transition_vehicle(self.users['supplier-a'],listing,'offline')
        for path in (model_path,brand_path):
            self.assertNotIn('/trade/vehicles/'+listing,self.seo.render(path)[1].decode())
    def test_sitemap_has_reviewed_source_and_english_models(self):
        root=ElementTree.fromstring(self.trade.sitemap_xml('models-1.xml'))
        ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','x':'http://www.w3.org/1999/xhtml'}
        urls=root.findall('s:url',ns)
        locations=[node.find('s:loc',ns).text for node in urls]
        self.assertEqual(len(locations),229)
        self.assertEqual(len(set(locations)),229)
        self.assertEqual(sum(url.endswith('?lang=zh') for url in locations),177)
        self.assertEqual(sum('?' not in url for url in locations),52)
        self.assertFalse(any('byd-shark' in url for url in locations))
        for node in urls:
            actual={link.attrib['hreflang']:link.attrib['href'] for link in node.findall('x:link',ns)}
            path=node.find('s:loc',ns).text.split('autolinkglobal.com',1)[1].split('?',1)[0]
            reviews=json.loads((Path(__file__).resolve().parent.parent/'site/locales/seo-model-en-reviewed.json').read_text())
            english=reviews.get(path.rsplit('/',1)[-1],{}).get('status')=='approved'
            expected={'zh-CN':localized_url(path,'zh'),'x-default':localized_url(path,'en' if english else 'zh')}
            if english:expected['en']=localized_url(path,'en')
            self.assertEqual(actual,expected)
        index=self.trade.sitemap_xml('sitemap.xml').decode()
        self.assertNotIn('vehicles-1.xml',index)
        self.assertNotIn('suppliers-1.xml',index)
        for empty in ('vehicles-1.xml','suppliers-1.xml'):
            with self.assertRaises(BuyerError):self.trade.sitemap_xml(empty)
    def test_unknown_private_and_deactivated_pages_are_not_indexable(self):
        for path in ('/trade/models/nonexistent','/trade/models/../buyer','/buyer/private','/trade/private','/trade/models/a/b'):
            with self.subTest(path=path):
                status,body=self.seo.render(path)
                self.assertEqual(status,404)
                self.assertIn('noindex',body.decode())
                self.assertEqual(HTMLDocument(body.decode()).alternates(),{})
        with self.auth.connect() as db:db.execute("UPDATE catalog_models SET active=0 WHERE id='aeolus-catalog-1'")
        self.assertEqual(self.seo.render('/trade/models/aeolus-catalog-1')[0],404)
    def test_public_inventory_html_never_publishes_private_price_contact_or_documents(self):
        listing=self.approved_vehicle()
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_vehicles SET price_minor=987654321,review_reason='PRIVATE_REVIEW_MARKER' WHERE id=?",(listing,))
            db.execute("UPDATE supplier_profiles SET public_contact_enabled=1,public_contact_email='private-marker@example.com' WHERE user_id='supplier-a'")
        before=self.snapshot()
        for path in ('/trade/vehicles/'+listing,'/trade/vehicles','/trade/suppliers/supplier-a','/trade/suppliers'):
            status,body=self.seo.render(path);source=body.decode()
            self.assertEqual(status,200)
            for private in ('987654321','private-marker@example.com','PRIVATE_REVIEW_MARKER','supplier-a@example.com','/data/private','stored_name','"Offer"'):
                self.assertNotIn(private,source)
        self.assertEqual(self.snapshot(),before)
        with self.auth.connect() as db:db.execute("UPDATE users SET status='SUSPENDED' WHERE id='supplier-a'")
        self.assertEqual(self.seo.render('/trade/vehicles/'+listing)[0],404)
        self.assertEqual(self.seo.render('/trade/suppliers/supplier-a')[0],404)
    def test_admin_maintained_text_is_escaped_in_html_and_jsonld(self):
        model=self.trade.catalog.get('aeolus-catalog-1')
        self.trade.catalog.save_model(self.users['admin'],{**model,'model':'Synthetic <script>alert(1)</script> \\g<0> & "quote"'},model['id'])
        status,body=self.seo.render('/trade/models/'+model['id']+'?lang=zh')
        source=body.decode();self.assertEqual(status,200)
        self.assertNotIn('<script>alert(1)</script>',source)
        self.assertIn('&lt;script&gt;',source)
        self.assertIn('\\u003cscript',source)
    def test_http_get_head_status_content_and_trusted_canonical(self):
        Handler.service=self.auth;Handler.trade=self.trade;Handler.buyer=BuyerService(self.auth)
        Handler.platform=self.trade.platform;Handler.seo=self.seo
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        path='/autolink/public/seo/trade/models/aeolus-catalog-1?lang=zh'
        with urllib.request.urlopen(urllib.request.Request(base+path,headers={'Host':'untrusted.example'})) as response:
            body=response.read();length=int(response.headers['Content-Length'])
            self.assertIn('text/html',response.headers['Content-Type'])
            self.assertEqual(length,len(body))
            self.assertEqual(HTMLDocument(body.decode()).canonical(),localized_url('/trade/models/aeolus-catalog-1','zh'))
        with urllib.request.urlopen(urllib.request.Request(base+path,method='HEAD')) as response:
            self.assertEqual(response.read(),b'');self.assertEqual(int(response.headers['Content-Length']),length)
        with urllib.request.urlopen(base+'/autolink/public/models') as response:
            self.assertIn('noindex',response.headers.get('X-Robots-Tag',''))
        with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(base+'/autolink/public/seo/trade/models/unknown')
        self.assertEqual(error.exception.code,404)
        self.assertIn('noindex',error.exception.read().decode())

if __name__=='__main__':unittest.main()
