"""Full isolated crawl using only public fields from the current 244-model catalogue."""
import json
from pathlib import Path
import unittest
from xml.etree import ElementTree
from seo_service import LANGUAGES, PublicSEOService, localized_url
from test_seo import HTMLDocument
import test_trade

ROOT=Path(__file__).resolve().parent.parent

class CurrentCatalogSEOTests(unittest.TestCase):
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        public=json.loads((ROOT/'tests/fixtures/production-public-catalog-20261012.json').read_text())
        self.models=public['models'];self.brands=public['brands']
        with self.auth.connect() as db:
            db.execute('UPDATE catalog_models SET active=0')
            db.execute('UPDATE catalog_brands SET active=0')
            for b in self.brands:
                db.execute('''INSERT INTO catalog_brands(id,name,country,logo,overview,active,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,
                    logo=excluded.logo,overview=excluded.overview,active=1,updated_at=excluded.updated_at''',
                    (b['id'],b['name'],b['country'],b['logo'],b['overview'],1,b['created_at'],b['updated_at']))
            for m in self.models:
                db.execute('''INSERT INTO catalog_models(id,brand_id,name,model_year,body_type,energy,image,
                    description,specifications,active,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET brand_id=excluded.brand_id,name=excluded.name,
                    model_year=excluded.model_year,body_type=excluded.body_type,energy=excluded.energy,
                    image=excluded.image,description=excluded.description,specifications=excluded.specifications,
                    active=1,updated_at=excluded.updated_at''',
                    (m['id'],m['brandId'],m['model'],m['year'],m['bodyType'],m['energy'],m['image'],
                     m['description'],json.dumps(m['specifications']),1,1791800000,1791800000))
        self.seo=PublicSEOService(self.trade,ROOT/'site')

    def test_every_current_detail_and_language(self):
        self.assertEqual(len(self.trade.catalog.models()),244)
        self.assertEqual(len(self.trade.catalog.brands()),53)
        indexable=[]
        for kind,records in (('models',self.models),('brands',self.brands)):
            for record in records:
                path='/trade/'+kind+'/'+record['id']
                entity=self.trade.catalog.get(record['id']) if kind=='models' else self.trade.catalog.brand(record['id'])
                policy=self.seo.index_policy('model' if kind=='models' else 'brand',entity)
                for language in LANGUAGES:
                    with self.subTest(kind=kind,id=record['id'],lang=language):
                        status,body=self.seo.render(path+'?lang='+language)
                        source=body.decode();doc=HTMLDocument(source)
                        self.assertEqual(status,200)
                        self.assertEqual(len(doc.h1),1)
                        self.assertIn(record['model'] if kind=='models' else record['name'],doc.h1[0])
                        self.assertEqual(doc.canonical(),localized_url(path,language))
                        self.assertEqual(doc.html['lang'],'zh-CN' if language=='zh' else language)
                        self.assertIn('data-ssr="true"',source)
                        self.assertNotIn('itemprop="price"',source)
                        if language in policy['indexLanguages']:
                            self.assertIn('content="index, follow"',source)
                            self.assertTrue(doc.alternates())
                            indexable.append(localized_url(path,language))
                        else:
                            self.assertIn('content="noindex, follow"',source)
                            self.assertEqual(doc.alternates(),{})
        self.assertEqual(len(indexable),len(set(indexable)))
        self.assertEqual(len(indexable),205)
        self.assertEqual(sum('?' not in url for url in indexable),25)
        self.assertEqual(sum('?lang=zh' in url for url in indexable),180)
        self.assertFalse(any('/trade/brands/' in url for url in indexable))

    def test_all_current_images_have_verified_mobile_derivatives(self):
        manifest=json.loads((ROOT/'site/images/seo-heroes/manifest.json').read_text())
        self.assertEqual(len(manifest),244)
        for model in self.models:
            with self.subTest(model=model['id']):
                source=ROOT/'site'/model['image'].lstrip('/')
                self.assertTrue(source.is_file())
                self.assertEqual(manifest[model['id']]['source'],model['image'])
                self.assertTrue((ROOT/'site'/manifest[model['id']]['mobile'].lstrip('/')).is_file())
                self.assertEqual(self.seo.mobile_hero(model,model['image']),manifest[model['id']]['mobile'])

    def test_sitemap_exactly_matches_index_policy(self):
        expected={localized_url('/trade/models/'+m['id'],lang)
                  for m in self.trade.catalog.models()
                  for lang in self.seo.index_policy('model',m)['indexLanguages']}
        ns={'s':'http://www.sitemaps.org/schemas/sitemap/0.9'}
        found=set()
        for page in range(1,2):
            root=ElementTree.fromstring(self.trade.sitemap_xml(f'models-{page}.xml'))
            found.update(node.text for node in root.findall('.//s:loc',ns))
        self.assertEqual(found,expected)
        self.assertEqual(sum('?' not in url for url in found),25)

    def test_english_review_withdraws_on_catalog_change(self):
        model=self.trade.catalog.get('geely-monjaro-2026')
        self.assertIn('en',self.seo.index_policy('model',model)['indexLanguages'])
        with self.auth.connect() as db:
            db.execute("UPDATE catalog_models SET name='Changed model' WHERE id=?",(model['id'],))
        self.assertNotIn('en',self.seo.index_policy('model',self.trade.catalog.get(model['id']))['indexLanguages'])

if __name__=='__main__':unittest.main()
