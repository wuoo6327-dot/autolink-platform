"""Legacy public APIs: temporary fixtures only, never production identities."""
import json
from http.server import ThreadingHTTPServer
import threading
import urllib.request
import urllib.error
from app import Handler
from buyer_service import BuyerService
from email_auth import EmailAuthService
from seo_service import PublicSEOService
import test_trade
import unittest

class LegacyCompatibilityTests(unittest.TestCase):
    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        Handler.service=self.auth;Handler.trade=self.trade;Handler.buyer=BuyerService(self.auth)
        Handler.platform=self.trade.platform;Handler.email_auth=EmailAuthService(self.auth)
        Handler.seo=PublicSEOService(self.trade)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def get(self,path,method='GET'):
        with urllib.request.urlopen(urllib.request.Request(self.base+path,method=method)) as r:return r, r.read()
    def snapshot(self):
        with self.auth.connect() as db:return '\n'.join(db.iterdump())
    def test_empty_directory_has_no_fake_merchants(self):
        before=self.snapshot();r,b=self.get('/autolink/merchants')
        self.assertEqual(json.loads(b)['data'],[]);self.assertEqual(r.status,200)
        self.assertEqual(before,self.snapshot())
    def test_directory_uses_same_publication_gate_and_excludes_contacts(self):
        self.approved_vehicle()
        with self.auth.connect() as db:db.execute("UPDATE supplier_profiles SET public_contact_enabled=1,public_contact_email='private@example.invalid' WHERE user_id='supplier-a'")
        before=self.snapshot();r,b=self.get('/autolink/merchants');rows=json.loads(b)['data']
        self.assertEqual([row['id'] for row in rows],[row['id'] for row in self.trade.supplier_list()])
        self.assertEqual(rows[0]['name'],self.trade.supplier_list()[0]['company_name'])
        self.assertNotIn('private@example.invalid',b.decode());self.assertNotIn('supplier-a@example.com',b.decode())
        self.assertEqual(before,self.snapshot())
        with self.auth.connect() as db:db.execute("UPDATE users SET status='SUSPENDED' WHERE id='supplier-a'")
        self.assertEqual(json.loads(self.get('/autolink/merchants')[1])['data'],[])
    def test_social_config_lists_only_implemented_google(self):
        before=self.snapshot();_,b=self.get('/autolink/auth/social/config')
        self.assertEqual(json.loads(b)['data'],{'google':True})
        self.auth.client_id='';_,b=self.get('/autolink/auth/social/config')
        self.assertEqual(json.loads(b)['data'],{'google':False})
        self.assertFalse(json.loads(self.get('/autolink/auth/google/config')[1])['data']['enabled'])
        self.assertEqual(before,self.snapshot())
    def test_private_head_does_not_dispatch_business_read(self):
        before=self.snapshot()
        with self.assertRaises(urllib.error.HTTPError) as error:self.get('/autolink/supplier/inquiries','HEAD')
        self.assertEqual(error.exception.code,405);self.assertEqual(error.exception.read(),b'')
        self.assertEqual(before,self.snapshot())
    def test_public_json_head_has_no_body(self):
        get,body=self.get('/autolink/public/models')
        head,empty=self.get('/autolink/public/models','HEAD')
        self.assertEqual(empty,b'');self.assertEqual(head.headers['Content-Length'],str(len(body)))
        self.assertIn('noindex',head.headers['X-Robots-Tag'])
    def test_reference_paths_reject_catalog_traversal(self):
        self.assertEqual(Handler.seo.reference({'id':'../../auth/catalog'}),{})
