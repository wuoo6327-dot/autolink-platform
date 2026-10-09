"""Round-one regressions: synthetic legal fixture, temporary SQLite, no real mail."""
import base64
import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

import test_trade
from app import Handler
from business_mail import BusinessMailer
from buyer_service import BuyerError, BuyerService
from email_auth import EmailAuthService
from supplier_agreement_service import SupplierAgreementService
from trade_service import TradeService


class BusinessReadonlyActivationTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp
    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle

    def snapshot(self):
        with self.auth.connect() as db:
            return '\n'.join(db.iterdump())

    def form(self):
        return {'companyName':'Synthetic activation QA company', 'registrationNo':'SYNTHETIC-001',
            'address':'Synthetic registered QA address', 'country':'China',
            'contactName':'Synthetic QA owner', 'contactPhone':'000000',
            'premisesAddress':'Synthetic QA warehouse', 'inventoryCount':0,
            'inventoryBasis':'AUTHORIZED', 'inventoryAsOf':date.today().isoformat()}

    def prepare(self, key='supplier-a', confirm=True):
        owner=self.users[key]
        self.trade.save_application(owner,self.form())
        self.trade.add_document(owner,{'kind':'BUSINESS_LICENSE','filename':'synthetic-license.pdf',
            'contentType':'application/pdf',
            'base64':base64.b64encode(b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF').decode()})
        test_trade.TradeFlowTests.add_application_evidence(self,owner)
        if confirm:test_trade.TradeFlowTests.sign_company(self,owner)
        return owner

    def quote(self, expire=False):
        listing=self.approved_vehicle()
        buyer,owner=self.users['buyer-a'],self.users['supplier-a']
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        quote=self.trade.create_quote(owner,inquiry['id'],{
            'unitPriceMinor':1850000,'validUntil':str(date.today()),'send':True})
        if expire:
            with self.auth.connect() as db:db.execute('UPDATE trade_quotes SET valid_until=? WHERE id=?',
                (str(date.today()-timedelta(days=1)),quote['id']))
        return buyer,owner,listing,inquiry,quote

    def server(self):
        class QuietHandler(Handler):
            def log_message(self, *args):pass
        QuietHandler.service=self.auth;QuietHandler.trade=self.trade
        QuietHandler.buyer=BuyerService(self.auth);QuietHandler.platform=self.trade.platform
        QuietHandler.email_auth=EmailAuthService(self.auth,sender=lambda *_:None)
        server=ThreadingHTTPServer(('127.0.0.1',0),QuietHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:'+str(server.server_port)

    def request(self, base, path, token, method='GET', body=None, origin='https://autolinkglobal.com'):
        headers={'Cookie':'autolink_session='+token,'Content-Type':'application/json','Origin':origin}
        req=urllib.request.Request(base+path,method=method,headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        try:response=urllib.request.urlopen(req)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,json.load(response)

    def test_packaged_legal_draft_blocks_signing_and_activation_without_rewriting_source(self):
        owner=self.prepare(confirm=False)
        source=Path(__file__).with_name('supplier-agreement.json')
        original=source.read_bytes()
        # The actual packaged draft is read only; its version is preserved in the
        # temporary DB alongside the separately versioned synthetic fixture.
        self.trade.agreement=SupplierAgreementService(self.auth)
        current=self.trade.agreement.current(owner)
        self.assertEqual(current['documentStatus'],'REVIEW_DRAFT')
        self.assertFalse(current['acceptanceEnabled'])
        self.assertIn('AGREEMENT_NOT_FINAL',current['blockingReasons'])
        self.assertIn('AGREEMENT_LEGAL_DETAILS_MISSING',current['blockingReasons'])
        before=self.snapshot()
        for call in (lambda:test_trade.TradeFlowTests.sign_company(self,owner),
            lambda:self.trade.save_application(owner,{**self.form(),'submit':True})):
            with self.assertRaises(BuyerError) as error:call()
            self.assertEqual(error.exception.status,409)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(source.read_bytes(),original)

    def test_final_release_requires_complete_resolved_metadata_and_effective_date(self):
        owner=self.prepare(confirm=False)
        final=copy.deepcopy(self.trade.agreement.document)
        cases=[('status','REVIEW_DRAFT'),('acceptanceEnabled',False),
            ('pendingFields',['operatorLegalName']),('body','Operator 【待补】'),('body',''),
            ('legalDetails',{}),('supportEmail','broken-address'),('supportEmail',123),
            ('operatorLegalName','待确认'),('effectiveDate','20200101'),
            ('effectiveDate','2020-13-01'),('effectiveDate',str(date.today()+timedelta(days=1)))]
        for field,value in cases:
            with self.subTest(field=field,value=value):
                document=copy.deepcopy(final)
                target=document['legalDetails'] if field in SupplierAgreementService.LEGAL_FIELDS else document
                target[field]=value
                self.trade.agreement.document=document
                before=self.snapshot()
                self.assertFalse(self.trade.agreement.current(owner)['acceptanceEnabled'])
                with self.assertRaises(BuyerError) as error:test_trade.TradeFlowTests.sign_company(self,owner)
                self.assertEqual(error.exception.status,409)
                self.assertEqual(self.snapshot(),before)
        self.trade.agreement.document=final
        self.assertTrue(self.trade.agreement.current(owner)['acceptanceEnabled'])

    def test_only_explicit_submission_activates_buyer_company_and_vehicle_needs_own_review(self):
        owner=self.prepare('buyer-a')
        before=self.snapshot()
        self.assertEqual(self.trade.application(owner)['status'],'DRAFT')
        self.assertIsNone(self.trade.public_supplier(owner['id']))
        self.assertEqual(self.snapshot(),before)
        active=self.trade.save_application(owner,{**self.form(),'submit':True})
        self.assertEqual(active['status'],'APPROVED')
        self.assertTrue(active['publication']['visible'])
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT role FROM users WHERE id=?',(owner['id'],)).fetchone()[0],'BUYER')
            self.assertIsNone(db.execute('SELECT reviewed_by FROM supplier_applications WHERE supplier_id=?',(owner['id'],)).fetchone()[0])
        item=self.trade.save_vehicle(owner,{'modelId':'zeekr-9x-2026','modelYear':2026,
            'priceMinor':1000000,'stock':1,'moq':1,'originPort':'Synthetic QA port','validUntil':str(date.today())})
        self.assertEqual(item['status'],'DRAFT')
        self.assertEqual(self.trade.vehicle_rows(public=True),[])
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,item['id'],'online')
        self.trade.images.add(owner,item['id'],test_trade.TradeFlowTests.image_body(self))
        self.trade.transition_vehicle(owner,item['id'],'submit')
        self.assertEqual(self.trade.vehicle(item['id'])['status'],'PENDING_REVIEW')
        self.assertEqual(self.trade.vehicle_rows(public=True),[])
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,item['id'],'online')

    def test_legacy_pending_requires_explicit_resubmission_and_keeps_confirmation_history(self):
        owner=self.prepare()
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET status='PENDING',submitted_at=123 WHERE supplier_id=?",(owner['id'],))
            history=[tuple(row) for row in db.execute('SELECT * FROM supplier_agreement_confirmations')]
            audit=[tuple(row) for row in db.execute('SELECT * FROM trade_audit')]
        before=self.snapshot()
        self.assertEqual(self.trade.application(owner)['status'],'PENDING')
        self.assertEqual(self.trade.application(owner)['publication']['nextAction'],'submit_application')
        self.assertIsNone(self.trade.public_supplier(owner['id']))
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.trade.save_application(owner,{**self.form(),'submit':True})['status'],'APPROVED')
        with self.auth.connect() as db:
            self.assertEqual([tuple(row) for row in db.execute('SELECT * FROM supplier_agreement_confirmations')],history)
            after={tuple(row) for row in db.execute('SELECT * FROM trade_audit')}
            self.assertTrue(set(audit)<=after)

    def test_legacy_approved_is_not_migrated_and_suspended_cannot_self_enable(self):
        listing=self.approved_vehicle()
        owner=self.users['supplier-a']
        self.trade.agreement=SupplierAgreementService(self.auth)
        before=self.snapshot()
        active=self.trade.application(owner)
        self.assertEqual(active['status'],'APPROVED')
        self.assertFalse(active['agreementReadiness']['acceptanceEnabled'])
        self.assertIsNotNone(self.trade.public_supplier(owner['id']))
        self.assertEqual(self.trade.vehicle(listing,public=True)['status'],'ONLINE')
        self.assertEqual(self.snapshot(),before)
        # A restart reads the isolated fixture and preserves prior approvals.
        TradeService(self.auth)
        self.assertEqual(self.snapshot(),before)
        self.trade.agreement=SupplierAgreementService(self.auth,self.agreement_path)
        self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'SUSPENDED','reason':'Synthetic QA hold'})
        before=self.snapshot()
        with self.assertRaises(BuyerError):self.trade.save_application(owner,{**self.form(),'submit':True})
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.trade.application(owner)['status'],'SUSPENDED')
        self.assertIsNone(self.trade.public_supplier(owner['id']))

    def test_activation_rechecks_account_and_rejects_sales_and_forged_owner_identity(self):
        owner=self.prepare()
        for column,value in [('is_test_workspace',1),('status','SUSPENDED'),('deleted_at',1),
            ('email_verified_at',None),('role','PLATFORM_ADMIN')]:
            with self.subTest(column=column):
                with self.auth.connect() as db:
                    original=db.execute('SELECT '+column+' FROM users WHERE id=?',(owner['id'],)).fetchone()[0]
                    db.execute('UPDATE users SET '+column+'=? WHERE id=?',(value,owner['id']))
                before=self.snapshot()
                with self.assertRaises(BuyerError) as error:self.trade.save_application(owner,{**self.form(),'submit':True})
                self.assertEqual(error.exception.status,403)
                self.assertEqual(self.snapshot(),before)
                with self.auth.connect() as db:db.execute('UPDATE users SET '+column+'=? WHERE id=?',(original,owner['id']))
        for principal in ({**owner,'supplier_role':'SALES'}, {**owner,'actor_user_id':'buyer-b'}):
            before=self.snapshot()
            with self.assertRaises(BuyerError) as error:self.trade.save_application(principal,{**self.form(),'submit':True})
            self.assertEqual(error.exception.status,403)
            self.assertEqual(self.snapshot(),before)

    def test_all_business_read_surfaces_project_expiry_and_leave_entire_database_unchanged(self):
        buyer,owner,listing,inquiry,quote=self.quote(expire=True)
        before=self.snapshot()
        calls=[lambda:self.trade.buyer_quote(buyer,quote['id']),lambda:self.trade.quote_rows(buyer),
            lambda:self.trade.quote_rows(owner,True),lambda:self.trade.supplier_quote(owner,quote['id']),
            lambda:self.trade.crm_detail(owner,buyer['id']),lambda:self.trade.supplier_inquiries(owner,inquiry['id']),
            lambda:self.trade.supplier_overview(owner),lambda:self.trade.application(owner),
            lambda:self.trade.supplier_profile(owner),lambda:self.trade.agreement.current(owner),
            lambda:self.trade.buyer_inquiry(buyer,inquiry['id']),lambda:self.trade.public_supplier(owner['id']),
            lambda:self.trade.vehicle(listing,public=True),lambda:self.trade.recent_views(buyer),
            lambda:BuyerService(self.auth).membership_page(buyer),lambda:self.trade.platform.entitlements(buyer)]
        for call in calls:
            call()
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.trade.buyer_quote(buyer,quote['id'])['status'],'EXPIRED')
        self.assertEqual(self.trade.supplier_quote(owner,quote['id'])['status'],'EXPIRED')
        self.assertEqual(self.trade.crm_detail(owner,buyer['id'])['quotes'][0]['status'],'EXPIRED')
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM trade_quotes WHERE id=?',(quote['id'],)).fetchone()[0],'SENT')
            self.assertIsNone(db.execute('SELECT viewed_at FROM buyer_inquiries WHERE id=?',(inquiry['id'],)).fetchone()[0])

    def test_expired_response_and_read_acknowledgement_fail_without_any_write(self):
        buyer,owner,listing,inquiry,quote=self.quote(expire=True)
        before=self.snapshot()
        for call in (lambda:self.trade.buyer_quote(buyer,quote['id'],'ACCEPTED'),
            lambda:self.trade.buyer_quote(buyer,quote['id'],'REJECTED'),
            lambda:self.trade.mark_quote_viewed(buyer,quote['id'])):
            with self.assertRaises(BuyerError) as error:call()
            self.assertEqual(error.exception.status,409)
            self.assertEqual(self.snapshot(),before)

    def test_http_get_is_readonly_and_viewed_post_is_explicit_scoped_and_idempotent(self):
        buyer,owner,listing,inquiry,quote=self.quote()
        base=self.server()
        tokens={key:self.auth.session_for_user(key)['access_token'] for key in ('buyer-a','buyer-b','supplier-a')}
        before=self.snapshot()
        endpoints={'buyer-a':['/autolink/me','/autolink/buyer/overview','/autolink/buyer/inquiries',
            '/autolink/buyer/inquiries/'+inquiry['id'],'/autolink/buyer/quotes',
            '/autolink/buyer/quotes/'+quote['id'],'/autolink/buyer/membership','/autolink/buyer/entitlements'],
            'supplier-a':['/autolink/supplier/application','/autolink/supplier/agreement',
            '/autolink/supplier/overview','/autolink/supplier/inquiries/'+inquiry['id'],
            '/autolink/supplier/quotes','/autolink/supplier/quotes/'+quote['id'],
            '/autolink/supplier/buyers/'+buyer['id'],'/autolink/supplier/team',
            '/autolink/supplier/contexts','/autolink/supplier/invitations']}
        for user,paths in endpoints.items():
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(self.request(base,path,tokens[user])[0],200)
                    self.assertEqual(self.snapshot(),before)
        path='/autolink/buyer/quotes/'+quote['id']+'/viewed'
        self.assertEqual(self.request(base,path,tokens['buyer-a'])[0],404)
        self.assertEqual(self.request(base,path,tokens['buyer-b'],'POST',{})[0],404)
        self.assertEqual(self.request(base,path,tokens['buyer-a'],'POST',{},'https://other.example')[0],403)
        self.assertEqual(self.snapshot(),before)
        status,response=self.request(base,path,tokens['buyer-a'],'POST',{})
        self.assertEqual(status,200);self.assertEqual(response['data']['status'],'VIEWED')
        after=self.snapshot()
        self.assertEqual(self.request(base,path,tokens['buyer-a'],'POST',{})[0],200)
        self.assertEqual(self.snapshot(),after)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM trade_audit WHERE action='QUOTE_VIEWED' AND entity_id=?",(quote['id'],)).fetchone()[0],1)
        with self.auth.connect() as db:db.execute('UPDATE trade_quotes SET valid_until=? WHERE id=?',
            (str(date.today()-timedelta(days=1)),quote['id']))
        before=self.snapshot()
        for suffix,body in [('/response',{'decision':'ACCEPTED'}),('/response',{'decision':'REJECTED'}),('/viewed',{})]:
            self.assertEqual(self.request(base,'/autolink/buyer/quotes/'+quote['id']+suffix,tokens['buyer-a'],'POST',body)[0],409)
            self.assertEqual(self.snapshot(),before)

    def test_http_inquiry_viewed_uses_put_and_get_stays_readonly_with_company_authorization(self):
        listing=self.approved_vehicle()
        buyer,owner=self.users['buyer-a'],self.users['supplier-a']
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        base=self.server()
        tokens={key:self.auth.session_for_user(key)['access_token'] for key in ('buyer-a','supplier-a','supplier-b')}
        path='/autolink/supplier/inquiries/'+inquiry['id']
        before=self.snapshot()
        status,response=self.request(base,path,tokens['supplier-a'])
        self.assertEqual(status,200);self.assertEqual(response['data']['status'],'SUBMITTED')
        self.assertIsNone(response['data']['viewed_at'])
        self.assertEqual(self.snapshot(),before)
        for key in ('buyer-a','supplier-b'):
            self.assertEqual(self.request(base,path,tokens[key],'PUT',{'status':'VIEWED'})[0],403)
            self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.request(base,path,tokens['supplier-a'],'PUT',{'status':'VIEWED'},'https://other.example')[0],403)
        self.assertEqual(self.snapshot(),before)
        status,response=self.request(base,path,tokens['supplier-a'],'PUT',{'status':'VIEWED'})
        self.assertEqual(status,200);self.assertEqual(response['data']['status'],'VIEWED')
        self.assertIsNotNone(response['data']['viewed_at'])
        after=self.snapshot()
        self.assertEqual(self.request(base,path,tokens['supplier-a'])[1]['data']['status'],'VIEWED')
        self.assertEqual(self.snapshot(),after)

    def test_business_owner_can_buy_from_other_company_but_self_and_team_cannot(self):
        listing=self.approved_vehicle('buyer-a')
        owner=self.users['buyer-a'];other=self.users['supplier-b']
        buyer=BuyerService(self.auth)
        for index,role in enumerate(('MERCHANT','SUPPLIER')):
            other=self.users[('supplier-a','supplier-b')[index]]
            with self.auth.connect() as db:db.execute('UPDATE users SET role=? WHERE id=?',(role,other['id']))
            principal=buyer.require(self.auth.session_for_user(other['id'])['access_token'])
            inquiry=self.trade.create_inquiry(principal,{'listingId':listing,'quantity':2+index,'destinationCountry':'Kenya'})
            self.assertEqual(inquiry['buyer_id'],other['id'])
        with self.assertRaises(BuyerError):self.trade.create_inquiry(owner,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        own_request=buyer.create_request(owner,{'title':'Synthetic self-company request','vehicleId':'zeekr-9x-2026',
            'quantity':2,'destinationCountry':'Kenya','status':'PUBLISHED','publishConsent':True})
        self.assertEqual(self.trade.buying_requests(owner),[])
        with self.assertRaises(BuyerError):self.trade.respond_to_request(owner,own_request['id'],{
            'listingId':listing,'unitPriceMinor':1850000,'validUntil':str(date.today())})
        invited=self.trade.team.invite(owner,{'email':self.users['buyer-b']['email']})
        self.trade.team.accept(self.users['buyer-b'],invited['id'])
        with self.assertRaises(BuyerError):self.trade.create_inquiry(self.users['buyer-b'],{
            'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})

    def test_buyer_company_owner_team_mail_and_sales_permissions_work_without_role_promotion(self):
        listing=self.approved_vehicle('buyer-a')
        owner=self.users['buyer-a'];recipient=self.users['buyer-b'];client=self.users['supplier-b']
        inquiry=self.trade.create_inquiry(client,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        invite=self.trade.team.invite(owner,{'email':recipient['email']})
        transport=Mock(return_value='synthetic-provider-accepted')
        BusinessMailer(self.auth,sender=transport).process_once(limit=20)
        self.assertIn(recipient['email'],[call.args[0] for call in transport.call_args_list])
        self.trade.team.accept(recipient,invite['id'])
        sales=self.trade.team.principal(recipient,owner['id'],approved=True)
        self.assertEqual(self.trade.supplier_inquiries(sales),[])
        for call in (lambda:self.trade.save_application(sales,{**self.form(),'submit':True}),
            lambda:self.trade.agreement.confirm(sales,{}),lambda:self.trade.team.invite(sales,{'email':'other@example.com'})):
            with self.assertRaises(BuyerError):call()
        self.trade.team.assign(owner,client['id'],{'userId':recipient['id']})
        self.assertEqual(self.trade.supplier_inquiries(sales)[0]['id'],inquiry['id'])
        self.trade.team.remove(owner,recipient['id'])
        with self.assertRaises(BuyerError):self.trade.supplier_inquiries(sales)
        with self.auth.connect() as db:
            roles={row['id']:row['role'] for row in db.execute('SELECT id,role FROM users')}
            self.assertEqual(roles[owner['id']],'BUYER');self.assertEqual(roles[recipient['id']],'BUYER')


if __name__=='__main__':unittest.main()
