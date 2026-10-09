"""Review gates, ownership and preserved evidence in isolated databases."""
import unittest
import threading
import json
import urllib.request
import urllib.error
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from app import Handler
from buyer_service import BuyerError, BuyerService
import image_service
import test_trade

class ReviewGateTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp

    def pending_vehicle(self):
        listing = test_trade.TradeFlowTests.approved_vehicle(self)
        owner = self.users['supplier-a']
        self.trade.transition_vehicle(owner, listing, 'offline')
        self.trade.save_vehicle(owner, {'modelId':'zeekr-9x-2026','modelYear':2026,'trim':'New review snapshot',
            'priceMinor':1890000,'moq':2,'stock':12,'originPort':'Shanghai','validUntil':date.today().isoformat()}, listing)
        self.trade.transition_vehicle(owner, listing, 'submit')
        return listing

    def reference(self, amount=2000000):
        return {'referencePriceMinor':amount,'currency':'USD','incoterm':'FOB','sourceName':'Isolated QA quote',
                'sourceUrl':'https://example.com/quote','observedOn':date.today().isoformat(),
                'referenceSpec':'Same model/year/trim/condition/steering/terms in test fixture', 'comparableConfirmed':True}

    def test_agreement_required_and_company_changes_need_new_confirmation(self):
        owner=self.users['supplier-a']
        form={'companyName':'QA company','registrationNo':'QA-REG','address':'QA Shanghai', 'country':'China','contactName':'Sales','contactPhone':'123',
            'premisesAddress':'QA warehouse','inventoryCount':1,'inventoryBasis':'OWNED','inventoryAsOf':date.today().isoformat()}
        self.trade.save_application(owner,form)
        self.trade.add_document(owner,{'kind':'BUSINESS_LICENSE','filename':'license.pdf','contentType':'application/pdf','base64':'JVBERi0xLjQKMSAwIG9iaiA8PCA+PiBlbmRvYmoKJSVFT0Y='})
        test_trade.TradeFlowTests.add_application_evidence(self,owner)
        with self.assertRaises(BuyerError) as e:self.trade.save_application(owner,{**form,'submit':True})
        self.assertEqual(e.exception.status,409);self.assertEqual(self.trade.application(owner)['status'],'DRAFT')
        first=test_trade.TradeFlowTests.sign_company(self,owner)['confirmation']['id']
        self.assertEqual(test_trade.TradeFlowTests.sign_company(self,owner)['confirmation']['id'],first)
        changed={**form,'registrationNo':'QA-NEW'}
        with self.assertRaises(BuyerError):self.trade.save_application(owner,{**changed,'submit':True})
        self.assertEqual(self.trade.application(owner)['registration_no'],'QA-REG')
        self.trade.save_application(owner,changed)
        self.assertIsNone(self.trade.agreement.current(owner)['confirmation'])
        second=test_trade.TradeFlowTests.sign_company(self,owner)['confirmation']['id'];self.assertNotEqual(first,second)
        self.trade.save_application(owner,{**changed,'submit':True})
        self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'APPROVED'})
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT registration_no FROM supplier_agreement_confirmations WHERE id=?',(first,)).fetchone()[0],'QA-REG')
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_agreement_confirmation_revisions').fetchone()[0],1)

    def test_supplier_approval_rechecks_agreement_snapshot(self):
        test_trade.TradeFlowTests.approved_vehicle(self)
        with self.auth.connect() as db:db.execute("UPDATE supplier_applications SET status='PENDING',registration_no='ALTERED' WHERE supplier_id='supplier-a'")
        with self.assertRaises(BuyerError):self.trade.review_supplier(self.users['admin'],'supplier-a',{'decision':'APPROVED'})

    def test_copy_photo_requires_declaration_and_approval_rechecks_photo(self):
        source=test_trade.TradeFlowTests.approved_vehicle(self);owner=self.users['supplier-a']
        copied=self.trade.copy_vehicle(owner,source)['id'];photo=self.trade.images.list(copied)[0]
        self.assertEqual(photo['stock_photo'],0)
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,copied,'submit')
        with self.assertRaises(BuyerError):self.trade.images.attest(self.users['supplier-b'],copied,photo['id'],{'stockPhoto':True})
        with self.assertRaises(BuyerError):self.trade.images.attest(owner,copied,photo['id'],{'stockPhoto':'true'})
        self.trade.images.attest(owner,copied,photo['id'],{'stockPhoto':True})
        self.trade.transition_vehicle(owner,copied,'submit')
        with self.auth.connect() as db:db.execute('DELETE FROM vehicle_images WHERE listing_id=?',(copied,))
        comparison=self.trade.price_reviews.record(self.users['admin'],copied,self.reference())
        with self.assertRaises(BuyerError):self.trade.review_vehicle(self.users['admin'],copied,{'decision':'APPROVED','priceReviewId':comparison['id']})
        self.assertEqual(self.trade.vehicle(copied)['status'],'PENDING_REVIEW')

    def test_missing_file_and_false_declaration_block_submission(self):
        source=test_trade.TradeFlowTests.approved_vehicle(self);owner=self.users['supplier-a'];copied=self.trade.copy_vehicle(owner,source)['id']
        photo=self.trade.images.list(copied)[0]
        with self.assertRaises(BuyerError):self.trade.images.add(owner,copied,{**test_trade.TradeFlowTests.image_body(self),'stockPhoto':False})
        self.trade.images.attest(owner,copied,photo['id'],{'stockPhoto':True})
        with self.auth.connect() as db:stored=db.execute('SELECT stored_name FROM vehicle_images WHERE id=?',(photo['id'],)).fetchone()[0]
        (image_service.ROOT/stored).unlink()
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,copied,'submit')

    def test_comparison_required_and_merchant_price_never_changed(self):
        listing=self.pending_vehicle();admin=self.users['admin']
        with self.assertRaises(BuyerError):self.trade.review_vehicle(admin,listing,{'decision':'APPROVED'})
        r=self.trade.price_reviews.record(admin,listing,self.reference())
        self.assertEqual(r['discount_percent'],5.5);self.assertTrue(r['within_target']);self.assertTrue(r['current'])
        self.trade.review_vehicle(admin,listing,{'decision':'APPROVED','priceReviewId':r['id']})
        self.assertEqual(self.trade.vehicle(listing)['price_minor'],1890000)
        self.trade.transition_vehicle(self.users['supplier-a'],listing,'online')
        public=self.trade.vehicle(listing,public=True)
        self.assertNotIn('reference_price_minor',public);self.assertNotIn('priceReviews',public)

    def test_outside_range_needs_reason_without_forcing_a_price(self):
        listing=self.pending_vehicle();admin=self.users['admin'];r=self.trade.price_reviews.record(admin,listing,self.reference(1800000))
        self.assertEqual(r['discount_percent'],-5);self.assertFalse(r['within_target'])
        with self.assertRaises(BuyerError):self.trade.review_vehicle(admin,listing,{'decision':'APPROVED','priceReviewId':r['id']})
        self.trade.review_vehicle(admin,listing,{'decision':'APPROVED','priceReviewId':r['id'],'reason':'QA exceptional configuration manually checked'})
        self.assertEqual(self.trade.vehicle(listing)['price_minor'],1890000)

    def test_stale_and_other_listing_records_cannot_approve(self):
        listing=self.pending_vehicle();admin=self.users['admin'];r=self.trade.price_reviews.record(admin,listing,self.reference())
        with self.auth.connect() as db:db.execute('UPDATE supplier_vehicles SET price_minor=1900000 WHERE id=?',(listing,))
        self.assertFalse(self.trade.price_reviews.history(admin,listing)[0]['current'])
        with self.assertRaises(BuyerError):self.trade.review_vehicle(admin,listing,{'decision':'APPROVED','priceReviewId':r['id']})
        foreign=test_trade.TradeFlowTests.approved_vehicle(self,'supplier-b')
        with self.auth.connect() as db:db.execute("UPDATE supplier_vehicles SET status='PENDING_REVIEW' WHERE id=?",(foreign,))
        with self.assertRaises(BuyerError):self.trade.review_vehicle(admin,foreign,{'decision':'APPROVED','priceReviewId':r['id']})

    def test_reference_validation_and_admin_isolation(self):
        listing=self.pending_vehicle();admin=self.users['admin']
        before=self.trade.price_reviews.history(admin,listing)
        for fields in ({'referencePriceMinor':True},{'referencePriceMinor':0},{'currency':'CNY'},{'incoterm':'CIF'},
                       {'comparableConfirmed':False},{'sourceUrl':'javascript:alert(1)'},{'sourceUrl':'https://name:password@example.com'},
                       {'observedOn':(date.today()+timedelta(days=1)).isoformat()}):
            with self.subTest(fields=fields),self.assertRaises(BuyerError):self.trade.price_reviews.record(admin,listing,{**self.reference(),**fields})
        for role in ('buyer-a','supplier-a','supplier-b'):
            with self.assertRaises(BuyerError):self.trade.price_reviews.history(self.users[role],listing)
            with self.assertRaises(BuyerError):self.trade.price_reviews.record(self.users[role],listing,self.reference())
            with self.assertRaises(BuyerError):self.trade.review_vehicle(self.users[role],listing,{'decision':'APPROVED'})
        self.assertEqual(self.trade.price_reviews.history(admin,listing),before)

    def test_http_price_rbac_and_photo_idor(self):
        listing=self.pending_vehicle()
        test_trade.TradeFlowTests.approved_vehicle(self,'supplier-b')
        Handler.service=self.auth;Handler.trade=self.trade;Handler.buyer=BuyerService(self.auth);Handler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def request(user,path,body=None):
            token=self.auth.session_for_user(user)['access_token'];data=None if body is None else json.dumps(body).encode()
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=data,headers={'Cookie':'autolink_session='+token,'Content-Type':'application/json','Origin':'https://autolinkglobal.com'})
            try:r=urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:r=e
            return r.status,json.loads(r.read())
        path='/autolink/admin/vehicles/'+listing+'/price-reviews'
        self.assertEqual(request('supplier-a',path)[0],403);self.assertEqual(request('buyer-a',path,self.reference())[0],403)
        status,p=request('admin',path,self.reference());self.assertEqual(status,200);self.assertEqual(p['data']['discount_percent'],5.5)
        self.assertEqual(request('admin',path)[0],200)
        photo=self.trade.images.list(listing)[0]['id']
        self.assertEqual(request('supplier-b','/autolink/supplier/vehicles/'+listing+'/images/'+photo+'/attest',{'stockPhoto':True})[0],404)
