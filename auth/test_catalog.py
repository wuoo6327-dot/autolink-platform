"""Catalogue administration, additive migration and public visibility boundaries."""
import json
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from app import Handler
from buyer_service import BuyerError, BuyerService, CATALOG
from catalog_service import CatalogService
import test_trade

class CatalogTests(unittest.TestCase):
    setUp=test_trade.TradeFlowTests.setUp
    approved_vehicle=test_trade.TradeFlowTests.approved_vehicle

    def brand_body(self, **fields):
        return {'id':'qa-brand','name':'QA Brand','country':'China','logo':'/favicon.svg','overview':'QA reference only','active':True,**fields}

    def model_body(self, **fields):
        return {'id':'qa-model-2026','brandId':'qa-brand','model':'QA Model','year':2026,'bodyType':'SUV',
                'energy':'PHEV','image':'/favicon.svg','active':True,'specifications':{'power':'Supplier must confirm'},**fields}

    def test_additive_restart_preserves_admin_edits_and_users(self):
        catalog=self.trade.catalog
        self.assertEqual(len(catalog.models()),len(CATALOG))
        catalog.save_brand(self.users['admin'],self.brand_body())
        catalog.save_model(self.users['admin'],self.model_body())
        existing=catalog.get('zeekr-9x-2026')
        catalog.save_model(self.users['admin'],{**existing,'model':'Maintained model','active':False},existing['id'])
        restarted=CatalogService(self.auth)
        self.assertEqual(restarted.get(existing['id'])['model'],'Maintained model')
        self.assertFalse(restarted.enabled(existing['id']))
        self.assertTrue(restarted.enabled('qa-model-2026'))
        unknown=next(item for item in restarted.models() if item['year'] is None)
        saved=restarted.save_model(self.users['admin'],{**unknown,'description':'Updated without inventing a model year'},unknown['id'])
        self.assertIsNone(saved['year'])
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],5)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.execute("SELECT count(*) FROM trade_audit WHERE action='MODEL_UPDATED'").fetchone()[0],2)

    def test_brand_logo_reaches_all_model_responses_and_preserves_admin_edits(self):
        catalog=self.trade.catalog
        catalog.save_brand(self.users['admin'],self.brand_body(logo='/images/brands/geely.svg'))
        catalog.save_model(self.users['admin'],self.model_body())
        self.assertEqual(catalog.brand('qa-brand')['logo'],'/images/brands/geely.svg')
        self.assertEqual(catalog.brand('qa-brand')['models'][0]['brandLogo'],'/images/brands/geely.svg')
        self.assertEqual(catalog.get('qa-model-2026')['brandLogo'],'/images/brands/geely.svg')
        self.assertEqual(catalog.models(brand='qa-brand')[0]['brandLogo'],'/images/brands/geely.svg')
        catalog.save_brand(self.users['admin'],self.brand_body(logo='/images/custom-admin-logo.svg'),'qa-brand')
        restarted=CatalogService(self.auth)
        self.assertEqual(restarted.get('qa-model-2026')['brandLogo'],'/images/custom-admin-logo.svg')
        catalog.save_brand(self.users['admin'],self.brand_body(logo=''),'qa-brand')
        self.assertEqual(catalog.get('qa-model-2026')['brandLogo'],'')

    def test_deactivation_hides_public_stock_preserves_owned_history(self):
        listing=self.approved_vehicle();buyer=self.users['buyer-a'];catalog=self.trade.catalog
        saved=BuyerService(self.auth)
        saved.add_vehicle(buyer,'favorites','zeekr-9x-2026')
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Saudi Arabia'})
        model=catalog.get('zeekr-9x-2026');brand=catalog.brand(model['brandId'],False)
        catalog.save_brand(self.users['admin'],{**brand,'active':False},brand['id'])
        self.assertEqual(self.trade.vehicle_rows(public=True),[])
        with self.assertRaises(BuyerError):self.trade.vehicle(listing,public=True)
        with self.assertRaises(BuyerError):saved.model(model['id'])
        self.assertEqual(saved.vehicle_list(buyer,'favorites')[0]['id'],model['id'])
        self.assertEqual(saved.inquiry_rows(buyer,inquiry['id'])[0]['id'],inquiry['id'])
        self.assertEqual(self.trade.vehicle(listing,supplier_id='supplier-a')['id'],listing)
        catalog.save_brand(self.users['admin'],{**brand,'active':True},brand['id'])
        self.assertEqual(self.trade.vehicle(listing,public=True)['id'],listing)

    def test_search_uses_maintained_names(self):
        listing=self.approved_vehicle();catalog=self.trade.catalog;model=catalog.get('zeekr-9x-2026')
        catalog.save_model(self.users['admin'],{**model,'model':'Revised Export Model'},model['id'])
        rows=self.trade.vehicle_rows(public=True,filters={'keyword':'Revised Export Model'})
        self.assertEqual([r['id'] for r in rows],[listing])
        self.assertEqual(rows[0]['model'],'Revised Export Model')

    def test_validation_and_service_role_checks(self):
        catalog=self.trade.catalog
        with self.assertRaises(BuyerError) as error:catalog.save_brand({**self.users['buyer-a'],'role':'PLATFORM_ADMIN'},self.brand_body())
        self.assertEqual(error.exception.status,403)
        for url in ['javascript:alert(1)','//external.example/a.png','/\\external.example/a.png','https://[broken','/../private.jpg']:
            with self.subTest(url=url),self.assertRaises(BuyerError):catalog.save_brand(self.users['admin'],self.brand_body(logo=url))
        catalog.save_brand(self.users['admin'],self.brand_body())
        for fields in [{'year':True},{'active':'yes'},{'specifications':{'password':'x'}}]:
            with self.subTest(fields=fields),self.assertRaises(BuyerError):catalog.save_model(self.users['admin'],self.model_body(**fields))
        catalog.save_model(self.users['admin'],self.model_body())
        with self.assertRaises(BuyerError) as error:catalog.save_model(self.users['admin'],self.model_body(id='another-slug'))
        self.assertEqual(error.exception.status,409)

    def test_http_admin_csrf_and_public_model_activation(self):
        Handler.service=self.auth;Handler.trade=self.trade;Handler.buyer=BuyerService(self.auth);Handler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        def call(path,account=None,method='GET',body=None,origin=None):
            headers={'Content-Type':'application/json'}
            if account:headers['Cookie']='autolink_session='+self.auth.session_for_user(account)['access_token']
            if origin:headers['Origin']=origin
            request=urllib.request.Request(base+path,headers=headers,method=method,data=json.dumps(body).encode() if body is not None else None)
            try:
                with urllib.request.urlopen(request) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        self.assertEqual(call('/autolink/admin/models','buyer-a')[0],403)
        self.assertEqual(call('/autolink/admin/seo/status','buyer-a')[0],403)
        self.assertEqual(call('/autolink/admin/seo/status')[0],401)
        seo_status=call('/autolink/admin/seo/status','admin')
        self.assertEqual(seo_status[0],200)
        self.assertEqual(seo_status[1]['data']['languages']['en'],{'models':50,'brands':10})
        self.assertEqual(seo_status[1]['data']['sitemap']['eligibleDetailUrls'],237)
        self.assertIsNone(seo_status[1]['data']['searchConsole']['indexedUrls'])
        self.assertEqual(call('/autolink/admin/brands','admin','POST',self.brand_body(),'https://attacker.example')[0],403)
        self.assertEqual(call('/autolink/admin/brands','admin','POST',self.brand_body())[0],200)
        self.assertEqual(call('/autolink/admin/models','admin','POST',self.model_body())[0],200)
        self.assertEqual(call('/autolink/public/models/qa-model-2026')[0],200)
        self.assertEqual(call('/autolink/admin/models/qa-model-2026','admin','PUT',self.model_body(active=False))[0],200)
        self.assertEqual(call('/autolink/public/models/qa-model-2026')[0],404)
        self.assertTrue(any(r['id']=='qa-model-2026' for r in call('/autolink/admin/models','admin')[1]['data']))

if __name__=='__main__':unittest.main()
