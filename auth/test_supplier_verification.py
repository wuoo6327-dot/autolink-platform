"""Evidence is enforced by the server and remains private across suppliers."""
import unittest
import base64
from datetime import date, timedelta
import test_trade
from trade_service import TradeService
from buyer_service import BuyerError

class SupplierVerificationTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp
    add_application_evidence = test_trade.TradeFlowTests.add_application_evidence

    def form(self):
        return {'companyName':'QA company','registrationNo':'QA-REG','address':'QA legal address',
                'country':'China','contactName':'QA owner','contactPhone':'123',
                'premisesAddress':'QA operating warehouse','inventoryCount':0,'inventoryBasis':'AUTHORIZED',
                'inventoryAsOf':date.today().isoformat()}

    def draft(self):
        owner = self.users['supplier-a']
        self.trade.save_application(owner, self.form())
        self.trade.add_document(owner, {'kind':'BUSINESS_LICENSE','filename':'qa-license.pdf','contentType':'application/pdf',
            'base64':base64.b64encode(b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF').decode()})
        test_trade.TradeFlowTests.sign_company(self, owner)
        return owner

    def test_required_fields_and_both_photo_categories_are_enforced(self):
        owner=self.draft()
        with self.assertRaises(BuyerError) as error:
            self.trade.save_application(owner, {**self.form(),'premisesAddress':'','submit':True})
        self.assertEqual(error.exception.status,409)
        with self.assertRaises(BuyerError):self.trade.save_application(owner, {**self.form(),'submit':True})
        self.add_application_evidence(owner)
        app=self.trade.save_application(owner,{**self.form(),'submit':True})
        self.assertEqual(app['status'],'PENDING')
        self.assertEqual(app['inventory_count'],0)
        self.assertEqual(app['evidence_version'],2)
        self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'APPROVED'})
        public=self.trade.public_supplier(owner['id'])
        for key in ('premises_address','inventory_count','inventory_basis','inventory_as_of'):
            self.assertNotIn(key,public)

    def test_photo_decode_mime_size_and_private_access(self):
        owner=self.draft()
        pdf={'kind':'PREMISES_PHOTO','filename':'fake.pdf','contentType':'application/pdf',
            'base64':base64.b64encode(b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF').decode()}
        with self.assertRaises(BuyerError):self.trade.add_document(owner,pdf)
        fake={'kind':'INVENTORY_PHOTO','filename':'fake.png','contentType':'image/png',
            'base64':base64.b64encode(b'\x89PNG\r\n\x1a\n'+b'garbage'*50).decode()}
        with self.assertRaises(BuyerError):self.trade.add_document(owner,fake)
        self.assertEqual(len(self.trade.documents(owner['id'])),1)
        self.add_application_evidence(owner)
        doc=next(d for d in self.trade.documents(owner['id']) if d['kind']=='INVENTORY_PHOTO')
        self.assertNotIn('stored_name',doc)
        self.assertEqual(doc['content_type'],'image/jpeg')
        self.assertTrue(self.trade.document_bytes(doc['id'],owner)['data'].startswith(b'\xff\xd8'))
        self.assertTrue(self.trade.document_bytes(doc['id'],self.users['admin'])['data'])
        for key in ('supplier-b','buyer-a'):
            with self.assertRaises(BuyerError) as error:self.trade.document_bytes(doc['id'],self.users[key])
            self.assertEqual(error.exception.status,404)

    def test_approval_rechecks_evidence_and_preserves_legacy_approvals(self):
        owner=self.draft();self.add_application_evidence(owner)
        self.trade.save_application(owner,{**self.form(),'submit':True})
        with self.auth.connect() as db:
            db.execute("DELETE FROM supplier_documents WHERE supplier_id=? AND kind='INVENTORY_PHOTO'",(owner['id'],))
        with self.assertRaises(BuyerError):self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'APPROVED'})
        with self.auth.connect() as db:
            db.execute('UPDATE supplier_applications SET evidence_version=1,status=\'APPROVED\' WHERE supplier_id=?',(owner['id'],))
        self.trade.review_supplier(self.users['admin'],owner['id'],{'decision':'APPROVED'})
        TradeService(self.auth)
        self.assertEqual(self.trade.application(owner)['status'],'APPROVED')
        self.assertEqual(self.trade.application(owner)['evidence_version'],1)

    def test_invalid_stock_metadata_and_locked_application(self):
        owner=self.draft()
        for key,value in [('inventoryCount',True),('inventoryCount',-1),('inventoryCount',1.5),('inventoryBasis','FAKE'),('inventoryAsOf',(date.today()+timedelta(days=1)).isoformat())]:
            with self.assertRaises(BuyerError) as error:self.trade.save_application(owner,{**self.form(),key:value})
            self.assertEqual(error.exception.status,400)
        self.add_application_evidence(owner)
        self.trade.save_application(owner,{**self.form(),'submit':True})
        with self.assertRaises(BuyerError):self.trade.save_application(owner,{**self.form(),'inventoryCount':999})

if __name__=='__main__':unittest.main()
