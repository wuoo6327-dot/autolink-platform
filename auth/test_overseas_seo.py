"""English editorial, brand, sitemap and market-guide publication boundaries."""
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree

from seo_service import PublicSEOService
from test_seo import HTMLDocument
import test_trade


ROOT = Path(__file__).resolve().parent.parent


class OverseasSEOTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp

    def test_reviewed_english_content_is_distinct_and_source_bound(self):
        seo=PublicSEOService(self.trade,ROOT/'site')
        models=self.trade.catalog.models()
        approved=[model for model in models if 'en' in seo.index_policy('model',model)['indexLanguages']]
        self.assertEqual(len(approved),52)
        self.assertTrue({'haval-catalog-1','tank-catalog-1'}.issubset({item['id'] for item in approved}))
        descriptions=set()
        for model in approved:
            with self.subTest(model=model['id']):
                status,body=seo.render('/trade/models/'+model['id'])
                document=HTMLDocument(body.decode())
                self.assertEqual(status,200)
                self.assertIn('index, follow',body.decode())
                self.assertIn('China-market',body.decode())
                self.assertIn('Source configuration',body.decode())
                if seo.english_editorial(model).get('buyerNote'):
                    self.assertIn('/buyer/requests',body.decode())
                description=next(item['content'] for item in document.metas if item.get('name')=='description')
                self.assertNotIn(description,descriptions)
                descriptions.add(description)
                self.assertNotIn('FOB $',body.decode())
        changed=self.trade.catalog.get('geely-catalog-3')
        with self.auth.connect() as db:
            db.execute("UPDATE catalog_models SET description='Changed after English review' WHERE id=?",(changed['id'],))
        self.assertNotIn('en',seo.index_policy('model',self.trade.catalog.get(changed['id']))['indexLanguages'])
        self.assertIn('noindex, follow',seo.render('/trade/models/'+changed['id'])[1].decode())

    def test_brand_review_withdraws_when_catalog_brand_changes(self):
        seo=PublicSEOService(self.trade,ROOT/'site')
        brand=self.trade.catalog.brand('byd')
        self.assertEqual(seo.index_policy('brand',brand)['indexLanguages'],['en'])
        source=seo.render('/trade/brands/byd')[1].decode()
        self.assertIn('manufacturer source',source)
        self.assertIn('Listing a brand on AUTOLINK does not imply official affiliation',source)
        self.assertIn('Supplier authorization, where claimed, is verified separately.',source)
        self.assertIn('/trade/models/',source)
        self.assertIn('/images/seo-heroes/byd-seal-07-ev-640.webp',source)
        self.assertNotIn('/images/catalog-update-20261011/byd-seal-07-ev.jpg',source)
        self.assertIn('No approved vehicle listings yet.',source)
        self.assertEqual(seo.index_policy('brand',self.trade.catalog.brand('aion'))['indexLanguages'],[])
        with self.auth.connect() as db:
            db.execute("UPDATE catalog_brands SET name='Changed BYD' WHERE id='byd'")
        self.assertEqual(seo.index_policy('brand',self.trade.catalog.brand('byd'))['indexLanguages'],[])
        self.assertIn('noindex, follow',seo.render('/trade/brands/byd')[1].decode())

    def test_brand_review_withdraws_after_model_change(self):
        seo=PublicSEOService(self.trade,ROOT/'site')
        self.assertEqual(seo.index_policy('brand',self.trade.catalog.brand('geely'))['indexLanguages'],['en'])
        with self.auth.connect() as db:
            db.execute("UPDATE catalog_models SET description='New model copy pending brand review' WHERE id='geely-catalog-3'")
        self.assertEqual(seo.index_policy('brand',self.trade.catalog.brand('geely'))['indexLanguages'],[])

    def test_sitemap_and_market_guide_language_boundaries(self):
        ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9','x':'http://www.w3.org/1999/xhtml'}
        static=ElementTree.fromstring(self.trade.sitemap_xml('static-1.xml'))
        home=[url for url in static.findall('s:url',ns)
            if url.find('s:loc',ns).text in ('https://autolinkglobal.com/','https://autolinkglobal.com/?lang=zh')]
        self.assertEqual({url.find('s:loc',ns).text for url in home},
            {'https://autolinkglobal.com/','https://autolinkglobal.com/?lang=zh'})
        for url in home:
            self.assertEqual({link.get('hreflang') for link in url.findall('x:link',ns)},
                {'en','zh-CN','x-default'})
        guide=[url for url in static.findall('s:url',ns)
            if '/guide/middle-east-importers' in url.find('s:loc',ns).text]
        self.assertEqual(len(guide),1)
        self.assertEqual(guide[0].find('s:loc',ns).text,'https://autolinkglobal.com/guide/middle-east-importers')
        self.assertEqual({link.get('hreflang') for link in guide[0].findall('x:link',ns)},{'en','x-default'})
        about=[url for url in static.findall('s:url',ns)
            if '/about' in url.find('s:loc',ns).text]
        self.assertEqual(len(about),1)
        self.assertEqual(about[0].find('s:loc',ns).text,'https://autolinkglobal.com/about')
        self.assertEqual({link.get('hreflang') for link in about[0].findall('x:link',ns)},{'en','x-default'})
        page=(ROOT/'site/guide/middle-east-importers.html').read_text()
        fallback=(ROOT/'site/guide/middle-east-importers.fallback.html').read_text()
        self.assertIn('content="index, follow"',page)
        self.assertIn('content="noindex, follow"',fallback)
        self.assertNotIn('hreflang="ar"',page)
        self.assertIn('import jurisdiction',page)
        africa=[url for url in static.findall('s:url',ns)
            if '/guide/african-importers' in url.find('s:loc',ns).text]
        self.assertEqual(len(africa),1)
        self.assertEqual(africa[0].find('s:loc',ns).text,'https://autolinkglobal.com/guide/african-importers')
        self.assertEqual({link.get('hreflang') for link in africa[0].findall('x:link',ns)},{'en','x-default'})
        africa_page=(ROOT/'site/guide/african-importers.html').read_text()
        self.assertIn('content="index, follow"',africa_page)
        self.assertIn('Kenya Revenue Authority',africa_page)
        self.assertIn('/buyer/requests',africa_page)
        self.assertIn('noindex, follow',(ROOT/'site/guide/african-importers.fallback.html').read_text())
        arabic=(ROOT/'site/guide/middle-east-importers.ar.html').read_text()
        self.assertIn('<html lang="ar" dir="rtl">',arabic)
        self.assertIn('content="noindex, follow"',arabic)
        self.assertIn('href="https://autolinkglobal.com/guide/middle-east-importers?lang=ar"',arabic)


if __name__=='__main__':unittest.main()
