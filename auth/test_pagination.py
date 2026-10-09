"""Older business records remain reachable without leaking another account's totals."""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import test_trade
from app import Handler
from buyer_service import BuyerError, BuyerService
from pagination import requested_page


class BusinessPaginationTests(unittest.TestCase):
    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle

    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        self.owner, self.buyer = self.users['supplier-a'], self.users['buyer-a']
        self.listing = self.approved_vehicle()
        self.inquiry = self.trade.create_inquiry(self.buyer, {
            'listingId': self.listing, 'quantity': 2, 'destinationCountry': 'Kenya'})
        self.quote = self.trade.create_quote(self.owner, self.inquiry['id'], {
            'unitPriceMinor': 1890000, 'validUntil': str(date.today()), 'send': True})

    @staticmethod
    def clone(db, table, original, key, new_id, **changes):
        row = dict(db.execute(f'SELECT * FROM {table} WHERE {key}=?', (original,)).fetchone())
        row.update({key:new_id, **changes})
        db.execute(f'INSERT INTO {table} ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))

    def bulk(self):
        now = int(time.time())
        with self.auth.connect() as db:
            for n in range(224):
                self.clone(db,'supplier_vehicles',self.listing,'id',f'VEH-PAGE-{n:04}',status='DRAFT')
                self.clone(db,'buyer_inquiries',self.inquiry['id'],'id',f'INQ-PAGE-{n:04}',status='CLOSED')
                self.clone(db,'trade_quotes',self.quote['id'],'id',f'QUO-PAGE-{n:04}',created_at=now)
            db.execute('UPDATE trade_quotes SET created_at=0 WHERE id=?', (self.quote['id'],))

    def serve(self):
        class TestHandler(Handler):
            pass
        TestHandler.service=self.auth
        TestHandler.buyer=BuyerService(self.auth)
        TestHandler.trade=self.trade
        TestHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),TestHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        tokens={name:self.auth.session_for_user(name)['access_token'] for name in self.users}
        def call(name,path,company=None):
            headers={'Cookie':'autolink_session='+tokens[name]} if name else {}
            if company:headers['X-Autolink-Supplier']=company
            request=urllib.request.Request(base+path,headers=headers)
            try:response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.loads(response.read())
        return call

    def test_page_validation_rejects_ambiguous_or_unbounded_input(self):
        self.assertIsNone(requested_page({}))
        self.assertEqual(requested_page({'page':['1']}),1)
        self.assertEqual(requested_page({'quotesPage':['9']},'quotesPage'),9)
        for value in ('','0','-1','01','1.0',' 1','1 ','1e2','1000001','999999999999'):
            with self.subTest(value=value),self.assertRaises(BuyerError):
                requested_page({'page':[value]})
        with self.assertRaises(BuyerError):requested_page({'page':['1','2']})
        for value in (True,0,-1,1.5,'2'):
            with self.subTest(value=value),self.assertRaises(BuyerError):
                self.trade.quote_rows(self.buyer,page=value)

    def test_buyer_quote_pages_reach_oldest_sent_quote_and_keep_scope_and_legacy_format(self):
        self.bulk()
        self.trade.create_quote(self.owner,self.inquiry['id'],{'unitPriceMinor':1,'validUntil':str(date.today())})
        with self.auth.connect() as db:
            self.clone(db,'trade_quotes',self.quote['id'],'id','QUO-ARCHIVED',archived_at=1)
            self.clone(db,'trade_quotes',self.quote['id'],'id','QUO-OTHER',buyer_id='buyer-b')
        self.assertIsInstance(self.trade.quote_rows(self.buyer),list)
        self.assertEqual(len(self.trade.quote_rows(self.buyer)),200)
        all_ids=[]
        for n in range(1,10):
            data=self.trade.quote_rows(self.buyer,page=n)
            self.assertEqual((data['total'],data['pages'],data['pageSize']),(225,9,25))
            all_ids.extend(q['id'] for q in data['items'])
            self.assertEqual(data['hasMore'],n<9)
        self.assertEqual(len(all_ids),len(set(all_ids)))
        self.assertEqual(all_ids[-1],self.quote['id'])
        self.assertEqual(self.trade.quote_rows(self.buyer,page=10)['items'],[])
        self.assertEqual(self.trade.quote_rows(self.users['buyer-b'],page=1)['total'],1)
        self.assertEqual(self.trade.buyer_quote(self.buyer,all_ids[-1])['id'],self.quote['id'])

    def test_supplier_pages_and_sales_totals_use_only_current_assignment(self):
        self.bulk()
        other=self.trade.create_inquiry(self.users['buyer-b'],{
            'listingId':self.listing,'quantity':2,'destinationCountry':'UAE'})
        self.trade.create_quote(self.owner,other['id'],{'unitPriceMinor':1,'validUntil':str(date.today()),'send':True})
        invite=self.trade.team.invite(self.owner,{'email':self.users['buyer-b']['email']})
        self.trade.team.accept(self.users['buyer-b'],invite['id'])
        sales=self.trade.team.principal(self.users['buyer-b'],self.owner['id'],approved=True)
        self.assertEqual(self.trade.quote_rows(sales,True,page=1)['total'],0)
        self.assertEqual(self.trade.supplier_inquiries(sales,page=1)['total'],0)
        self.trade.team.assign(self.owner,self.buyer['id'],{'userId':'buyer-b'})
        for method in (lambda p:self.trade.quote_rows(sales,True,page=p),lambda p:self.trade.supplier_inquiries(sales,page=p)):
            data=method(9)
            self.assertEqual((data['total'],len(data['items'])),(225,25))
            self.assertTrue(all(q['buyer_id']=='buyer-a' for q in data['items']))
        self.assertEqual(self.trade.quote_rows(self.owner,True,page=1)['total'],226)
        self.assertEqual(self.trade.supplier_inquiries(self.owner,page=1)['total'],226)
        self.assertEqual(self.trade.crm(sales,page=1)['total'],1)
        self.trade.team.assign(self.owner,self.buyer['id'],{'userId':''})
        self.assertEqual(self.trade.quote_rows(sales,True,page=9)['total'],0)
        self.assertEqual(self.trade.supplier_inquiries(sales,page=9)['items'],[])
        self.trade.team.remove(self.owner,'buyer-b')
        with self.assertRaises(BuyerError):self.trade.quote_rows(sales,True,page=1)

    def test_private_vehicle_pages_keep_status_filter_public_redaction_and_stable_order(self):
        self.bulk()
        ids=[]
        for page in range(1,10):
            data=self.trade.vehicle_rows(supplier_id=self.owner['id'],page=page)
            self.assertEqual(data['total'],225)
            ids += [v['id'] for v in data['items']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(self.trade.vehicle_rows(supplier_id=self.owner['id'],status='DRAFT',page=1)['total'],224)
        public=self.trade.vehicle_rows(public=True,page=1)
        self.assertEqual(public['total'],1)
        self.assertNotIn('review_reason',public['items'][0])
        self.assertEqual(self.trade.vehicle_rows(supplier_id='supplier-b',page=9)['total'],0)

    def test_crm_histories_have_independent_pages_and_cannot_cross_company_or_buyer(self):
        self.bulk()
        self.trade.update_crm(self.owner,self.buyer['id'],{'status':'FOLLOW_UP','note':'Original private note'})
        with self.auth.connect() as db:
            first=db.execute('SELECT id FROM supplier_crm_notes LIMIT 1').fetchone()[0]
            for n in range(124):self.clone(db,'supplier_crm_notes',first,'id',f'NOTE-PAGE-{n:04}')
        data=self.trade.crm_detail(self.owner,self.buyer['id'],{'notesPage':5,'inquiriesPage':9,'quotesPage':9})
        self.assertEqual((data['notes']['total'],data['notes']['page']),(125,5))
        self.assertEqual((data['inquiries']['total'],len(data['inquiries']['items'])),(225,25))
        self.assertEqual(data['quotes']['items'][-1]['id'],self.quote['id'])
        with self.assertRaises(BuyerError):self.trade.crm_detail(self.users['supplier-b'],self.buyer['id'],{'notesPage':1})
        with self.assertRaises(BuyerError):self.trade.crm_detail(self.owner,'buyer-b',{'notesPage':1})

    def test_notification_pages_and_totals_are_owned_and_do_not_mark_read(self):
        with self.auth.connect() as db:
            first=db.execute("SELECT id FROM account_notifications WHERE user_id='buyer-a' LIMIT 1").fetchone()[0]
            for n in range(224):self.clone(db,'account_notifications',first,'id',f'NOTICE-PAGE-{n:04}')
            self.clone(db,'account_notifications',first,'id','NOTICE-OTHER',user_id='buyer-b')
        self.assertEqual(len(self.trade.platform.notifications(self.buyer)),100)
        data=self.trade.platform.notifications(self.buyer,page=9)
        self.assertEqual((data['total'],len(data['items'])),(225,25))
        self.assertTrue(all(row['read_at'] is None for row in data['items']))
        self.assertEqual(self.trade.platform.notifications(self.users['buyer-b'],page=1)['total'],1)
        self.assertEqual(self.trade.platform.unread_notification_count(self.buyer),225)

    def test_admin_pages_and_keyed_details_reach_records_beyond_legacy_cap(self):
        self.bulk()
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET updated_at=0 WHERE supplier_id='supplier-a'")
            for n in range(224):
                ident=f'supplier-page-{n:04}'
                self.clone(db,'users','supplier-a','id',ident,email=ident+'@example.com')
                self.clone(db,'supplier_profiles','supplier-a','user_id',ident)
                self.clone(db,'supplier_applications','supplier-a','supplier_id',ident,updated_at=int(time.time()))
        call=self.serve()
        for path in ('suppliers','vehicles','users','support','reports','audit'):
            with self.subTest(path=path):
                status,result=call('admin','/autolink/admin/'+path+'?page=9')
                self.assertEqual(status,200);self.assertIsInstance(result['data']['items'],list)
                self.assertEqual(result['data']['page'],9)
                self.assertEqual(call('buyer-a','/autolink/admin/'+path+'?page=9')[0],403)
        legacy=call('admin','/autolink/admin/suppliers')[1]['data']
        self.assertEqual(len(legacy),200)
        self.assertNotIn('supplier-a',{row['supplier_id'] for row in legacy})
        self.assertEqual(call('admin','/autolink/admin/suppliers/supplier-a')[1]['data']['supplier_id'],'supplier-a')
        self.assertEqual(call('admin','/autolink/admin/vehicles/'+self.listing)[1]['data']['id'],self.listing)
        for path in ('suppliers/supplier-a','vehicles/'+self.listing):
            self.assertEqual(call('buyer-a','/autolink/admin/'+path)[0],403)
        self.assertEqual(call('admin','/autolink/admin/suppliers/missing')[0],404)
        self.assertEqual(call('admin','/autolink/admin/vehicles/missing')[0],404)

    def test_http_page_input_and_authenticated_company_scopes(self):
        self.bulk();call=self.serve()
        paths=[('buyer-a','/autolink/buyer/quotes'),('buyer-a','/autolink/notifications'),
               ('supplier-a','/autolink/supplier/inquiries'),('supplier-a','/autolink/supplier/quotes'),
               ('supplier-a','/autolink/supplier/vehicles'),('admin','/autolink/admin/vehicles')]
        for who,path in paths:
            for bad in ('page=0','page=','page=2&page=3','page=nan','page=1000001'):
                with self.subTest(path=path,bad=bad):self.assertEqual(call(who,path+'?'+bad)[0],400)
            self.assertEqual(call(who,path+'?page=9')[0],200)
            self.assertEqual(call(None,path+'?page=9')[0],401)
        self.assertEqual(call('supplier-b','/autolink/supplier/inquiries?page=9',company='supplier-a')[0],404)

    def test_buyer_inquiry_pages_filters_unicode_literals_and_ownership(self):
        self.bulk();service=BuyerService(self.auth)
        with self.auth.connect() as db:
            db.execute("UPDATE users SET company_name='Поставщик ÄUTÓ 中文 100%' WHERE id='supplier-a'")
            self.clone(db,'buyer_inquiries',self.inquiry['id'],'id','INQ-OTHER-BUYER',buyer_id='buyer-b')
        ids=[]
        for n in range(1,10):
            data=service.inquiry_rows(self.buyer,page=n)
            self.assertEqual((data['total'],data['pages'],len(data['items'])),(225,9,25))
            ids.extend(row['id'] for row in data['items'])
        self.assertEqual(len(set(ids)),225)
        self.assertEqual(len(service.inquiry_rows(self.buyer)),225)
        self.assertEqual(service.inquiry_rows(self.users['buyer-b'],page=1)['total'],1)
        self.assertEqual(service.inquiry_rows(self.buyer,page=1,status='CLOSED')['total'],224)
        self.assertEqual(service.inquiry_rows(self.buyer,page=1,status='QUOTED')['total'],1)
        for keyword in ('пОСТАВЩИК','äutó','中文','100%','Zeekr 9X'):
            with self.subTest(keyword=keyword):self.assertEqual(service.inquiry_rows(self.buyer,page=9,keyword=keyword)['total'],225)
        for keyword in ("%' OR 1=1 --",'supplier-b','_'):
            self.assertEqual(service.inquiry_rows(self.buyer,page=1,keyword=keyword)['total'],0)
        exact=service.inquiry_rows(self.buyer,page=1,keyword='INQ-PAGE-0000')
        self.assertEqual(exact['total'],1);self.assertEqual(exact['items'][0]['id'],'INQ-PAGE-0000')
        self.assertEqual(service.inquiry_rows(self.buyer,self.inquiry['id'],page=9)[0]['id'],self.inquiry['id'])

    def test_buyer_overview_only_decorates_five_recent_inquiries(self):
        from unittest.mock import patch
        self.bulk();service=BuyerService(self.auth)
        with patch.object(service.catalog,'get',wraps=service.catalog.get) as model_read:
            result=service.overview(self.buyer)
        self.assertEqual(len(result['recentInquiries']),5)
        self.assertEqual(model_read.call_count,5)
        self.assertEqual(result['counts']['quotes'],225)
        self.assertEqual(result['counts']['activeInquiries'],1)

    def test_buyer_request_pages_and_keyed_mutation_preserve_all_history(self):
        service=BuyerService(self.auth)
        original=service.create_request(self.buyer,{'title':'Original draft','quantity':2})
        with self.auth.connect() as db:
            for n in range(224):self.clone(db,'buyer_requests',original['id'],'id',f'REQ-PAGE-{n:04}')
            self.clone(db,'buyer_requests',original['id'],'id','REQ-OTHER',buyer_id='buyer-b')
            db.execute('UPDATE buyer_requests SET updated_at=0 WHERE id=?',(original['id'],))
        rows=[]
        for n in range(1,10):
            result=service.requests(self.buyer,page=n);self.assertEqual(result['total'],225)
            rows.extend(row['id'] for row in result['items'])
        self.assertEqual(len(set(rows)),225);self.assertEqual(rows[-1],original['id'])
        self.assertEqual(service.requests(self.users['buyer-b'],page=1)['total'],1)
        self.assertEqual(len(service.requests(self.buyer)),225)
        with self.assertRaises(BuyerError):service.update_request_status(self.users['buyer-b'],original['id'],{'status':'CLOSED'})
        self.assertEqual(service.update_request_status(self.buyer,original['id'],{'status':'CLOSED'})['status'],'CLOSED')
        self.assertEqual(len(service.requests(self.buyer)),225)

    def test_shared_request_pages_require_publication_consent_and_live_buyer(self):
        service=BuyerService(self.auth)
        original=service.create_request(self.buyer,{'title':'Published request','quantity':2,'status':'PUBLISHED','publishConsent':True,'destinationCountry':'Kenya'})
        with self.auth.connect() as db:
            for n in range(224):self.clone(db,'buyer_requests',original['id'],'id',f'REQ-SHARED-{n:04}')
            self.clone(db,'buyer_requests',original['id'],'id','REQ-PRIVATE',distribution_consent=0)
            self.clone(db,'buyer_requests',original['id'],'id','REQ-DRAFT',status='DRAFT')
            self.clone(db,'buyer_requests',original['id'],'id','REQ-CLOSED',status='CLOSED')
            self.clone(db,'buyer_requests',original['id'],'id','REQ-DELETED-BUYER',buyer_id='buyer-b')
            db.execute("UPDATE users SET deleted_at=1 WHERE id='buyer-b'")
            db.execute('UPDATE buyer_requests SET published_at=0 WHERE id=?',(original['id'],))
        ids=[]
        for n in range(1,10):
            result=self.trade.buying_requests(self.owner,page=n)
            self.assertEqual(result['total'],225)
            self.assertEqual(len(result['items']),25)
            for row in result['items']:
                self.assertNotIn('buyer_id',row);self.assertNotIn('email',row);self.assertNotIn('company_name',row)
            ids.extend(row['id'] for row in result['items'])
        self.assertEqual(len(set(ids)),225);self.assertEqual(ids[-1],original['id'])
        self.assertEqual(len(self.trade.buying_requests(self.owner)),100)
        self.assertEqual(self.trade.buying_requests(self.owner,original['id'],page=9)[0]['id'],original['id'])
        call=self.serve();self.assertEqual(call('buyer-a','/autolink/supplier/buying-requests?page=9')[0],403)
        self.assertEqual(call('supplier-a','/autolink/supplier/buying-requests?page=9')[1]['data']['total'],225)
        with self.auth.connect() as db:db.execute("UPDATE users SET email_verified_at=NULL WHERE id='buyer-a'")
        self.assertEqual(self.trade.buying_requests(self.owner,page=9)['total'],0)

    def test_inquiry_filter_input_and_new_collection_page_validation(self):
        call=self.serve()
        for query in ('status=WRONG','status=CLOSED&status=QUOTED','keyword=one&keyword=two','keyword='+('a'*161),'page=0','page=1&page=2'):
            self.assertEqual(call('buyer-a','/autolink/buyer/inquiries?'+query)[0],400)
        self.assertEqual(call('buyer-a','/autolink/buyer/inquiries?page=1&status=ALL')[1]['data']['total'],1)
        for name,path in [('buyer-a','/autolink/buyer/requests'),('supplier-a','/autolink/supplier/buying-requests')]:
            self.assertEqual(call(name,path+'?page=0')[0],400)
            self.assertEqual(call(name,path+'?page=1')[0],200)
            self.assertEqual(call(None,path+'?page=1')[0],401)
