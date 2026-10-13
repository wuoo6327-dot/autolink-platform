"""Sales access, ownership, invitation identity and immediate revocation checks."""
import json
import time
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import Mock
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from app import Handler
from buyer_service import BuyerError
from email_auth import EmailAuthService
from business_mail import BusinessMailer
from mail_service import MailUnavailable
import test_trade


class SupplierTeamTests(unittest.TestCase):
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        # A supplier salesperson has a supplier identity, never a buyer identity.
        with self.auth.connect() as db:
            db.execute("UPDATE users SET role='MERCHANT' WHERE id='buyer-b'")
        self.users['buyer-b']=self.auth.user_for_token(self.auth.session_for_user('buyer-b')['access_token'])
        self.listing=self.approved_vehicle()
        self.owner=self.users['supplier-a']
        self.recipient=self.users['buyer-b']
        self.inquiry=self.trade.create_inquiry(self.users['buyer-a'],{
            'listingId':self.listing,'quantity':2,'destinationCountry':'Saudi Arabia'})
    approved_vehicle=test_trade.TradeFlowTests.approved_vehicle

    def sales(self):
        invite=self.trade.team.invite(self.owner,{'email':self.recipient['email']})
        self.trade.team.accept(self.recipient,invite['id'])
        return self.trade.team.principal(self.recipient,self.owner['id'],approved=True)

    def quote(self,sales,**extra):
        return self.trade.create_quote(sales,self.inquiry['id'],{
            'unitPriceMinor':1850000,'validUntil':str(date.today()),**extra})

    def test_invite_requires_correct_verified_recipient_and_is_single_use(self):
        invite=self.trade.team.invite(self.owner,{'email':self.recipient['email']})
        self.assertEqual(self.trade.team.invitations(self.users['buyer-a']),[])
        with self.assertRaises(BuyerError):self.trade.team.accept(self.users['buyer-a'],invite['id'])
        with self.assertRaises(BuyerError):self.trade.team.accept({**self.recipient,'email_verified_at':None},invite['id'])
        self.assertEqual(self.trade.team.accept(self.recipient,invite['id'])['role'],'SALES')
        with self.assertRaises(BuyerError):self.trade.team.accept(self.recipient,invite['id'])
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT role FROM users WHERE id=?',(self.recipient['id'],)).fetchone()[0],'MERCHANT')

    def register_invited(self,email,language='en'):
        transport=Mock()
        auth=EmailAuthService(self.auth,sender=transport)
        auth.send_code(email,'login','isolated-invitation-qa',language)
        session=auth.login_code({'email':email,'code':transport.call_args.args[1],
            'role':'MERCHANT','companyName':'Synthetic sales staff','consent':True,'language':language})
        return self.auth.user_for_token(session['access_token'])

    def test_new_email_invitation_registration_assignment_and_buyer_quote_loop(self):
        address='new-sales@outlook.com'
        invitation=self.trade.team.invite(self.owner,{'email':' New-Sales@Outlook.com '})
        self.trade.team.__class__(self.auth)
        with self.auth.connect() as db:
            indexes={r[1] for r in db.execute('PRAGMA index_list(supplier_team_invites)')}
            self.assertTrue({'supplier_invites_company_time','supplier_invites_email_time'}<=indexes)
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],5)
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_team_members').fetchone()[0],0)
            job=db.execute("SELECT * FROM business_mail_jobs WHERE event='TEAM_INVITATION'").fetchone()
            self.assertEqual((job['user_id'],job['entity_id']),('supplier-a',invitation['id']))
        transport=Mock(return_value='synthetic-provider-accepted')
        BusinessMailer(self.auth,sender=transport).process_once(limit=20)
        invited_mail=[call for call in transport.call_args_list if call.args[0]==address]
        self.assertEqual(len(invited_mail),1)
        self.assertIn('https://autolinkglobal.com/supplier/team',invited_mail[0].args[2])
        user=self.register_invited(address)
        self.assertEqual(user['role'],'MERCHANT')
        self.assertEqual(self.trade.team.invitations(user)[0]['id'],invitation['id'])
        with self.auth.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM supplier_team_members').fetchone()[0],0)
        with self.assertRaises(BuyerError):self.trade.team.accept(self.users['buyer-a'],invitation['id'])
        self.assertEqual(self.trade.team.accept(user,invitation['id'])['role'],'SALES')
        sales=self.trade.team.principal(user,'supplier-a',True)
        self.assertEqual(self.trade.supplier_inquiries(sales),[])
        self.trade.team.assign(self.owner,'buyer-a',{'userId':user['id']})
        self.trade.update_crm(sales,'buyer-a',{'status':'FOLLOW_UP','note':'New verified team member follow-up'})
        quote=self.quote(sales,send=True)
        self.assertEqual(self.trade.quote_rows(self.users['buyer-a'])[0]['id'],quote['id'])
        self.trade.team.remove(self.owner,user['id'])
        with self.assertRaises(BuyerError):self.trade.supplier_inquiries(sales)
        with self.auth.connect() as db:self.assertEqual(db.execute('SELECT role FROM users WHERE id=?',(user['id'],)).fetchone()[0],'MERCHANT')

    def test_unsent_new_email_invitation_is_cancelled_if_invitation_or_owner_is_revoked(self):
        for case in ('cancel','expire','suspend','demote','delete','unverify'):
            with self.subTest(case=case):
                with self.auth.connect() as db:db.execute("UPDATE users SET status='ACTIVE',role='MERCHANT',deleted_at=NULL,email_verified_at=? WHERE id='supplier-a'",(int(time.time()),))
                address=case+'-invite@example.com'
                invitation=self.trade.team.invite(self.owner,{'email':address})
                if case=='cancel':self.trade.team.cancel(self.owner,invitation['id'])
                else:
                    with self.auth.connect() as db:
                        if case=='expire':db.execute('UPDATE supplier_team_invites SET expires_at=0 WHERE id=?',(invitation['id'],))
                        elif case=='suspend':db.execute("UPDATE users SET status='SUSPENDED' WHERE id='supplier-a'")
                        elif case=='demote':db.execute("UPDATE users SET role='BUYER' WHERE id='supplier-a'")
                        elif case=='delete':db.execute("UPDATE users SET deleted_at=? WHERE id='supplier-a'",(int(time.time()),))
                        else:db.execute("UPDATE users SET email_verified_at=NULL WHERE id='supplier-a'")
                transport=Mock(return_value='synthetic-provider-accepted')
                BusinessMailer(self.auth,sender=transport).process_once(limit=20)
                self.assertNotIn(address,[call.args[0] for call in transport.call_args_list])
                with self.auth.connect() as db:self.assertEqual(db.execute("SELECT status FROM business_mail_jobs WHERE event='TEAM_INVITATION' AND entity_id=?",(invitation['id'],)).fetchone()[0],'CANCELLED')

    def test_new_email_invitation_retry_keeps_payload_and_changed_address_cancels(self):
        address='retry-new@example.com'
        invitation=self.trade.team.invite(self.owner,{'email':address})
        transport=Mock(side_effect=MailUnavailable('synthetic transport failure'))
        mailer=BusinessMailer(self.auth,sender=transport);mailer.process_once(limit=20)
        original=next(call for call in transport.call_args_list if call.args[0]==address)
        self.register_invited(address,'fr')
        with self.auth.connect() as db:db.execute('UPDATE business_mail_jobs SET next_attempt_at=0')
        transport.reset_mock();transport.side_effect=None;transport.return_value='synthetic-provider-accepted'
        mailer.process_once(limit=20)
        self.assertEqual(next(call for call in transport.call_args_list if call.kwargs['idempotency_key']==original.kwargs['idempotency_key']),original)
        second=self.trade.team.invite(self.owner,{'email':'changed-before-retry@example.com'})
        transport.side_effect=MailUnavailable('synthetic transport failure');mailer.process_once(limit=20)
        with self.auth.connect() as db:
            db.execute('UPDATE supplier_team_invites SET email=? WHERE id=?',('other-target@example.com',second['id']))
            db.execute('UPDATE business_mail_jobs SET next_attempt_at=0')
        transport.reset_mock();transport.side_effect=None;mailer.process_once(limit=20)
        self.assertNotIn('other-target@example.com',[call.args[0] for call in transport.call_args_list])
        with self.auth.connect() as db:self.assertEqual(db.execute('SELECT status FROM business_mail_jobs WHERE entity_id=?',(second['id'],)).fetchone()[0],'CANCELLED')

    def test_team_mutations_recheck_current_owner_and_recipient_under_lock(self):
        invitation=self.trade.team.invite(self.owner,{'email':self.recipient['email']})
        for change in ("status='SUSPENDED'","role='PLATFORM_ADMIN'","role='BUYER'","email_verified_at=NULL","email='changed@example.com'"):
            with self.auth.connect() as db:db.execute('UPDATE users SET '+change+" WHERE id='buyer-b'")
            with self.assertRaises(BuyerError) as denied:self.trade.team.accept(self.recipient,invitation['id'])
            self.assertEqual(denied.exception.status,403)
            with self.auth.connect() as db:db.execute("UPDATE users SET status='ACTIVE',role='MERCHANT',email_verified_at=?,email='buyer-b@example.com' WHERE id='buyer-b'",(int(time.time()),))
        with self.auth.connect() as db:db.execute("UPDATE users SET role='BUYER' WHERE id='supplier-a'")
        for call in (lambda:self.trade.team.invite(self.owner,{'email':'not-permitted@example.com'}),
            lambda:self.trade.team.cancel(self.owner,invitation['id']),
            lambda:self.trade.team.assign(self.owner,'buyer-a',{'userId':'buyer-b'})):
            with self.assertRaises(BuyerError) as denied:call()
            self.assertEqual(denied.exception.status,403)
        with self.assertRaises(BuyerError):self.trade.team.accept(self.recipient,invitation['id'])
        with self.auth.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM supplier_team_members').fetchone()[0],0)

    def test_team_invites_have_strict_fields_company_and_recipient_limits(self):
        for body in ({'email':'invalid'}, {'email':'a@example.com','role':'OWNER'},
            {'email':'a@example.com','supplierId':'supplier-b'}, {'email':None}, {'email':self.owner['email']}):
            with self.assertRaises(BuyerError) as invalid:self.trade.team.invite(self.owner,body)
            self.assertEqual(invalid.exception.status,400)
        for _ in range(5):
            invitation=self.trade.team.invite(self.owner,{'email':'limited-new@example.com'})
            self.trade.team.cancel(self.owner,invitation['id'])
        with self.assertRaises(BuyerError) as limited:self.trade.team.invite(self.owner,{'email':'limited-new@example.com'})
        self.assertEqual(limited.exception.status,429)
        self.approved_vehicle('supplier-b')
        with self.assertRaises(BuyerError) as limited:self.trade.team.invite(self.users['supplier-b'],{'email':'limited-new@example.com'})
        self.assertEqual(limited.exception.status,429)
        for n in range(5):self.trade.team.invite(self.owner,{'email':str(n)+'@example.com'})
        with self.assertRaises(BuyerError) as limited:self.trade.team.invite(self.owner,{'email':'eleventh@example.com'})
        self.assertEqual(limited.exception.status,429)

    def test_new_email_invitation_http_requires_owner_origin_and_correct_verified_account(self):
        self.approved_vehicle('supplier-b')
        class TestHandler(Handler):pass
        TestHandler.service=self.auth;TestHandler.trade=self.trade;TestHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        def call(user,tail,body,origin='https://autolinkglobal.com'):
            token=self.auth.session_for_user(user['id'])['access_token']
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/autolink/supplier/'+tail,
                data=json.dumps(body).encode(),headers={'Cookie':'autolink_session='+token,'Content-Type':'application/json','Origin':origin})
            try:res=urllib.request.urlopen(req)
            except urllib.error.HTTPError as err:res=err
            with res:return res.status,json.loads(res.read())
        self.assertEqual(call(self.owner,'team/invitations',{'email':'http-new@example.com'},'https://attacker.example')[0],403)
        self.assertEqual(call(self.users['buyer-a'],'team/invitations',{'email':'http-new@example.com'})[0],403)
        code,data=call(self.owner,'team/invitations',{'email':'http-new@example.com'})
        self.assertEqual(code,200);invitation=data['data']['id']
        self.assertNotIn('email',data['data']);self.assertNotIn('token',data['data'])
        self.assertEqual(call(self.users['supplier-b'],'team/invitations/'+invitation+'/cancel',{})[0],404)
        self.assertEqual(call(self.users['buyer-a'],'invitations/'+invitation+'/accept',{})[0],403)
        user=self.register_invited('http-new@example.com')
        self.assertEqual(call(user,'invitations/'+invitation+'/accept',{})[0],200)
        self.assertEqual(call(user,'invitations/'+invitation+'/accept',{})[0],404)

    def test_sales_assignment_quote_crm_and_actor_audit(self):
        sales=self.sales()
        self.assertEqual(self.trade.supplier_inquiries(sales),[])
        self.assertEqual(self.trade.crm(sales),[])
        with self.assertRaises(BuyerError):self.quote(sales)
        self.trade.team.assign(self.owner,'buyer-a',{'userId':'buyer-b'})
        self.assertEqual(self.trade.supplier_inquiries(sales)[0]['id'],self.inquiry['id'])
        self.trade.update_crm(sales,'buyer-a',{'status':'FOLLOW_UP','note':'Sales follow-up'})
        quote=self.quote(sales,send=True)
        self.assertEqual(self.trade.quote_rows(self.users['buyer-a'])[0]['id'],quote['id'])
        self.assertEqual(self.trade.quote_rows(sales,True)[0]['id'],quote['id'])
        with self.auth.connect() as db:
            audit=db.execute("SELECT actor_user_id,supplier_id FROM trade_audit WHERE action='QUOTE_SENT' AND entity_id=?",(quote['id'],)).fetchone()
            self.assertEqual(tuple(audit),('buyer-b','supplier-a'))
            self.assertEqual(db.execute('SELECT actor_id FROM supplier_crm_notes').fetchone()[0],'buyer-b')

    def test_other_company_and_unassigned_buyers_are_hidden(self):
        sales=self.sales();other=self.approved_vehicle('supplier-b')
        inquiry=self.trade.create_inquiry(self.users['buyer-a'],{'listingId':other,'quantity':2,'destinationCountry':'UAE'})
        with self.assertRaises(BuyerError):self.trade.team.principal(self.recipient,'supplier-b',True)
        self.assertEqual(self.trade.supplier_inquiries(sales,inquiry['id']),[])
        with self.assertRaises(BuyerError):self.trade.update_inquiry(sales,inquiry['id'],{'status':'CONTACTED'})
        with self.assertRaises(BuyerError):self.trade.crm_detail(sales,'buyer-a')
        with self.assertRaises(BuyerError):self.trade.team.assign(self.owner,'buyer-a',{'userId':'supplier-b'})
        with self.assertRaises(BuyerError):self.trade.team.assign(self.users['supplier-b'],'buyer-b',{'userId':'supplier-b'})

    def test_quote_list_expiry_updates_only_sales_assigned_unarchived_quotes(self):
        sales = self.sales()
        self.trade.team.assign(self.owner, 'buyer-a', {'userId': 'buyer-b'})
        assigned = self.quote(self.owner, send=True)
        with self.auth.connect() as db:
            db.execute("INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) VALUES (?,?,?,?,?,?,?)",
                       ('buyer-c','buyer-c@example.com','Synthetic other buyer','Buyer C','BUYER',int(time.time()),int(time.time())))
        other_buyer=self.auth.user_for_token(self.auth.session_for_user('buyer-c')['access_token'])
        other_inquiry = self.trade.create_inquiry(other_buyer, {
            'listingId': self.listing, 'quantity': 2, 'destinationCountry': 'UAE'})
        unassigned = self.trade.create_quote(self.owner, other_inquiry['id'], {
            'unitPriceMinor': 1890000, 'validUntil': str(date.today()), 'send': True})
        archived = self.quote(self.owner, send=True)
        yesterday = str(date.today()-timedelta(days=1))
        with self.auth.connect() as db:
            db.execute('UPDATE trade_quotes SET valid_until=?', (yesterday,))
            db.execute('UPDATE trade_quotes SET archived_at=1 WHERE id=?', (archived['id'],))
            before = dict(db.execute('SELECT * FROM trade_quotes WHERE id=?', (unassigned['id'],)).fetchone())
            archived_before = dict(db.execute('SELECT * FROM trade_quotes WHERE id=?', (archived['id'],)).fetchone())
        rows = self.trade.quote_rows(sales, True)
        self.assertEqual([(q['id'], q['status']) for q in rows], [(assigned['id'], 'EXPIRED')])
        with self.auth.connect() as db:
            self.assertEqual(dict(db.execute('SELECT * FROM trade_quotes WHERE id=?', (unassigned['id'],)).fetchone()), before)
            self.assertEqual(dict(db.execute('SELECT * FROM trade_quotes WHERE id=?', (archived['id'],)).fetchone()), archived_before)
        self.trade.quote_rows(self.owner, True)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM trade_quotes WHERE id=?', (unassigned['id'],)).fetchone()[0], 'EXPIRED')

    def test_revocation_denies_current_principal_and_preserves_history(self):
        sales=self.sales();self.trade.team.assign(self.owner,'buyer-a',{'userId':'buyer-b'})
        quote=self.quote(sales)
        self.trade.team.remove(self.owner,'buyer-b')
        for call in (lambda:self.trade.supplier_inquiries(sales),lambda:self.trade.crm(sales),
                     lambda:self.trade.quote_rows(sales,True),lambda:self.trade.send_quote(sales,quote['id']),
                     lambda:self.trade.cancel_quote(sales,quote['id'])):
            with self.assertRaises(BuyerError):call()
        self.assertEqual(self.trade.quote_rows(self.owner,True)[0]['id'],quote['id'])
        self.assertIsNone(self.trade.supplier_inquiries(self.owner)[0]['assigned_to'])
        with self.assertRaises(BuyerError):self.trade.team.principal(self.recipient,self.owner['id'],True)

    def test_expired_cancelled_and_foreign_invitations_cannot_be_used(self):
        invite=self.trade.team.invite(self.owner,{'email':self.recipient['email']})
        with self.assertRaises(BuyerError):self.trade.team.cancel(self.users['supplier-b'],invite['id'])
        self.trade.team.cancel(self.owner,invite['id'])
        with self.assertRaises(BuyerError):self.trade.team.accept(self.recipient,invite['id'])
        invite=self.trade.team.invite(self.owner,{'email':self.recipient['email']})
        with self.auth.connect() as db:db.execute('UPDATE supplier_team_invites SET expires_at=? WHERE id=?',(int(time.time())-1,invite['id']))
        with self.assertRaises(BuyerError):self.trade.team.accept(self.recipient,invite['id'])

    def test_sales_cannot_manage_team_and_suspended_company_loses_access(self):
        sales=self.sales()
        for call in (lambda:self.trade.team.invite(sales,{'email':'buyer-a@example.com'}),
                     lambda:self.trade.team.assign(sales,'buyer-a',{'userId':'buyer-b'}),
                     lambda:self.trade.team.remove(sales,'buyer-b')):
            with self.assertRaises(BuyerError) as error:call()
            self.assertEqual(error.exception.status,403)
        self.trade.review_supplier(self.users['admin'],'supplier-a',{'decision':'SUSPENDED','reason':'QA suspension'})
        with self.assertRaises(BuyerError):self.trade.team.principal(self.recipient,'supplier-a',True)
        with self.assertRaises(BuyerError):self.trade.supplier_inquiries(sales)

    def test_new_inquiry_inherits_the_buyer_sales_assignment(self):
        sales=self.sales();self.trade.team.assign(self.owner,'buyer-a',{'userId':'buyer-b'})
        with self.auth.connect() as db:db.execute('UPDATE buyer_inquiries SET created_at=?',(int(time.time())-600,))
        fresh=self.trade.create_inquiry(self.users['buyer-a'],{'listingId':self.listing,'quantity':3,'destinationCountry':'Saudi Arabia'})
        self.assertEqual(fresh['assigned_to'],'buyer-b')
        self.assertEqual(len(self.trade.supplier_inquiries(sales)),2)

    def test_api_enforces_sales_capabilities_and_company_header(self):
        self.sales();self.trade.team.assign(self.owner,'buyer-a',{'userId':'buyer-b'})
        class TestHandler(Handler):pass
        TestHandler.service=self.auth;TestHandler.trade=self.trade;TestHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        token=self.auth.session_for_user('buyer-b')['access_token']
        def call(tail,method='GET',body=None,company='supplier-a'):
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/autolink/'+tail,
                data=json.dumps(body).encode() if body is not None else None,method=method,
                headers={'Cookie':'autolink_session='+token,'X-Autolink-Supplier':company,'Content-Type':'application/json'})
            try:response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.loads(response.read())
        self.assertEqual(call('supplier/inquiries')[0],200)
        self.assertEqual(call('supplier/inquiries',company='supplier-b')[0],404)
        for tail,method,body in (('supplier/documents','GET',None),('supplier/application','GET',None),
            ('supplier/vehicles','POST',{}),('supplier/team','GET',None),('admin/overview','GET',None),
            ('supplier/buyers/buyer-a/assignment','PUT',{'userId':'buyer-b'})):
            self.assertEqual(call(tail,method,body)[0],403,(tail,method))
        self.trade.team.remove(self.owner,'buyer-b')
        self.assertEqual(call('supplier/inquiries')[0],404)

if __name__=='__main__':unittest.main()
