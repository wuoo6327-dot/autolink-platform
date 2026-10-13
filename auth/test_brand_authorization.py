"""Private proof and scope gates for supplier-specific brand authorization."""

import base64
from datetime import date, timedelta
import unittest

from buyer_service import BuyerError
from seo_service import PublicSEOService
import test_trade


class BrandAuthorizationTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp
    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle
    add_application_evidence = test_trade.TradeFlowTests.add_application_evidence
    sign_company = test_trade.TradeFlowTests.sign_company
    record_price = test_trade.TradeFlowTests.record_price
    image_body = test_trade.TradeFlowTests.image_body

    def claim(self, document_id):
        return {
            'brandId':'zeekr', 'authorizationType':'AUTHORIZED_EXPORTER',
            'holderLegalName':'China Export Co', 'issuerLegalName':'Issuer Test Ltd',
            'businessScope':'New passenger vehicles only', 'territories':'United Arab Emirates',
            'authorizationChain':'Direct appointment by issuer; reviewer must validate issuer authority.',
            'validFrom':date.today().isoformat(),
            'validUntil':(date.today()+timedelta(days=60)).isoformat(),
            'evidenceDocumentId':document_id,
        }

    def evidence(self, supplier='supplier-a'):
        return self.trade.add_document(self.users[supplier], {
            'kind':'BRAND_AUTHORIZATION','filename':'private-proof.pdf',
            'contentType':'application/pdf',
            'base64':base64.b64encode(b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF').decode(),
        })['id']

    def test_no_company_or_listing_review_grants_brand_authorization(self):
        self.approved_vehicle()
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])
        public=self.trade.public_supplier('supplier-a')
        self.assertIsNotNone(public)
        self.assertEqual(public['brandAuthorizations'], [])

    def test_private_proof_review_expiry_and_revocation(self):
        with self.assertRaises(BuyerError):
            self.evidence()
        self.approved_vehicle()
        document_id=self.evidence()
        with self.assertRaises(BuyerError):
            self.trade.document_bytes(document_id,self.users['buyer-a'])
        with self.assertRaises(BuyerError):
            self.trade.brand_authorizations.submit(self.users['supplier-a'],
                {**self.claim(document_id),'holderLegalName':'Different company'})
        with self.assertRaises(BuyerError):
            self.trade.brand_authorizations.submit(self.users['supplier-b'],self.claim(document_id))
        claim=self.trade.brand_authorizations.submit(self.users['supplier-a'],self.claim(document_id))
        self.assertEqual(claim['status'],'PENDING')
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])
        with self.assertRaises(BuyerError):
            self.trade.brand_authorizations.submit(self.users['supplier-a'],self.claim(document_id))
        with self.assertRaises(BuyerError):
            self.trade.brand_authorizations.review(self.users['admin'],claim['id'],
                {'decision':'APPROVED'})
        self.trade.brand_authorizations.review(self.users['admin'],claim['id'],
            {'decision':'APPROVED','evidenceChecked':True})
        visible=self.trade.brand_authorizations.rows('supplier-a', public=True)
        self.assertEqual(len(visible),1)
        self.assertEqual(visible[0]['brand_name'],'Zeekr')
        self.assertNotIn('evidence_document_id',visible[0])
        html=PublicSEOService(self.trade).render('/trade/suppliers/supplier-a')[1].decode()
        self.assertIn('Reviewed supplier brand authorizations',html)
        self.assertIn('United Arab Emirates',html)
        self.assertNotIn('Issuer Test Ltd',html)
        self.assertNotIn('private-proof.pdf',html)
        with self.auth.connect() as db:
            db.execute('UPDATE supplier_brand_authorizations SET valid_until=? WHERE id=?',
                ((date.today()-timedelta(days=1)).isoformat(),claim['id']))
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])
        with self.auth.connect() as db:
            db.execute('UPDATE supplier_brand_authorizations SET valid_until=? WHERE id=?',
                ((date.today()+timedelta(days=60)).isoformat(),claim['id']))
        with self.assertRaises(BuyerError):
            self.trade.brand_authorizations.review(self.users['admin'],claim['id'],
                {'decision':'REVOKED'})
        self.trade.brand_authorizations.review(self.users['admin'],claim['id'],
            {'decision':'REVOKED','reason':'Issuer withdrew authorization'})
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])
        self.assertNotIn('Reviewed supplier brand authorizations',
            PublicSEOService(self.trade).render('/trade/suppliers/supplier-a')[1].decode())

    def test_inactive_brand_and_company_hide_reviewed_claim(self):
        self.approved_vehicle()
        claim=self.trade.brand_authorizations.submit(self.users['supplier-a'],self.claim(self.evidence()))
        self.trade.brand_authorizations.review(self.users['admin'],claim['id'],
            {'decision':'APPROVED','evidenceChecked':True})
        with self.auth.connect() as db:
            db.execute("UPDATE catalog_brands SET active=0 WHERE id='zeekr'")
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])
        with self.auth.connect() as db:
            db.execute("UPDATE catalog_brands SET active=1 WHERE id='zeekr'")
            db.execute("UPDATE supplier_applications SET status='SUSPENDED' WHERE supplier_id='supplier-a'")
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET status='APPROVED' WHERE supplier_id='supplier-a'")
            db.execute("UPDATE users SET company_name='Renamed supplier' WHERE id='supplier-a'")
        self.assertEqual(self.trade.brand_authorizations.rows('supplier-a', public=True), [])


if __name__=='__main__':
    unittest.main()
