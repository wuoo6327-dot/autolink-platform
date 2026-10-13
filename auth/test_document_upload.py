"""Uploads before company-form completion must persist privately without approval."""
import base64
import json
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import test_trade
from app import Handler
from buyer_service import BuyerError, BuyerService

class DocumentUploadTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp

    def body(self):
        return {'kind':'BUSINESS_LICENSE','filename':'local-upload-test.pdf','contentType':'application/pdf',
                'base64':base64.b64encode(b'%PDF-1.4\n1 0 obj << >> endobj\n%%EOF').decode()}

    def test_upload_first_creates_only_private_draft_and_keeps_role(self):
        user=self.users['supplier-a']
        saved=self.trade.add_document(user,self.body())
        self.assertEqual(self.trade.documents(user['id'])[0]['id'],saved['id'])
        application=self.trade.application(user)
        self.assertEqual(application['status'],'DRAFT')
        self.assertEqual(application['registration_no'],'')
        self.assertIsNone(application['agreementConfirmation'])
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT role FROM users WHERE id=?',(user['id'],)).fetchone()[0],'MERCHANT')
            self.assertEqual(db.execute('SELECT published FROM supplier_profiles WHERE user_id=?',(user['id'],)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_documents WHERE supplier_id=?',(user['id'],)).fetchone()[0],1)
        with self.assertRaises(BuyerError):self.trade.document_bytes(saved['id'],self.users['supplier-b'])
        self.assertNotIn('stored_name',saved)

    def test_invalid_file_does_not_create_a_draft(self):
        with self.assertRaises(BuyerError):self.trade.add_document(self.users['supplier-a'],{**self.body(),'base64':base64.b64encode(b'invalid'+b'x'*100).decode()})
        with self.auth.connect() as db:
            self.assertIsNone(db.execute('SELECT status FROM supplier_applications WHERE supplier_id=?',('supplier-a',)).fetchone())
        self.assertEqual(self.trade.documents('supplier-a'),[])

    def test_locked_state_and_limit_still_enforced(self):
        user=self.users['supplier-a'];self.trade.add_document(user,self.body())
        with self.auth.connect() as db:db.execute("UPDATE supplier_applications SET status='PENDING' WHERE supplier_id=?",(user['id'],))
        with self.assertRaises(BuyerError):self.trade.add_document(user,self.body())
        with self.auth.connect() as db:db.execute("UPDATE supplier_applications SET status='DRAFT' WHERE supplier_id=?",(user['id'],))
        for _ in range(5):self.trade.add_document(user,self.body())
        with self.assertRaises(BuyerError):self.trade.add_document(user,self.body())
        self.assertEqual(len(self.trade.documents(user['id'])),6)

    def test_http_upload_first_csrf_auth_and_idor(self):
        Handler.service=self.auth;Handler.trade=self.trade;Handler.buyer=BuyerService(self.auth);Handler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        token=self.auth.session_for_user('supplier-a')['access_token']
        def call(path,body=None,cookie=token,company=None,origin=None):
            headers={'Content-Type':'application/json','Cookie':'autolink_session='+cookie}
            if company:headers['X-Autolink-Supplier']=company
            if origin:headers['Origin']=origin
            request=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,headers=headers,data=json.dumps(body).encode() if body else None)
            try:
                with urllib.request.urlopen(request) as r:return r.status,json.load(r)
            except urllib.error.HTTPError as r:return r.code,json.load(r)
        endpoint='/autolink/supplier/documents'
        self.assertEqual(call(endpoint,self.body(),cookie='invalid')[0],401)
        self.assertEqual(call(endpoint,self.body(),origin='https://attacker.example')[0],403)
        self.assertEqual(call(endpoint,self.body(),company='supplier-b')[0],404)
        status,result=call(endpoint,self.body());self.assertEqual(status,200)
        status,rows=call(endpoint);self.assertEqual(status,200)
        self.assertEqual(rows['data'][0]['id'],result['data']['id'])
        self.assertEqual(call('/autolink/supplier/vehicles')[0],403)

if __name__=='__main__':unittest.main()
