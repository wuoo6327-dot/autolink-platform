"""Buying requests share only with consent and reuse real inquiry/quote persistence."""
import unittest
from datetime import date
import test_trade
from buyer_service import BuyerError,BuyerService

class BuyingRequestFlowTests(unittest.TestCase):
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        self.buyer=BuyerService(self.auth)
    approved_vehicle=test_trade.TradeFlowTests.approved_vehicle

    def request(self,**extra):
        return self.buyer.create_request(self.users['buyer-a'],{'title':'Monjaro sourcing request','vehicleId':'zeekr-9x-2026',
            'quantity':2,'destinationCountry':'Saudi Arabia','destinationPort':'Jeddah','tradeTerm':'FOB',
            'status':'PUBLISHED','publishConsent':True,**extra})

    def response(self,listing,**extra):
        return {'listingId':listing,'unitPriceMinor':1850000,'validUntil':str(date.today()),**extra}

    def test_publish_requires_verified_email_and_explicit_sharing(self):
        self.approved_vehicle()
        with self.assertRaises(BuyerError):self.request(publishConsent=False)
        draft=self.request(status='DRAFT',publishConsent=False)
        with self.auth.connect() as db:
            db.execute("UPDATE buyer_requests SET status='PUBLISHED' WHERE id=?",(draft['id'],))
        self.assertEqual(self.trade.buying_requests(self.users['supplier-a']),[])
        with self.assertRaises(BuyerError):self.buyer.update_request_status({**dict(self.users['buyer-a']),'email_verified_at':None},draft['id'],{'status':'PUBLISHED','publishConsent':True})
        self.buyer.update_request_status(self.users['buyer-a'],draft['id'],{'status':'PUBLISHED','publishConsent':True})
        shared=self.trade.buying_requests(self.users['supplier-a'])[0]
        self.assertNotIn('buyer_id',shared);self.assertNotIn('email',shared)
        self.assertNotIn('company_name',shared)

    def test_supplier_response_reaches_buyer_quote_and_crm_atomically(self):
        listing=self.approved_vehicle();request=self.request()
        result=self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing))
        quotes=self.trade.quote_rows(self.users['buyer-a']);self.assertEqual(quotes[0]['id'],result['quote']['id'])
        self.assertEqual(quotes[0]['status'],'SENT');self.assertEqual(quotes[0]['total_price_minor'],3700000)
        inquiry=self.trade.buyer_inquiry(self.users['buyer-a'],result['inquiryId'])
        self.assertEqual(inquiry['request_id'],request['id']);self.assertEqual(inquiry['status'],'QUOTED')
        opened=self.trade.supplier_inquiries(self.users['supplier-a'],result['inquiryId'])[0]
        self.assertEqual(opened['status'],'QUOTED');self.assertIsNone(opened['viewed_at'])
        self.trade.update_inquiry(self.users['supplier-a'],result['inquiryId'],{'status':'VIEWED'})
        self.assertIsNotNone(self.trade.supplier_inquiries(self.users['supplier-a'],result['inquiryId'])[0]['viewed_at'])
        self.assertEqual(self.trade.buyer_inquiry(self.users['buyer-a'],result['inquiryId'])['status'],'QUOTED')
        self.assertEqual(self.trade.crm(self.users['supplier-a'])[0]['buyer_id'],'buyer-a')
        self.assertEqual(self.buyer.requests(self.users['buyer-a'])[0]['response_count'],1)
        self.assertEqual(self.trade.platform.notifications(self.users['buyer-a'])[0]['event'],'NEW_QUOTE')
        self.assertEqual(self.trade.buyer_quote(self.users['buyer-a'],quotes[0]['id'],'ACCEPTED')['status'],'ACCEPTED')
        with self.assertRaises(BuyerError):self.trade.buyer_quote(self.users['buyer-b'],quotes[0]['id'])

    def test_cross_supplier_listing_and_repeat_response_are_rejected(self):
        listing=self.approved_vehicle();self.approved_vehicle('supplier-b');request=self.request()
        with self.assertRaises(BuyerError) as raised:self.trade.respond_to_request(self.users['supplier-b'],request['id'],self.response(listing))
        self.assertEqual(raised.exception.status,404)
        self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing))
        with self.assertRaises(BuyerError) as raised:self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing))
        self.assertEqual(raised.exception.status,409)
        self.assertEqual(len(self.trade.quote_rows(self.users['buyer-a'])),1)

    def test_invalid_quote_leaves_no_inquiry_response_or_notification(self):
        listing=self.approved_vehicle();request=self.request()
        with self.assertRaises(BuyerError):self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing,unitPriceMinor=-1))
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM buyer_inquiries').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM buyer_request_responses').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM trade_quotes').fetchone()[0],0)
        self.assertEqual(self.trade.platform.notifications(self.users['buyer-a']),[])

    def test_close_is_buyer_scoped_and_preserves_previous_response(self):
        listing=self.approved_vehicle();request=self.request()
        with self.assertRaises(BuyerError) as raised:self.buyer.update_request_status(self.users['buyer-b'],request['id'],{'status':'CLOSED'})
        self.assertEqual(raised.exception.status,404)
        self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing))
        self.buyer.update_request_status(self.users['buyer-a'],request['id'],{'status':'CLOSED'})
        self.assertEqual(self.trade.buying_requests(self.users['supplier-a']),[])
        self.assertEqual(len(self.trade.quote_rows(self.users['buyer-a'])),1)
        with self.assertRaises(BuyerError):self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing))
        self.assertEqual(self.buyer.requests(self.users['buyer-b']),[])

    def test_published_request_rate_limit_and_model_matching(self):
        listing=self.approved_vehicle()
        request=self.request(vehicleId='geely-monjaro-2026')
        with self.assertRaises(BuyerError):self.trade.respond_to_request(self.users['supplier-a'],request['id'],self.response(listing))
        self.request(title='Second request');self.request(title='Third request')
        with self.assertRaises(BuyerError) as raised:self.request(title='Fourth request')
        self.assertEqual(raised.exception.status,429)

if __name__=='__main__':unittest.main()
