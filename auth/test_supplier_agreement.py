"""Isolated synthetic confirmations: persistence, version checks and no promotion."""
import unittest
import hashlib
import test_trade
from buyer_service import BuyerError
from trade_service import TradeService


class SupplierAgreementTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp

    def draft(self, key='supplier-a'):
        owner = self.users[key]
        self.trade.save_application(owner, {'companyName':'Synthetic QA company',
            'registrationNo':'QA-REG','address':'Synthetic QA address',
            'country':'China','contactName':'QA owner','contactPhone':'123'})
        return owner

    def payload(self):
        document = self.trade.agreement.document
        return {'version':document['version'],'bodySha256':document['bodySha256'],
                'consent':True,'privacyAcknowledged':True,'authorized':True}

    def test_persists_single_confirmation_with_immutable_text_and_no_approval(self):
        owner = self.draft()
        result = self.trade.agreement.confirm(owner,self.payload())
        again = self.trade.agreement.confirm(owner,self.payload())
        self.assertEqual(result['confirmation']['id'],again['confirmation']['id'])
        self.assertEqual(self.trade.application(owner)['status'],'DRAFT')
        self.assertIsNone(self.trade.public_supplier(owner['id']))
        with self.auth.connect() as db:
            row = db.execute('SELECT * FROM supplier_agreement_confirmations').fetchone()
            self.assertEqual(row['confirmed_email'],owner['email'])
            self.assertEqual(row['company_name'],'Synthetic QA company')
            self.assertEqual(row['verification_method'],'VERIFIED_EMAIL_SESSION')
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_agreement_confirmations').fetchone()[0],1)
            version = db.execute('SELECT * FROM supplier_agreement_versions').fetchone()
            self.assertEqual(hashlib.sha256(version['body'].encode()).hexdigest(),self.payload()['bodySha256'])
            self.assertEqual(version['document_status'],'FINAL')
            self.assertEqual(db.execute("SELECT count(*) FROM trade_audit WHERE action='SUPPLIER_AGREEMENT_CONFIRMED'").fetchone()[0],1)
        TradeService(self.auth)
        self.assertEqual(self.trade.application(owner)['agreementConfirmation']['id'],row['id'])

    def test_all_consents_and_exact_version_are_required(self):
        owner = self.draft()
        for key,value in [('consent',False),('consent',1),('privacyAcknowledged',False),
                          ('authorized',False),('version','tampered'),('bodySha256','0'*64)]:
            with self.assertRaises(BuyerError):
                self.trade.agreement.confirm(owner,{**self.payload(),key:value})
        with self.assertRaises(BuyerError):
            self.trade.agreement.confirm(owner,{**self.payload(),'supplierId':'supplier-b'})
        self.assertIsNone(self.trade.agreement.current(owner)['confirmation'])

    def test_owner_verified_account_and_company_details_are_required(self):
        owner=self.users['supplier-a']
        with self.assertRaises(BuyerError):self.trade.agreement.confirm(owner,self.payload())
        self.draft()
        with self.assertRaises(BuyerError):
            self.trade.agreement.confirm({**owner,'supplier_role':'SALES'},self.payload())
        with self.assertRaises(BuyerError):
            self.trade.agreement.confirm({**owner,'actor_user_id':'supplier-b'},self.payload())
        with self.auth.connect() as db:db.execute('UPDATE users SET email_verified_at=NULL WHERE id=?',(owner['id'],))
        with self.assertRaises(BuyerError):self.trade.agreement.confirm(owner,self.payload())

    def test_other_company_cannot_read_or_replace_confirmation(self):
        owner=self.draft();other=self.draft('supplier-b')
        original=self.trade.agreement.confirm(owner,self.payload())
        self.assertIsNone(self.trade.agreement.current(other)['confirmation'])
        self.trade.agreement.confirm(other,self.payload())
        self.assertEqual(self.trade.agreement.current(owner)['confirmation'],original['confirmation'])
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_agreement_versions SET body='tampered' WHERE version=?",(self.payload()['version'],))
        with self.assertRaises(RuntimeError):TradeService(self.auth)


if __name__ == '__main__':unittest.main()
