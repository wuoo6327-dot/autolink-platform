"""Read-only publication guidance follows existing review and visibility gates."""
import base64
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import test_trade
from app import Handler
from buyer_service import BuyerError, BuyerService
from email_auth import EmailAuthService


class PublicationReadinessTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp
    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle

    def form(self):
        return {'companyName':'Synthetic export company','registrationNo':'SYNTHETIC-001',
            'address':'Synthetic legal address','country':'China','contactName':'Synthetic owner',
            'contactPhone':'+8613800000000','premisesAddress':'Synthetic warehouse',
            'inventoryCount':0,'inventoryBasis':'AUTHORIZED','inventoryAsOf':date.today().isoformat()}

    def evidence(self, owner):
        self.trade.add_document(owner,{'kind':'BUSINESS_LICENSE','filename':'synthetic-license.pdf',
            'contentType':'application/pdf','base64':base64.b64encode(b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF').decode()})
        test_trade.TradeFlowTests.add_application_evidence(self,owner)

    def supplier_state(self, ident='supplier-a'):
        with self.auth.connect() as db:
            return self.trade.supplier_publication(db,ident)

    def snapshot(self):
        with self.auth.connect() as db:
            return '\n'.join(db.iterdump())

    def test_missing_application_is_actionable_without_creating_records(self):
        before=self.snapshot()
        result=self.trade.application(self.users['supplier-a'])
        publication=result['publication']
        self.assertFalse(publication['visible'])
        self.assertEqual(publication['reasons'],['APPLICATION_MISSING'])
        self.assertEqual(publication['nextAction'],'save_application')
        self.assertIn('registrationNo',publication['requiredFields'])
        self.assertNotIn('companyName',publication['requiredFields'])
        self.assertEqual(publication['requiredDocumentKinds'],['BUSINESS_LICENSE','PREMISES_PHOTO','INVENTORY_PHOTO'])
        self.assertFalse(publication['agreementConfirmed'])
        self.assertFalse(publication['requirementsComplete'])
        self.assertEqual(self.snapshot(),before)
        serialized=json.dumps(result)
        self.assertNotIn('/data/',serialized)
        self.assertNotIn('supplier-b',serialized)

    def test_guidance_tracks_documents_agreement_and_explicit_automatic_activation(self):
        owner=self.users['supplier-a']
        self.trade.save_application(owner,self.form())
        publication=self.supplier_state()
        self.assertEqual(publication['requiredFields'],[],'Zero inventory is valid application metadata')
        self.assertEqual(publication['nextAction'],'upload_documents')
        self.evidence(owner)
        self.assertEqual(self.supplier_state()['nextAction'],'confirm_agreement')
        test_trade.TradeFlowTests.sign_company(self,owner)
        ready=self.supplier_state()
        self.assertTrue(ready['requirementsComplete'])
        self.assertFalse(ready['visible'])
        self.assertEqual(ready['nextAction'],'submit_application')
        self.trade.save_application(owner,{**self.form(),'submit':True})
        approved=self.supplier_state()
        self.assertTrue(approved['visible'])
        self.assertEqual(approved['reasons'],[])
        self.assertEqual(approved['nextAction'],'create_vehicle')
        self.assertEqual(len(self.trade.supplier_list(public=True)),1)

    def test_company_identity_change_invalidates_only_agreement_guidance(self):
        owner=self.users['supplier-a']
        self.trade.save_application(owner,self.form());self.evidence(owner)
        test_trade.TradeFlowTests.sign_company(self,owner)
        self.trade.save_application(owner,{**self.form(),'registrationNo':'SYNTHETIC-CHANGED'})
        state=self.supplier_state()
        self.assertFalse(state['agreementConfirmed'])
        self.assertFalse(state['requirementsComplete'])
        self.assertEqual(state['nextAction'],'confirm_agreement')
        self.assertEqual(state['reasons'],['APPLICATION_DRAFT'])

    def test_supplier_reasons_and_public_counts_match_existing_sql_filters(self):
        self.approved_vehicle()
        cases=(('status','SUSPENDED','ACCOUNT_INACTIVE'),('deleted_at',123,'ACCOUNT_DELETED'),
            ('email_verified_at',None,'EMAIL_UNVERIFIED'),('is_test_workspace',1,'TEST_WORKSPACE'),
            ('role','PLATFORM_ADMIN','ACCOUNT_ROLE_INELIGIBLE'))
        for column,value,reason in cases:
            with self.subTest(reason=reason):
                with self.auth.connect() as db:
                    original=db.execute('SELECT '+column+' FROM users WHERE id=?',('supplier-a',)).fetchone()[0]
                    db.execute('UPDATE users SET '+column+'=? WHERE id=?',(value,'supplier-a'))
                state=self.supplier_state()
                self.assertFalse(state['visible']);self.assertIn(reason,state['reasons'])
                self.assertIsNone(self.trade.public_supplier('supplier-a'))
                overview=self.trade.admin_overview()
                self.assertEqual((overview['suppliers'],overview['onlineVehicles']),(1,1))
                self.assertEqual((overview['publicSuppliers'],overview['publicVehicles']),(0,0))
                with self.auth.connect() as db:db.execute('UPDATE users SET '+column+'=? WHERE id=?',(original,'supplier-a'))
        with self.auth.connect() as db:db.execute('UPDATE supplier_profiles SET published=0 WHERE user_id=?',('supplier-a',))
        self.assertIn('PROFILE_UNPUBLISHED',self.supplier_state()['reasons'])
        self.assertEqual(self.supplier_state()['nextAction'],'contact_support')

    def test_application_status_reasons_do_not_change_review_state(self):
        self.approved_vehicle()
        for status in ('DRAFT','PENDING','REJECTED','REQUIRES_CHANGES','SUSPENDED'):
            with self.subTest(status=status):
                with self.auth.connect() as db:db.execute('UPDATE supplier_applications SET status=? WHERE supplier_id=?',(status,'supplier-a'))
                before=self.snapshot();state=self.supplier_state()
                self.assertFalse(state['visible']);self.assertIn('APPLICATION_'+status,state['reasons'])
                self.assertEqual(self.snapshot(),before)
                self.assertIsNone(self.trade.public_supplier('supplier-a'))

    def test_vehicle_lifecycle_readiness_matches_actual_public_visibility(self):
        listing=self.approved_vehicle()
        cases=(('DRAFT','VEHICLE_DRAFT','edit_vehicle'),
            ('PENDING_REVIEW','VEHICLE_PENDING_REVIEW','await_review'),
            ('APPROVED','VEHICLE_APPROVED_NOT_ONLINE','put_online'),
            ('REJECTED','VEHICLE_REJECTED','edit_vehicle'),('OFFLINE','VEHICLE_OFFLINE','put_online'),
            ('SOLD_OUT','VEHICLE_SOLD_OUT','put_online'),('ARCHIVED','VEHICLE_ARCHIVED','restore_vehicle'))
        for status,reason,action in cases:
            with self.subTest(status=status):
                with self.auth.connect() as db:db.execute('UPDATE supplier_vehicles SET status=?,archived_at=? WHERE id=?',(status,123 if status=='ARCHIVED' else None,listing))
                result=self.trade.vehicle(listing,supplier_id='supplier-a',include_archived=True)
                self.assertEqual(result['publication'],{'visible':False,'reasons':[reason],'nextAction':action})
                with self.assertRaises(BuyerError):self.trade.vehicle(listing,public=True)
        with self.auth.connect() as db:db.execute("UPDATE supplier_vehicles SET status='ONLINE',archived_at=NULL WHERE id=?",(listing,))
        self.assertEqual(self.trade.vehicle(listing)['publication'],{'visible':True,'reasons':[],'nextAction':'view_public_listing'})

    def test_catalogue_deactivation_is_explained_without_changing_listing(self):
        listing=self.approved_vehicle()
        with self.auth.connect() as db:
            brand=db.execute('SELECT brand_id FROM catalog_models WHERE id=?',('zeekr-9x-2026',)).fetchone()[0]
            db.execute('UPDATE catalog_models SET active=0 WHERE id=?',('zeekr-9x-2026',))
        self.assertIn('CATALOG_MODEL_INACTIVE',self.trade.vehicle(listing)['publication']['reasons'])
        self.assertEqual(self.trade.vehicle(listing)['status'],'ONLINE')
        self.assertEqual(self.trade.admin_overview()['publicVehicles'],0)
        with self.auth.connect() as db:
            db.execute('UPDATE catalog_models SET active=1 WHERE id=?',('zeekr-9x-2026',))
            db.execute('UPDATE catalog_brands SET active=0 WHERE id=?',(brand,))
        self.assertIn('CATALOG_BRAND_INACTIVE',self.trade.vehicle(listing)['publication']['reasons'])

    def test_legacy_approval_reports_missing_evidence_without_new_publication_gate(self):
        self.approved_vehicle()
        with self.auth.connect() as db:
            db.execute('DELETE FROM supplier_documents WHERE supplier_id=?',('supplier-a',))
            db.execute('DELETE FROM supplier_agreement_confirmations WHERE supplier_id=?',('supplier-a',))
            db.execute("UPDATE supplier_applications SET evidence_version=1,premises_address='',inventory_count=NULL WHERE supplier_id=?",('supplier-a',))
        before=self.snapshot();state=self.supplier_state()
        self.assertTrue(state['visible'],'Existing approved/public records retain the original SQL eligibility')
        self.assertFalse(state['requirementsComplete'])
        self.assertFalse(state['agreementConfirmed'])
        self.assertEqual(state['nextAction'],'contact_support')
        self.assertIn('premisesAddress',state['requiredFields'])
        self.assertEqual(len(state['requiredDocumentKinds']),3)
        self.assertEqual(self.trade.application(self.users['supplier-a'])['status'],'APPROVED')
        self.assertEqual(self.snapshot(),before)

    def test_diagnostics_are_private_paginated_and_supplier_scoped(self):
        listing=self.approved_vehicle()
        suppliers=self.trade.supplier_list(public=False,page=1)
        vehicles=self.trade.vehicle_rows(supplier_id='supplier-a',page=1)
        self.assertTrue(suppliers['items'][0]['publication']['visible'])
        self.assertTrue(vehicles['items'][0]['publication']['visible'])
        self.assertEqual(vehicles['total'],1)
        self.assertEqual(self.trade.vehicle_rows(supplier_id='supplier-b',page=1)['items'],[])
        self.assertNotIn('publication',self.trade.public_supplier('supplier-a'))
        self.assertNotIn('publication',self.trade.vehicle(listing,public=True))
        self.assertNotIn('publication',self.trade.vehicle_rows(public=True)[0])
        with self.assertRaises(BuyerError) as error:self.trade.vehicle(listing,supplier_id='supplier-b')
        self.assertEqual(error.exception.status,404)

    def test_http_owner_admin_and_anonymous_boundaries_remain_enforced(self):
        self.approved_vehicle()
        Handler.service=self.auth;Handler.trade=self.trade;Handler.buyer=BuyerService(self.auth)
        Handler.platform=self.trade.platform;Handler.email_auth=EmailAuthService(self.auth,sender=lambda *_:None)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        def call(path,account=None,workspace=None):
            headers={}
            if account:headers['Cookie']='autolink_session='+self.auth.session_for_user(account)['access_token']
            if workspace:headers['X-Autolink-Supplier']=workspace
            request=urllib.request.Request(base+path,headers=headers)
            try:
                with urllib.request.urlopen(request) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        self.assertEqual(call('/autolink/supplier/application')[0],401)
        self.assertEqual(call('/autolink/admin/suppliers','buyer-a')[0],403)
        self.assertEqual(call('/autolink/supplier/application','supplier-b','supplier-a')[0],404)
        own=call('/autolink/supplier/application','supplier-b')
        self.assertEqual(own[1]['data']['publication']['reasons'],['APPLICATION_MISSING'])
        self.assertEqual(own[1]['data']['supplier_id'],'supplier-b')
        reviewed=call('/autolink/admin/suppliers/supplier-a','admin')
        self.assertTrue(reviewed[1]['data']['publication']['visible'])
        public=call('/autolink/public/suppliers')
        self.assertEqual(public[0],200);self.assertNotIn('publication',public[1]['data'][0])


if __name__=='__main__':unittest.main()
