"""Notification, contact and application boundaries use real isolated SQLite."""
import unittest
import threading
import time
import json
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from datetime import date, timedelta
import test_trade
from buyer_service import BuyerError, BuyerService


class PlatformFlowTests(unittest.TestCase):
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        self.platform = self.trade.platform

    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle

    def test_saved_supplier_is_idempotent_and_scoped_to_the_buyer(self):
        self.approved_vehicle()
        service=BuyerService(self.auth)
        buyer,other=self.users['buyer-a'],self.users['buyer-b']
        for _ in range(2):
            saved=service.save_supplier(buyer,'supplier-a')
            self.assertEqual(len(saved),1)
            self.assertEqual(saved[0]['verificationStatus'],'COMPANY_CHECKED')
        self.assertEqual(service.suppliers(other,saved=True),[])
        service.save_supplier(other,'supplier-a',add=False)
        self.assertEqual(service.overview(buyer)['counts']['savedSuppliers'],1)
        self.assertEqual(service.overview(other)['counts']['savedSuppliers'],0)
        for forbidden in ('email','registration_no','review_reason','password_hash','stored_name'):
            self.assertNotIn(forbidden,json.dumps(saved))
        for invalid in ('',None,{'supplierId':'supplier-a'},'x'*101):
            with self.subTest(invalid=invalid),self.assertRaises(BuyerError) as raised:
                service.save_supplier(buyer,invalid)
            self.assertEqual(raised.exception.status,400)

    def test_saved_supplier_hides_revoked_profiles_and_preserves_saved_history(self):
        self.approved_vehicle()
        service=BuyerService(self.auth)
        buyer,other=self.users['buyer-a'],self.users['buyer-b']
        service.save_supplier(buyer,'supplier-a')
        cases=(("users","status","SUSPENDED","ACTIVE"),
               ("users","deleted_at",1,None),
               ("users","email_verified_at",None,int(time.time())),
               ("users","role","BUYER","MERCHANT"),
               ("supplier_profiles","published",0,1),
               ("supplier_applications","status","REQUIRES_CHANGES","APPROVED"))
        for table,column,revoked,restored in cases:
            owner_column={'users':'id','supplier_profiles':'user_id','supplier_applications':'supplier_id'}[table]
            with self.subTest(table=table,column=column):
                with self.auth.connect() as db:
                    db.execute(f'UPDATE {table} SET {column}=? WHERE {owner_column}=?',(revoked,'supplier-a'))
                self.assertEqual(service.suppliers(buyer),[])
                self.assertEqual(service.suppliers(buyer,saved=True),[])
                with self.assertRaises(BuyerError) as raised:service.save_supplier(other,'supplier-a')
                self.assertEqual(raised.exception.status,404)
                with self.auth.connect() as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM buyer_saved_suppliers WHERE user_id=?',(buyer['id'],)).fetchone()[0],1)
                    db.execute(f'UPDATE {table} SET {column}=? WHERE {owner_column}=?',(restored,'supplier-a'))
                self.assertEqual(len(service.suppliers(buyer,saved=True)),1)
        with self.auth.connect() as db:db.execute("UPDATE supplier_profiles SET published=0 WHERE user_id='supplier-a'")
        self.assertEqual(service.save_supplier(buyer,'supplier-a',add=False),[])
        self.assertEqual(service.overview(buyer)['counts']['savedSuppliers'],0)

    def test_admin_account_summary_reuses_membership_and_limits_private_fields(self):
        listing=self.approved_vehicle()
        buyer=self.users['buyer-a']; supplier=self.users['supplier-a']
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Saudi Arabia'})
        self.trade.create_quote(supplier,inquiry['id'],{'unitPriceMinor':100,'validUntil':str(date.today()),'send':True})
        self.trade.create_quote(supplier,inquiry['id'],{'unitPriceMinor':200,'validUntil':str(date.today())})
        invitation=self.trade.team.invite(supplier,{'email':buyer['email']})
        self.trade.team.accept(buyer,invitation['id'])
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("INSERT INTO buyer_profiles(user_id,country,city) VALUES ('buyer-a','Saudi Arabia','Riyadh')")
            db.execute("UPDATE users SET preferred_language='ar',google_sub='qa-private-google-sub' WHERE id='buyer-a'")
            db.execute("INSERT INTO email_passwords VALUES ('buyer-a','qa-private-password-hash',?)",(now,))
            db.execute("INSERT INTO buyer_memberships VALUES ('QA-MEM','buyer-a','quarterly','ACTIVE',?,?,0)",(now-1000,now-1))
            before=dict(db.execute("SELECT * FROM users WHERE id='buyer-a'").fetchone())
        detail=self.trade.admin_user_detail(self.users['admin'],'buyer-a')
        self.assertEqual(detail['account']['id'],'buyer-a')
        self.assertEqual(detail['profile']['country'],'Saudi Arabia')
        self.assertEqual(detail['account']['preferred_language'],'ar')
        self.assertEqual(detail['membership']['status'],'EXPIRED')
        self.assertEqual(detail['membership']['plan'],'quarterly')
        self.assertEqual(detail['counts']['buyerInquiries'],1)
        self.assertEqual(detail['counts']['buyerQuotes'],1)
        self.assertEqual(detail['counts']['supplierInquiries'],0)
        self.assertEqual(detail['supplierWorkspaces'][0]['role'],'SALES')
        self.assertEqual(detail['supplierWorkspaces'][0]['supplier_id'],'supplier-a')
        serialized=json.dumps(detail)
        for forbidden in ('qa-private-google-sub','qa-private-password-hash','password_hash','token_hash',
                          'code_hash','registration_no','stored_name','review_reason','metadata'):
            self.assertNotIn(forbidden,serialized)
        self.assertTrue(all(set(item)=={'action','entity_type','entity_id','created_at'} for item in detail['activity']))
        with self.auth.connect() as db:
            self.assertEqual(dict(db.execute("SELECT * FROM users WHERE id='buyer-a'").fetchone()),before)
            db.execute("UPDATE buyer_memberships SET end_at=? WHERE id='QA-MEM'",(now+1000,))
        self.assertEqual(self.trade.admin_user_detail(self.users['admin'],'buyer-a')['membership']['status'],'ACTIVE')
        self.assertEqual(self.trade.admin_user_detail(self.users['admin'],'buyer-b')['membership']['status'],'FREE')
        self.assertEqual(self.trade.admin_user_detail(self.users['admin'],'supplier-a')['counts']['supplierInquiries'],1)
        self.assertEqual(self.trade.admin_user_detail(self.users['admin'],'supplier-a')['counts']['supplierQuotes'],2)
        self.assertEqual(self.trade.admin_user_detail(self.users['admin'],'supplier-a')['supplierWorkspaces'][0]['role'],'OWNER')

    def test_admin_account_summary_denies_non_admin_and_rechecks_suspension(self):
        for account in ('buyer-a','supplier-a'):
            with self.assertRaises(BuyerError) as raised:
                self.trade.admin_user_detail(self.users[account],'buyer-b')
            self.assertEqual(raised.exception.status,403)
        with self.assertRaises(BuyerError) as raised:
            self.trade.admin_user_detail(self.users['admin'],'unknown-user')
        self.assertEqual(raised.exception.status,404)
        with self.auth.connect() as db:db.execute("UPDATE users SET status='SUSPENDED' WHERE id='admin'")
        with self.assertRaises(BuyerError) as raised:
            self.trade.admin_user_detail(self.users['admin'],'buyer-a')
        self.assertEqual(raised.exception.status,403)

    def test_admin_account_detail_http_guard_and_unknown_routes(self):
        Handler=test_trade.Handler
        Handler.service=self.auth;Handler.trade=self.trade;Handler.platform=self.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)+'/autolink/admin/users/'
        tokens={name:self.auth.session_for_user(name)['access_token'] for name in ('buyer-a','supplier-a','admin')}
        def request(account,tail):
            return urllib.request.Request(base+tail,headers={'Cookie':'autolink_session='+tokens[account]} if account else {})
        for account,tail,status in ((None,'buyer-a',401),('buyer-a','buyer-b',403),('supplier-a','buyer-a',403),
                                    ('admin','unknown-user',404),('admin','buyer-a/unexpected',404)):
            with self.subTest(account=account,tail=tail),self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request(account,tail))
            self.assertEqual(raised.exception.code,status);raised.exception.close()
        with urllib.request.urlopen(request('admin','buyer-a')) as response:
            payload=json.load(response)
            self.assertEqual(payload['data']['account']['id'],'buyer-a')
            self.assertEqual(response.status,200)
        with self.auth.connect() as db:db.execute("UPDATE users SET role='BUYER' WHERE id='admin'")
        with self.assertRaises(urllib.error.HTTPError) as raised:urllib.request.urlopen(request('admin','buyer-a'))
        self.assertEqual(raised.exception.code,403);raised.exception.close()

    def test_public_company_profile_is_opt_in_and_preserves_reviewed_identity(self):
        self.approved_vehicle()
        owner = self.users['supplier-a']
        before = self.trade.application(owner)
        initial = self.trade.public_supplier(owner['id'])
        self.assertIsNone(initial['contact'])
        self.assertEqual(initial['joined_at'], owner['created_at'])
        body = {'description':'Export stock and trade support.', 'logoUrl':'https://images.example.com/company.png',
                'contactName':'Export sales','contactEmail':'Sales@Export.example.com','contactPhone':'+86 138 0000 0000',
                'contactWebsite':'https://export.example.com','contactAddress':'Public showroom, Shanghai',
                'publishContact':False}
        saved = self.trade.save_supplier_profile(owner,body)
        self.assertEqual(saved['contact_email'],'sales@export.example.com')
        self.assertIsNone(self.trade.public_supplier(owner['id'])['contact'])
        self.trade.save_supplier_profile(owner,{**body,'publishContact':True})
        public = self.trade.public_supplier(owner['id'])
        self.assertEqual(public['contact']['email'],'sales@export.example.com')
        self.assertEqual(public['description'],body['description'])
        self.assertEqual(public['logo_url'],body['logoUrl'])
        self.assertNotIn(owner['email'],json.dumps(public))
        for key in ('registration_no','review_reason','reviewed_by','password_hash','public_contact_email','contact_email'):
            self.assertNotIn(key,public)
        self.assertEqual(self.trade.application(owner),before)
        self.trade.save_supplier_profile(owner,{**body,'publishContact':False})
        public = self.trade.public_supplier(owner['id'])
        self.assertIsNone(public['contact'])
        self.assertNotIn('sales@export.example.com',json.dumps(public))
        self.assertEqual(self.trade.supplier_profile(owner)['contact_email'],'sales@export.example.com')
        with self.auth.connect() as db:
            audits = db.execute("SELECT metadata FROM trade_audit WHERE action='COMPANY_PUBLIC_PROFILE_CHANGED'").fetchall()
            self.assertEqual(len(audits),3)
            self.assertFalse(any('sales@export.example.com' in row['metadata'] for row in audits))
        # Repeat migration preserves saved data and does not publish other accounts.
        test_trade.TradeService(self.auth)
        self.assertEqual(self.trade.supplier_profile(owner)['contact_enabled'],0)

    def test_company_profile_rejects_invalid_contact_urls_and_privilege_fields(self):
        self.approved_vehicle()
        owner = self.users['supplier-a']
        invalid = ({'publishContact':'true'}, {'publishContact':True}, {'contactEmail':'not-an-email'},
                   {'contactPhone':'javascript:alert(1)'}, {'description':'invalid\x00text'},
                   {'companyName':'Replace reviewed name'}, {'published':1}, {'status':'APPROVED'},
                   {'supplierId':'supplier-b'}, {'role':'PLATFORM_ADMIN'})
        for body in invalid:
            with self.subTest(body=body),self.assertRaises(BuyerError) as raised:
                self.trade.save_supplier_profile(owner,body)
            self.assertEqual(raised.exception.status,400)
        for url in ('javascript:alert(1)','data:image/svg+xml,test','http://images.example.com/logo.png',
                    'https://user:password@images.example.com/logo.png','https://127.0.0.1/x',
                    'https://192.168.1.1/x','https://a.local/logo.png','https://example.com:9999/logo.png',
                    'https://autolinkglobal.com/autolink/supplier/documents/DOC-1',
                    'https://autolinkglobal.com/assets/%2e%2e/autolink/private', 'https://example.com/x\nheader'):
            with self.subTest(url=url),self.assertRaises(BuyerError):
                self.trade.save_supplier_profile(owner,{'logoUrl':url})
        self.trade.save_supplier_profile(owner,{'logoUrl':'https://autolinkglobal.com/assets/company.png'})

    def test_company_profile_rechecks_owner_and_suspension_and_hides_inactive_suppliers(self):
        self.approved_vehicle()
        owner = self.users['supplier-a']
        for principal in (self.users['buyer-a'],{**owner,'supplier_role':'SALES','actor_user_id':'buyer-a'},
                          {**owner,'actor_user_id':'supplier-b'}):
            for operation in (lambda:self.trade.supplier_profile(principal),
                              lambda:self.trade.save_supplier_profile(principal,{'description':'attempt'})):
                with self.assertRaises(BuyerError) as raised:operation()
                self.assertEqual(raised.exception.status,403)
        self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'SUSPENDED','reason':'QA suspension'})
        with self.assertRaises(BuyerError):self.trade.save_supplier_profile(owner,{'description':'stale owner'})
        self.assertIsNone(self.trade.public_supplier(owner['id']))
        self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'APPROVED'})
        for assignments in ("deleted_at=1", "role='PLATFORM_ADMIN'", "email_verified_at=NULL", "status='SUSPENDED'"):
            with self.auth.connect() as db:
                db.execute('UPDATE users SET '+assignments+' WHERE id=?',(owner['id'],))
            self.assertIsNone(self.trade.public_supplier(owner['id']))
            with self.auth.connect() as db:
                db.execute("UPDATE users SET deleted_at=NULL,role='MERCHANT',email_verified_at=1,status='ACTIVE' WHERE id=?",(owner['id'],))

    def test_company_profile_http_enforces_workspace_owner_and_origin(self):
        self.approved_vehicle(); self.approved_vehicle('supplier-b')
        invite = self.trade.team.invite(self.users['supplier-a'],{'email':'buyer-a@example.com'})
        self.trade.team.accept(self.users['buyer-a'],invite['id'])
        Handler = test_trade.Handler
        Handler.service=self.auth; Handler.trade=self.trade; Handler.platform=self.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)+'/autolink/supplier/profile'
        tokens={key:self.auth.session_for_user(key)['access_token'] for key in ('supplier-a','supplier-b','buyer-a','buyer-b','admin')}
        def request(account,company=None,body=None,origin='https://autolinkglobal.com'):
            headers={'Content-Type':'application/json','Origin':origin}
            if account:headers['Cookie']='autolink_session='+tokens[account]
            if company:headers['X-Autolink-Supplier']=company
            return urllib.request.Request(base,headers=headers,method='GET' if body is None else 'PUT',
                                          data=None if body is None else json.dumps(body).encode())
        for account,company,body,origin,expected in (
                (None,None,None,'https://autolinkglobal.com',401),
                ('buyer-b','supplier-a',None,'https://autolinkglobal.com',404),
                ('supplier-b','supplier-a',None,'https://autolinkglobal.com',404),
                ('admin','supplier-a',None,'https://autolinkglobal.com',403),
                ('buyer-a','supplier-a',None,'https://autolinkglobal.com',403),
                ('buyer-a','supplier-a',{'description':'Sales edit'},'https://autolinkglobal.com',403),
                ('supplier-a','supplier-a',{'description':'Cross site'},'https://evil.example',403)):
            with self.subTest(account=account,body=body),self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request(account,company,body,origin))
            self.assertEqual(raised.exception.code,expected);raised.exception.close()
        with urllib.request.urlopen(request('supplier-a','supplier-a',{'description':'Owner public overview'})) as response:
            self.assertEqual(json.load(response)['data']['description'],'Owner public overview')
        with urllib.request.urlopen(request('supplier-b','supplier-b')) as response:
            self.assertNotEqual(json.load(response)['data']['description'],'Owner public overview')

    def test_contact_and_quote_expiry_are_owner_scoped(self):
        listing = self.approved_vehicle()
        buyer = self.users['buyer-a']
        inquiry = self.trade.create_inquiry(buyer, {'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        contact = self.trade.buyer_supplier_contact(buyer,inquiry['id'])
        self.assertEqual(contact['email'],'supplier-a@example.com')
        self.assertIsNone(self.trade.buyer_supplier_contact(self.users['buyer-b'],inquiry['id']))
        self.assertNotIn('registration_no',contact)
        quote = self.trade.create_quote(self.users['supplier-a'],inquiry['id'],{
            'unitPriceMinor':100,'validUntil':str(date.today()),'send':True})
        with self.auth.connect() as db:
            db.execute('UPDATE trade_quotes SET valid_until=? WHERE id=?',(str(date.today()-timedelta(days=1)),quote['id']))
        self.assertEqual(self.trade.quote_rows(buyer)[0]['status'],'EXPIRED')
        self.assertEqual(self.trade.buyer_quote(buyer,quote['id'])['supplierContact']['email'],contact['email'])
        with self.assertRaises(BuyerError):self.trade.buyer_quote(self.users['buyer-b'],quote['id'])

    def test_notifications_cannot_be_read_by_another_account(self):
        with self.auth.connect() as db:
            self.platform.notify(db,'buyer-a','TEST','test','/buyer')
        notices=self.platform.notifications(self.users['buyer-a'])
        self.assertEqual(len(notices),1)
        self.assertEqual(self.platform.notifications(self.users['buyer-b']),[])
        with self.assertRaises(BuyerError):self.platform.mark_notification(self.users['buyer-b'],notices[0]['id'])
        self.platform.mark_notification(self.users['buyer-a'],notices[0]['id'])
        self.assertIsNotNone(self.platform.notifications(self.users['buyer-a'])[0]['read_at'])

    def test_buyer_overview_counts_all_unread_notifications_and_is_account_scoped(self):
        now = int(time.time())
        with self.auth.connect() as db:
            rows = [('qa-notice-'+str(n), 'buyer-a', 'NEW_QUOTE', 'qa-quote', '/buyer/quotes',
                     now-300+n, None if n < 105 else now) for n in range(205)]
            rows += [('qa-other-'+str(n), 'buyer-b', 'NEW_QUOTE', 'qa-other', '/buyer/quotes', now, None)
                     for n in range(7)]
            db.executemany('INSERT INTO account_notifications VALUES (?,?,?,?,?,?,?)', rows)
        buyer, other = self.users['buyer-a'], self.users['buyer-b']
        self.assertEqual(len(self.platform.notifications(buyer)), 100)
        self.assertTrue(all(row['read_at'] for row in self.platform.notifications(buyer)))
        self.assertEqual(self.platform.unread_notification_count(buyer), 105)
        self.assertEqual(self.platform.unread_notification_count(other), 7)
        self.assertEqual(self.platform.unread_notification_count(self.users['supplier-a']), 0)
        class TestHandler(test_trade.Handler):
            pass
        TestHandler.service = self.auth
        TestHandler.buyer = BuyerService(self.auth)
        TestHandler.trade = self.trade
        TestHandler.platform = self.platform
        server = ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        endpoint = 'http://127.0.0.1:'+str(server.server_port)+'/autolink/buyer/overview'
        for account, expected in ((buyer, 105), (other, 7)):
            token = self.auth.session_for_user(account['id'])['access_token']
            request = urllib.request.Request(endpoint, headers={'Cookie': 'autolink_session='+token})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(json.loads(response.read())['data']['unreadNotifications'], expected)
        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(endpoint)
        self.assertEqual(denied.exception.code, 401)
        denied.exception.close()
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM account_notifications WHERE user_id='buyer-a' AND read_at IS NULL").fetchone()[0], 105)

    def test_membership_application_does_not_grant_paid_access(self):
        buyer=self.users['buyer-a']
        body={'type':'Membership','subject':'Membership application','message':'Contact me about the monthly plan.',
              'plan':'monthly','language':'ar','consent':True}
        with self.assertRaises(BuyerError):self.platform.contact(buyer,{**body,'consent':False},'test-ip')
        result=self.platform.contact(buyer,body,'test-ip')
        self.assertFalse(result['paymentAvailable'])
        self.assertFalse(self.platform.entitlements(buyer)['membershipActive'])
        with self.auth.connect() as db:
            row=db.execute('SELECT * FROM membership_applications WHERE user_id=?',(buyer['id'],)).fetchone()
            self.assertEqual(row['language'],'ar')
            self.assertEqual(row['status'],'PENDING')
        for _ in range(2):self.platform.contact(None,{'type':'General Support','email':'a@example.com','subject':'Help','message':'Please help.'},'test-ip')
        with self.assertRaises(BuyerError) as raised:self.platform.contact(buyer,body,'test-ip')
        self.assertEqual(raised.exception.status,429)

    def test_buyer_application_does_not_grant_supplier_tools_before_review(self):
        token=self.auth.session_for_user('buyer-a')['access_token']
        self.assertEqual(self.trade.require_supplier(token,approved=False)['role'],'BUYER')
        with self.assertRaises(BuyerError):self.trade.require_supplier(token,approved=True)
        self.approved_vehicle('buyer-a')
        self.assertEqual(self.trade.require_supplier(token,approved=True)['id'],'buyer-a')
        self.assertEqual(self.auth.user_for_token(token)['role'],'BUYER')
        self.assertEqual(len(self.trade.vehicle_rows(public=True)),1)

    def test_reports_need_verified_identity_and_valid_entity(self):
        listing=self.approved_vehicle()
        body={'entityType':'vehicle','entityId':listing,'reason':'Incorrect Price','message':'Please check this price.'}
        user=self.users['buyer-a']
        with self.assertRaises(BuyerError):self.platform.report({**dict(user),'email_verified_at':None},body)
        result=self.platform.report(user,body)
        self.platform.review_report(self.users['admin'],result['id'],{'status':'RESOLVED','resolution':'Reviewed listing details.'})
        self.assertEqual(self.platform.reports()[0]['status'],'RESOLVED')

    def test_public_search_filters_use_real_listing_and_catalog_fields(self):
        self.approved_vehicle()
        self.assertEqual(len(self.trade.vehicle_rows(public=True,filters={'brand':'Zeekr','model':'9X','vehicleType':'SUV'})),1)
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'model':'Not a model'}),[])
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'minPriceMinor':2000000}),[])
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'vehicleType':'Sedan'}),[])

    def test_search_combines_year_stock_price_supplier_and_real_recent_popularity(self):
        first=self.approved_vehicle()
        second=self.approved_vehicle('supplier-b')
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_vehicles SET model_year=2025,price_minor=1700000,stock=3,steering='RHD',vehicle_condition='USED',energy_type='EV',updated_at=100 WHERE id=?",(second,))
            db.execute("UPDATE supplier_vehicles SET updated_at=200 WHERE id=?",(first,))
        self.trade.record_view(self.users['buyer-a'],first)
        self.trade.record_view(self.users['buyer-b'],first)
        self.trade.record_view(self.users['buyer-a'],second)
        rows=self.trade.vehicle_rows(public=True,supplier_id='supplier-b',filters={
            'brand':'Zeekr','model':'9X','vehicleType':'SUV','year':'2025','minStock':'3',
            'condition':'USED','steering':'RHD','energyType':'Electric','incoterm':'FOB',
            'minPriceMinor':'1600000','maxPriceMinor':'1750000','sort':'price_asc'})
        self.assertEqual([r['id'] for r in rows],[second])
        for filters in ({'year':2024},{'minStock':13},{'maxPriceMinor':1600000}):
            self.assertEqual(self.trade.vehicle_rows(public=True,filters=filters),[])
        self.assertEqual([r['id'] for r in self.trade.vehicle_rows(public=True,filters={'sort':'popular'})],[first,second])
        self.assertEqual([r['id'] for r in self.trade.vehicle_rows(public=True,filters={'sort':'price_asc'})],[second,first])
        self.assertEqual([r['id'] for r in self.trade.vehicle_rows(public=True,filters={'sort':'price_desc'})],[first,second])
        with self.auth.connect() as db:
            db.execute("UPDATE buyer_vehicle_views SET viewed_at=? WHERE listing_id=?",(int(time.time())-31*86400,first))
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'sort':'popular'})[0]['id'],second)
        # Suspended viewers and unverified accounts never boost popularity.
        with self.auth.connect() as db:
            db.execute("UPDATE users SET status='SUSPENDED' WHERE id='buyer-a'")
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'sort':'popular'})[0]['id'],first)
        self.assertFalse(any('viewer' in k or 'popularity' in k for r in rows for k in r))
        self.trade.transition_vehicle(self.users['supplier-b'],second,'offline')
        self.assertEqual(self.trade.vehicle_rows(public=True,supplier_id='supplier-b'),[])

    def test_search_pagination_has_stable_ties_and_literal_keyword_matching(self):
        first=self.approved_vehicle()
        with self.auth.connect() as db:
            columns=[r[1] for r in db.execute('PRAGMA table_info(supplier_vehicles)')]
            row=dict(db.execute('SELECT * FROM supplier_vehicles WHERE id=?',(first,)).fetchone())
            for number in range(27):
                copy={**row,'id':f'QA-PAGE-{number:02}','trim':f'Batch 100%_{number:02}','updated_at':100}
                db.execute('INSERT INTO supplier_vehicles('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+')',tuple(copy[k] for k in columns))
            db.execute('UPDATE supplier_vehicles SET updated_at=100 WHERE id=?',(first,))
        page1=self.trade.vehicle_rows(public=True,limit=24,offset=0)
        page2=self.trade.vehicle_rows(public=True,limit=24,offset=24)
        self.assertEqual(len(page1),24);self.assertEqual(len(page2),4)
        self.assertFalse(set(r['id'] for r in page1)&set(r['id'] for r in page2))
        self.assertEqual([r['id'] for r in page1+page2],sorted([first]+[f'QA-PAGE-{n:02}' for n in range(27)]))
        self.assertEqual(len(self.trade.vehicle_rows(public=True,limit=50,filters={'keyword':'100%_'})),27)
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'keyword':"' OR 1=1 --"}),[])
        self.assertEqual(self.trade.vehicle_rows(public=True,filters={'keyword':'missing%'}),[])

    def test_public_http_search_validates_numeric_range_enum_and_pagination(self):
        self.approved_vehicle()
        Handler=test_trade.Handler
        Handler.service=self.auth;Handler.trade=self.trade;Handler.platform=self.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)+'/autolink/public/vehicles?'
        for query in ('year=2026&minStock=12&minPriceMinor=1800000&maxPriceMinor=1900000&sort=popular',
                      'supplierId=supplier-a&limit=1&offset=0'):
            with urllib.request.urlopen(base+query) as response:
                self.assertEqual(len(json.load(response)['data']),1)
        for query in ('year=2026.5','year=1800','minStock=-1','minStock=1.5','sort=random',
                      'minPriceMinor=2000000&maxPriceMinor=1000000','minPriceMinor=999999999999999999',
                      'condition=invalid','steering=invalid','incoterm=invalid','offset=100001'):
            with self.subTest(query=query),self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(base+query)
            self.assertEqual(raised.exception.code,400)
            raised.exception.close()
        for value in (True,1.5,-1,'1.0'):
            with self.subTest(value=value),self.assertRaises(BuyerError):
                self.trade.vehicle_rows(public=True,filters={'minStock':value})

    def test_closed_inquiry_cannot_send_a_saved_draft_quote(self):
        listing=self.approved_vehicle()
        buyer=self.users['buyer-a'];supplier=self.users['supplier-a']
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        quote=self.trade.create_quote(supplier,inquiry['id'],{'unitPriceMinor':100,'validUntil':str(date.today()),'send':False})
        self.trade.update_inquiry(supplier,inquiry['id'],{'status':'CLOSED'})
        with self.assertRaises(BuyerError) as raised:self.trade.send_quote(supplier,quote['id'])
        self.assertEqual(raised.exception.status,409)
        self.assertEqual(self.trade.quote_rows(buyer),[])
        self.assertEqual(self.trade.quote_rows(supplier,True)[0]['status'],'DRAFT')

    def test_concurrent_quote_response_cannot_overwrite_first_decision(self):
        listing=self.approved_vehicle()
        buyer=self.users['buyer-a']
        inquiry=self.trade.create_inquiry(buyer,{'listingId':listing,'quantity':2,'destinationCountry':'Kenya'})
        quote=self.trade.create_quote(self.users['supplier-a'],inquiry['id'],{'unitPriceMinor':100,'validUntil':str(date.today()),'send':True})
        gate=threading.Barrier(2);results=[]
        def respond(decision):
            gate.wait()
            try:results.append(self.trade.buyer_quote(buyer,quote['id'],decision)['status'])
            except BuyerError as error:results.append(error.status)
        threads=[threading.Thread(target=respond,args=(decision,)) for decision in ('ACCEPTED','REJECTED')]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertEqual(results.count(409),1)
        self.assertEqual(len([value for value in results if value in ('ACCEPTED','REJECTED')]),1)
