"""Private online test account: login, tenant isolation and publishing limits."""
import json
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from app import Handler
from email_auth import EmailAuthService, password_hash
from buyer_service import BuyerService, BuyerError
import test_trade


class TestWorkspaceTests(unittest.TestCase):
    setUp = test_trade.TradeFlowTests.setUp

    def activate(self):
        owner=self.users['supplier-a']
        self.trade.save_application(owner,{'companyName':'Private test workspace',
            'registrationNo':'TEST-ONLY','address':'Synthetic private test data',
            'country':'China','contactName':'Test owner','contactPhone':'000000'})
        with self.auth.connect() as db:
            db.execute("UPDATE users SET is_test_workspace=1 WHERE id=?",(owner['id'],))
            db.execute("UPDATE supplier_applications SET status='APPROVED' WHERE supplier_id=?",(owner['id'],))
            db.execute('INSERT INTO email_passwords VALUES (?,?,?)',
                (owner['id'],password_hash('Synthetic test password!'),1))
        return self.auth.user_for_token(self.auth.session_for_user(owner['id'])['access_token'])

    def server(self):
        class PrivateHandler(Handler):pass
        PrivateHandler.service=self.auth;PrivateHandler.trade=self.trade
        PrivateHandler.email_auth=EmailAuthService(self.auth,sender=lambda *_:None)
        PrivateHandler.buyer=BuyerService(self.auth);PrivateHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),PrivateHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        return 'http://127.0.0.1:'+str(server.server_port)

    def request(self,base,path,token='',body=None,method=None,company=None):
        headers={'Cookie':'autolink_session='+token,'Origin':'https://autolinkglobal.com',
            'Content-Type':'application/json'}
        if company:headers['X-Autolink-Supplier']=company
        request=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
            headers=headers,method=method)
        try:
            with urllib.request.urlopen(request) as response:return response.status,json.load(response),response.headers
        except urllib.error.HTTPError as exc:return exc.code,json.load(exc),exc.headers

    def test_password_login_session_dashboard_and_tenant_denial(self):
        owner=self.activate();base=self.server()
        status,result,headers=self.request(base,'/autolink/auth/password/login',body={
            'email':owner['email'],'password':'Synthetic test password!'})
        self.assertEqual(status,200)
        token=result['data']['access_token'];cookie=headers.get('Set-Cookie','')
        self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Lax',cookie)
        self.assertTrue(self.request(base,'/autolink/me',token)[1]['data']['isTestWorkspace'])
        self.assertEqual(self.request(base,'/autolink/supplier/overview',token)[0],200)
        self.assertEqual(self.request(base,'/autolink/supplier/overview',token,company='supplier-b')[0],404)
        self.assertEqual(self.request(base,'/autolink/admin/users',token)[0],403)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT is_test_workspace FROM users WHERE id='buyer-a'").fetchone()[0],0)

    def test_private_drafts_work_and_real_business_actions_are_denied(self):
        owner=self.activate();base=self.server();token=self.auth.session_for_user(owner['id'])['access_token']
        form={'modelId':'zeekr-9x-2026','modelYear':2026,'priceMinor':1000000,
            'stock':1,'moq':1,'originPort':'Test port','validUntil':str(date.today())}
        status,result,_=self.request(base,'/autolink/supplier/vehicles',token,form)
        self.assertEqual(status,200);listing=result['data']['id']
        self.assertEqual(result['data']['status'],'DRAFT')
        for path in ('/autolink/supplier/vehicles/'+listing+'/submit',
                     '/autolink/supplier/vehicles/'+listing+'/online',
                     '/autolink/supplier/team/invite','/autolink/supplier/agreement',
                     '/autolink/buyer/inquiries','/autolink/support','/autolink/reports'):
            self.assertEqual(self.request(base,path,token,{},'POST')[0],403,path)
        self.assertEqual(self.request(base,'/autolink/supplier/buying-requests',token)[0],403)
        for action in ('copy','archive','restore'):
            self.assertEqual(self.request(base,'/autolink/supplier/vehicles/'+listing+'/'+action,token,{})[0],200)
        with self.assertRaises(BuyerError):self.trade.transition_vehicle(owner,listing,'submit')

    def test_public_queries_hide_test_accounts_even_with_legacy_public_rows(self):
        listing=test_trade.TradeFlowTests.approved_vehicle(self)
        with self.auth.connect() as db:db.execute("UPDATE users SET is_test_workspace=1 WHERE id='supplier-a'")
        self.assertIsNone(self.trade.public_supplier('supplier-a'))
        self.assertNotIn(listing,{v['id'] for v in self.trade.vehicle_rows(public=True)})
        with self.assertRaises(BuyerError):self.trade.vehicle(listing,public=True)

    def test_database_guards_block_test_publication(self):
        owner=self.activate()
        item=self.trade.save_vehicle(owner,{'modelId':'zeekr-9x-2026','modelYear':2026,
            'priceMinor':1000000,'stock':1,'moq':1,'originPort':'Test port','validUntil':str(date.today())})
        for sql,args in [('UPDATE supplier_profiles SET published=1 WHERE user_id=?',(owner['id'],)),
            ("UPDATE supplier_vehicles SET status='ONLINE' WHERE id=?",(item['id'],)),
            ("UPDATE supplier_vehicles SET status='PENDING_REVIEW' WHERE id=?",(item['id'],))]:
            with self.assertRaises(sqlite3.IntegrityError):
                with self.auth.connect() as db:db.execute(sql,args)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

if __name__=='__main__':unittest.main()
