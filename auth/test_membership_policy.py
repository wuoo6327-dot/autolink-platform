"""HTTP access rules and transactional free-account lifetime allowance."""
import os
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch
import test_trade
import test_pagination
from buyer_service import BuyerError


class MembershipPolicyTests(unittest.TestCase):
    approved_vehicle=test_trade.TradeFlowTests.approved_vehicle
    serve=test_pagination.BusinessPaginationTests.serve

    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        flag=patch.dict(os.environ,{'MEMBERSHIP_RESTRICTIONS':'true'})
        flag.start();self.addCleanup(flag.stop)
        self.buyer=self.users['buyer-a'];self.owner=self.users['supplier-a']
        self.listing=self.approved_vehicle()
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_profiles SET public_contact_enabled=1,public_contact_email='supplier-a@example.com' WHERE user_id='supplier-a'")

    def grant(self,plan='monthly',start=None,end=None):
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("DELETE FROM buyer_memberships WHERE user_id='buyer-a'")
            db.execute("INSERT INTO buyer_memberships(id,user_id,plan,status,start_at,end_at) VALUES ('member','buyer-a',?,'ACTIVE',?,?)",(plan,now-1 if start is None else start,now+3600 if end is None else end))

    def inquiry(self,buyer=None):
        return self.trade.create_inquiry(buyer or self.buyer,{'listingId':self.listing,'quantity':2,'destinationCountry':'Kenya'})

    def test_public_free_prices_contacts_filter_probes_and_supplier_owner_scope(self):
        call=self.serve()
        for who in (None,'buyer-a','buyer-b','supplier-b'):
            status,result=call(who,'/autolink/public/vehicles/'+self.listing)
            self.assertEqual(status,200);self.assertIsNone(result['data']['price_minor'])
            self.assertTrue(result['data']['priceLocked'])
            status,result=call(who,'/autolink/public/suppliers/supplier-a')
            self.assertEqual(status,200);self.assertIsNone(result['data']['contact'])
            self.assertNotIn('supplier-a@example.com',json.dumps(result))
            for query in ('minPriceMinor=1890000','maxPriceMinor=1890000','sort=price_asc','sort=price_desc'):
                self.assertEqual(call(who,'/autolink/public/vehicles?'+query)[0],403)
        status,result=call('supplier-a','/autolink/supplier/vehicles')
        self.assertEqual(status,200);self.assertEqual(result['data'][0]['price_minor'],1890000)
        self.assertIn(call('supplier-b','/autolink/supplier/vehicles/'+self.listing)[0],(403,404))

    def test_three_tiers_equal_expiry_future_and_current_user_checked(self):
        call=self.serve();outcomes=[]
        for plan in ('monthly','quarterly','annual'):
            self.grant(plan)
            self.assertEqual(call('buyer-a','/autolink/public/vehicles/'+self.listing)[1]['data']['price_minor'],1890000)
            self.assertEqual(call('buyer-a','/autolink/public/vehicles?minPriceMinor=1')[0],200)
            self.assertEqual(call('buyer-a','/autolink/public/suppliers/supplier-a')[1]['data']['contact']['email'],'supplier-a@example.com')
            e=self.trade.platform.entitlements(self.buyer)
            outcomes.append((e['viewVehiclePrices'],e['viewSupplierContacts'],e['inquiriesPerDay']))
        self.assertEqual(outcomes,[(True,True,30)]*3)
        now=int(time.time())
        for start,end in ((now-20,now-1),(now+100,now+200)):
            self.grant(start=start,end=end)
            self.assertFalse(self.trade.platform.can_view_member_data(self.buyer))
            self.assertFalse(self.trade.platform.entitlements(self.buyer)['membershipActive'])
        self.grant()
        with self.auth.connect() as db:db.execute("UPDATE users SET status='SUSPENDED' WHERE id='buyer-a'")
        self.assertFalse(self.trade.platform.can_view_member_data(self.buyer))
        self.assertTrue(self.trade.platform.can_view_member_data(self.users['admin']))

    def test_one_lifetime_inquiry_survives_closing_old_age_and_event_cleanup(self):
        first=self.inquiry()
        with self.auth.connect() as db:
            db.execute("UPDATE buyer_inquiries SET status='CLOSED',created_at=1 WHERE id=?",(first['id'],))
            db.execute('DELETE FROM inquiry_rate_events')
        with self.assertRaises(BuyerError) as exc:self.inquiry()
        self.assertEqual(exc.exception.status,429)
        self.inquiry(self.users['buyer-b'])
        self.grant();self.inquiry()
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT count(*) FROM buyer_inquiries WHERE buyer_id='buyer-a'").fetchone()[0],2)
        self.grant(end=int(time.time())-1)
        with self.assertRaises(BuyerError):self.inquiry()

    def test_concurrent_free_submissions_commit_one(self):
        def submit(_):
            try:self.inquiry();return 200
            except BuyerError as exc:return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:outcomes=sorted(pool.map(submit,range(2)))
        self.assertEqual(outcomes,[200,429])
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM buyer_inquiries WHERE buyer_id='buyer-a'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM inquiry_rate_events WHERE buyer_id='buyer-a'").fetchone()[0],1)

    def test_quotes_history_contact_masked_no_blind_accept_and_no_history_loss(self):
        call=self.serve();inquiry=self.inquiry()
        quote=self.trade.create_quote(self.owner,inquiry['id'],{'unitPriceMinor':1890000,'validUntil':str(date.today()),'send':True})
        for path in ('/autolink/buyer/quotes','/autolink/buyer/quotes/'+quote['id'],'/autolink/buyer/overview'):
            status,result=call('buyer-a',path);self.assertEqual(status,200)
            for value in ('1890000','3780000','supplier-a@example.com'):self.assertNotIn(value,json.dumps(result))
        with self.assertRaises(BuyerError) as exc:self.trade.buyer_quote(self.buyer,quote['id'],'ACCEPTED')
        self.assertEqual(exc.exception.status,403)
        self.assertEqual(call('buyer-b','/autolink/buyer/quotes/'+quote['id'])[0],404)
        self.grant()
        self.assertEqual(call('buyer-a','/autolink/buyer/quotes/'+quote['id'])[1]['data']['total_price_minor'],3780000)
        self.assertEqual(self.trade.buyer_quote(self.buyer,quote['id'],'ACCEPTED')['status'],'ACCEPTED')
        self.grant(end=int(time.time())-1)
        result=call('buyer-a','/autolink/buyer/quotes/'+quote['id'])[1]['data']
        self.assertEqual(result['status'],'ACCEPTED');self.assertIsNone(result['total_price_minor'])
