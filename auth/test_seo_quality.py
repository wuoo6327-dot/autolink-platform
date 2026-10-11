"""Index quality gates; synthetic reference edits only in a temporary directory."""
import json
from pathlib import Path
import tempfile
import unittest
from seo_service import PublicSEOService, LANGUAGES
from test_seo import HTMLDocument
import test_trade


class SEOQualityTests(unittest.TestCase):
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        self.site = Path(__file__).resolve().parent.parent/'site'
        self.seo = PublicSEOService(self.trade,self.site)

    def test_complete_and_thin_partition_keeps_all_244_real_model_records(self):
        models=self.trade.catalog.models()
        policies={m['id']:self.seo.index_policy('model',m) for m in models}
        self.assertEqual(len(models),244)
        self.assertEqual(sum(p['contentComplete'] for p in policies.values()),177)
        self.assertEqual(sum(not p['contentComplete'] for p in policies.values()),67)
        self.assertEqual(sum('zh' in p['indexLanguages'] for p in policies.values()),177)
        self.assertEqual(sum('en' in p['indexLanguages'] for p in policies.values()),22)
        self.assertTrue(all(not p['indexLanguages'] for p in policies.values() if not p['contentComplete']))

    def test_all_67_thin_models_remain_accessible_in_every_language_and_noindex(self):
        thin=[m for m in self.trade.catalog.models() if not self.seo.index_policy('model',m)['contentComplete']]
        self.assertEqual(len(thin),67)
        for model in thin:
            for language in LANGUAGES:
                with self.subTest(model=model['id'],language=language):
                    status,body=self.seo.render('/trade/models/'+model['id']+'?lang='+language)
                    doc=HTMLDocument(body.decode())
                    self.assertEqual(status,200)
                    self.assertIn('noindex, follow',[m.get('content') for m in doc.metas])
                    self.assertEqual(doc.alternates(),{})
                    self.assertIn(model['model'],doc.h1[0])

    def test_unreviewed_brand_editorial_pages_are_not_blindly_indexed(self):
        brands=self.trade.catalog.brands()
        self.assertEqual(len(brands),53)
        for brand in brands:
            policy=self.seo.index_policy('brand',self.trade.catalog.brand(brand['id']))
            self.assertEqual(policy['indexLanguages'],[])
        for language in LANGUAGES:
            status,body=self.seo.render('/trade/brands/byd?lang='+language)
            self.assertEqual(status,200)
            self.assertIn('noindex, follow',body.decode())
            self.assertEqual(HTMLDocument(body.decode()).alternates(),{})

    def temporary_reference(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        site=Path(directory.name)
        (site/'model-reference').mkdir();(site/'locales').mkdir()
        source=json.loads((self.site/'model-reference/aeolus-catalog-1.json').read_text())
        model=self.trade.catalog.get('byd-shark')
        source['modelId']=model['id']
        file=site/'model-reference'/(model['id']+'.json')
        file.write_text(json.dumps(source))
        return PublicSEOService(self.trade,site),model,source,file

    def test_real_reference_recovery_requires_structural_and_provenance_validation(self):
        seo,model,reference,file=self.temporary_reference()
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],['zh'])
        reference['variants'][0]['values']={};file.write_text(json.dumps(reference))
        self.assertFalse(seo.index_policy('model',model)['contentComplete'])
        reference['status']='draft';file.write_text(json.dumps(reference))
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],[])

    def test_foreign_review_is_bound_to_content_and_still_rejects_chinese_residual(self):
        seo,model,reference,file=self.temporary_reference()
        review=seo.site_root/'locales/seo-index-reviews.json'
        fingerprint=seo.index_policy('model',model)['sourceFingerprint']
        review.write_text(json.dumps({'model':{model['id']:{'en':{'sourceFingerprint':fingerprint,'reviewedBy':'isolated-test','evidence':'synthetic-local-review'}}}}))
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],['zh'])
        # Neutral non-language symbols in a synthetic reference prove review can
        # enable a locale; these are not written into a real catalog or fixture.
        for v in reference['variants']:
            v['name']='Synthetic';v['values']={k:'123' for k in v['values']}
        for g in reference['groups']:
            g['name']='Synthetic';
            for r in g['rows']:r['label']='Synthetic'
        file.write_text(json.dumps(reference))
        fingerprint=seo.index_policy('model',model)['sourceFingerprint']
        review.write_text(json.dumps({'model':{model['id']:{'en':{'sourceFingerprint':fingerprint,'reviewedBy':'isolated-test','evidence':'synthetic-local-review'}}}}))
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],['en','zh'])
        reference['variants'][0]['values'][next(iter(reference['variants'][0]['values']))]='456'
        file.write_text(json.dumps(reference))
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],['zh'])

    def test_invalid_review_file_and_incomplete_reference_fail_closed(self):
        seo,model,reference,file=self.temporary_reference()
        (seo.site_root/'locales/seo-index-reviews.json').write_text('[null]')
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],['zh'])
        file.write_text('{invalid-json')
        self.assertEqual(seo.index_policy('model',model)['indexLanguages'],[])

    def test_exact_terminology_preserves_numbers_units_and_unknown_trim_names(self):
        expected={'5门7座SUV':'5-door 7-seat SUV','7挡湿式双离合':'7-speed wet dual-clutch','国VI':'China VI','挡':'gear'}
        for source,target in expected.items():self.assertEqual(self.seo.translated_value(source,'en'),target)
        source='Ultra版55kWh五座'
        self.assertEqual(self.seo.translated_value(source,'en'),source)
        self.assertEqual(self.seo.translated_value('55kWh','en'),'55kWh')
        self.assertEqual(self.seo.translated_value(0,'en'),'0')

    def test_noindex_is_readable_by_crawlers_not_blocked_by_robots(self):
        robots=(self.site/'robots.txt').read_text()
        self.assertNotIn('Disallow: /trade/models',robots)
        self.assertNotIn('Disallow: /trade/brands',robots)
        status,body=self.seo.render('/trade/models/byd-shark?lang=en')
        self.assertEqual(status,200);self.assertIn('noindex, follow',body.decode())


if __name__=='__main__':unittest.main()
