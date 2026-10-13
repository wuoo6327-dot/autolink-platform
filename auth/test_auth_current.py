import tempfile
import time
import unittest
import json
import threading
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from pathlib import Path

from app import ApiError, AuthService, Handler
from email_auth import EmailAuthService, EmailError, verify_password
from buyer_service import BuyerService
from trade_service import TradeService
from mail_templates import RESOURCES


class CurrentAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.claims = {}
        self.sent = []

        def verify(credential, audience):
            self.assertEqual(audience, 'test-client.apps.googleusercontent.com')
            return self.claims[credential]

        self.auth = AuthService(Path(self.temp.name) / 'auth.sqlite3',
                                'test-client.apps.googleusercontent.com', verifier=verify)
        self.email = EmailAuthService(self.auth, sender=lambda address, code, purpose:
                                      self.sent.append((address, code, purpose)))

    def tearDown(self):
        self.temp.cleanup()

    def code(self, address='buyer@example.com', purpose='login', ip='192.0.2.1'):
        self.email.send_code(address, purpose, ip)
        return self.sent[-1][1]

    def google_body(self, sub='google-1', address='google@example.com', **extra):
        nonce = self.auth.challenge()['nonce']
        credential = 'x' * 130 + str(len(self.claims))
        self.claims[credential] = {'sub': sub, 'email': address, 'email_verified': True,
                                   'nonce': nonce, 'name': 'Example'}
        return {'nonce': nonce, 'credential': credential, **extra}

    def buyer(self, address='buyer@example.com'):
        code = self.code(address)
        session = self.email.login_code({'email': address, 'code': code, 'consent': True})
        self.assertEqual(session['role'], 'BUYER')
        return session

    def test_password_registration_creates_one_verified_buyer_with_country(self):
        service=BuyerService(self.auth)
        code=self.code('Buyer@outlook.com')
        body={'email':'  BUYER@OUTLOOK.COM  ','code':code,'password':'Registration secret 123!',
              'country':' Saudi Arabia ','consent':True,'language':'ar','remember':True}
        result=self.email.register(body)
        user=self.auth.user_for_token(result['access_token'])
        self.assertEqual(result['role'],'BUYER');self.assertEqual(user['role'],'BUYER')
        self.assertTrue(user['email_verified_at']);self.assertEqual(user['preferred_language'],'ar')
        self.assertEqual(service.profile(user)['country'],'Saudi Arabia')
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)
            stored=db.execute('SELECT password_hash FROM email_passwords WHERE user_id=?',(user['id'],)).fetchone()[0]
            self.assertNotEqual(stored,body['password']);self.assertTrue(verify_password(body['password'],stored))
            self.assertIsNotNone(db.execute('SELECT used_at FROM email_verification_codes').fetchone()[0])
            self.assertEqual(db.execute('SELECT count(*) FROM consents WHERE user_id=?',(user['id'],)).fetchone()[0],1)
        logged=self.email.login_password({'email':'buyer@outlook.com','password':body['password']})
        self.assertEqual(self.auth.user_for_token(logged['access_token'])['id'],user['id'])
        self.assertNotIn(body['password'],json.dumps(result));self.assertNotIn(code,json.dumps(result))
        with self.assertRaises(EmailError) as replay:self.email.register(body)
        self.assertEqual(replay.exception.status,401)

    def test_registration_rejects_invalid_fields_without_creating_accounts(self):
        BuyerService(self.auth)
        code=self.code('buyer@company.example')
        body={'email':'buyer@company.example','code':code,'password':'Registration secret 123!',
              'country':'Kenya','consent':True}
        for changes in ({'consent':False},{'country':''},{'country':None},{'country':['Kenya']},
                        {'country':'x'*121},{'country':'Kenya\nheader'},{'password':'short'},
                        {'password':True},{'language':'invalid'},{'role':'PLATFORM_ADMIN'}):
            with self.subTest(changes=changes),self.assertRaises(EmailError) as invalid:
                self.email.register({**body,**changes})
            self.assertEqual(invalid.exception.status,400)
        with patch('email_auth.password_hash') as costly_hash:
            with self.assertRaises(EmailError):self.email.register({**body,'code':'111111' if code!='111111' else '222222'})
            costly_hash.assert_not_called()
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM email_passwords').fetchone()[0],0)
            self.assertIsNone(db.execute('SELECT used_at FROM email_verification_codes').fetchone()[0])
        self.assertEqual(self.email.register(body)['role'],'BUYER')

    def test_registration_never_replaces_existing_google_account_or_role(self):
        BuyerService(self.auth)
        session=self.auth.google_login(self.google_body(companyName='Existing company',consent=True))
        user=self.auth.user_for_token(session['access_token'])
        code=self.code('google@example.com')
        body={'email':'google@example.com','code':code,'password':'Attempted replacement 123!',
              'country':'Kenya','consent':True}
        with self.assertRaises(EmailError) as exists:self.email.register(body)
        self.assertEqual(exists.exception.status,409)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT role FROM users WHERE id=?',(user['id'],)).fetchone()[0],'MERCHANT')
            self.assertEqual(db.execute('SELECT count(*) FROM email_passwords').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM buyer_profiles').fetchone()[0],0)
        logged=self.email.login_code({'email':body['email'],'code':code,'role':'MERCHANT'})
        self.assertEqual(self.auth.user_for_token(logged['access_token'])['id'],user['id'])
        self.assertEqual(logged['role'],'MERCHANT')

    def test_registration_http_verifies_before_cookie_and_checks_origin(self):
        BuyerService(self.auth)
        class LocalHandler(Handler):pass
        LocalHandler.service=self.auth;LocalHandler.email_auth=self.email;LocalHandler.buyer=BuyerService(self.auth)
        server=ThreadingHTTPServer(('127.0.0.1',0),LocalHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base='http://127.0.0.1:'+str(server.server_port)
        code=self.code('buyer@yahoo.com')
        body={'email':'buyer@yahoo.com','code':code,'password':'Registration secret 123!',
              'country':'Kazakhstan','consent':True,'language':'kk'}
        def request(data,origin=None):
            headers={'Content-Type':'application/json'}
            if origin:headers['Origin']=origin
            return urllib.request.Request(base+'/autolink/auth/email/register',data=json.dumps(data).encode(),headers=headers)
        with self.assertRaises(urllib.error.HTTPError) as cross_site:urllib.request.urlopen(request(body,'https://attacker.example'))
        self.assertEqual(cross_site.exception.code,403);cross_site.exception.close()
        with self.assertRaises(urllib.error.HTTPError) as consent:urllib.request.urlopen(request({**body,'consent':False}))
        self.assertEqual(consent.exception.code,400);consent.exception.close()
        with urllib.request.urlopen(request(body)) as response:
            data=json.load(response)['data'];cookie=response.headers['Set-Cookie']
            self.assertEqual(data['role'],'BUYER')
            for flag in ('HttpOnly','Secure','SameSite=Lax'):self.assertIn(flag,cookie)
        account=self.auth.user_for_token(data['access_token'])
        self.assertTrue(account['email_verified_at'])
        self.assertEqual(LocalHandler.buyer.profile(account)['country'],'Kazakhstan')
        self.assertNotIn('password',json.dumps(data))

    def test_reset_revokes_outstanding_login_code_and_does_not_hash_invalid_proof(self):
        session=self.buyer()
        with self.auth.connect() as db:db.execute('UPDATE email_verification_codes SET created_at=?',(int(time.time())-61,))
        login_code=self.code()
        with self.auth.connect() as db:db.execute('UPDATE email_verification_codes SET created_at=?',(int(time.time())-61,))
        reset_code=self.code(purpose='reset_password')
        with patch('email_auth.password_hash') as costly_hash:
            with self.assertRaises(EmailError):self.email.reset_password({'email':'buyer@example.com','code':'111111' if reset_code!='111111' else '222222','password':'New reset secret 123!'})
            costly_hash.assert_not_called()
        self.email.reset_password({'email':'buyer@example.com','code':reset_code,'password':'New reset secret 123!'})
        with self.assertRaises(ApiError):self.auth.user_for_token(session['access_token'])
        with self.assertRaises(EmailError):self.email.login_code({'email':'buyer@example.com','code':login_code})
        self.assertEqual(self.email.login_password({'email':'buyer@example.com','password':'New reset secret 123!'})['role'],'BUYER')

    def test_language_preferences_are_owned_and_additive_without_changing_country(self):
        session=self.buyer();token=session['access_token']
        first=self.auth.user_for_token(token)
        self.assertEqual(first['preferred_language'],'en')
        second=self.buyer('other@example.com')
        buyer=BuyerService(self.auth)
        buyer.update_profile(first,{'country':'Saudi Arabia','companyName':'QA Buyer'})
        self.assertEqual(self.auth.save_language(token,{'language':'ar'}),{'language':'ar'})
        self.assertEqual(self.auth.user_for_token(token)['preferred_language'],'ar')
        self.assertEqual(self.auth.user_for_token(second['access_token'])['preferred_language'],'en')
        self.assertEqual(buyer.profile(first)['country'],'Saudi Arabia')
        for body in ({'language':'bad'},{'language':None},{'language':[]},{'language':'en','user_id':first['id']},{'language':'fr','role':'PLATFORM_ADMIN'}):
            with self.assertRaises(ApiError) as invalid:self.auth.save_language(token,body)
            self.assertEqual(invalid.exception.status,400)
        again=AuthService(self.auth.db_path,'test-client.apps.googleusercontent.com')
        self.assertEqual(again.user_for_token(token)['preferred_language'],'ar')
        with self.auth.connect() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.auth.logout(token)
        with self.assertRaises(ApiError) as expired:self.auth.save_language(token,{'language':'fr'})
        self.assertEqual(expired.exception.status,401)

    def test_localised_code_transport_and_new_buyer_language_without_code_exposure(self):
        email=EmailAuthService(self.auth)
        with patch('mail_service.send_message',return_value='qa-accepted') as sender:
            result=email.send_code('arabic@example.com','login','192.0.2.4','ar')
            self.assertEqual(result,{'retryAfter':60})
            self.assertIn('dir="rtl"',sender.call_args.args[3])
            self.assertIn(RESOURCES['ar']['verification'],sender.call_args.args[1])
        with self.auth.connect() as db:before=db.execute('SELECT count(*) FROM email_verification_codes').fetchone()[0]
        with self.assertRaises(EmailError):email.send_code('bad@example.com','login','192.0.2.4','unknown')
        with self.auth.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM email_verification_codes').fetchone()[0],before)
        code=self.code('chinese@example.com')
        result=self.email.login_code({'email':'chinese@example.com','code':code,'consent':True,'language':'zh-CN'})
        user=self.auth.user_for_token(result['access_token'])
        self.assertEqual(user['preferred_language'],'zh');self.assertEqual(user['role'],'BUYER')
        self.assertNotIn(code,json.dumps(result))

    def test_preference_http_authentication_origin_and_input_boundaries(self):
        session=self.buyer();cookie='autolink_session='+session['access_token']
        class LocalHandler(Handler):pass
        LocalHandler.service=self.auth
        server=ThreadingHTTPServer(('127.0.0.1',0),LocalHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)+'/autolink/auth/preferences'
        def call(body=None,auth=cookie,origin=None):
            headers={'Content-Type':'application/json'}
            if auth:headers['Cookie']=auth
            if origin:headers['Origin']=origin
            request=urllib.request.Request(url,headers=headers,data=json.dumps(body).encode() if body is not None else None)
            try:response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status,json.load(response)
        self.assertEqual(call(auth=None)[0],401)
        self.assertEqual(call({'language':'fr'},auth=None)[0],401)
        self.assertEqual(call({'language':'fr'},origin='https://attacker.example')[0],403)
        self.assertEqual(call({'language':'fr','userId':'other'})[0],400)
        self.assertEqual(call({'language':'fr'})[1]['data'],{'language':'fr'})
        self.assertEqual(call()[1]['data'],{'language':'fr'})
        with self.auth.connect() as db:db.execute("UPDATE users SET status='SUSPENDED'")
        self.assertEqual(call({'language':'ar'})[0],401)

    def test_new_email_code_creates_verified_buyer_and_replay_fails(self):
        session = self.buyer('Buyer@Example.com')
        user = self.auth.user_for_token(session['access_token'])
        self.assertEqual(user['email'], 'buyer@example.com')
        self.assertIsNotNone(user['email_verified_at'])
        with self.assertRaises(EmailError):
            self.email.login_code({'email': 'buyer@example.com', 'code': self.sent[-1][1]})
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 1)

    def test_existing_google_account_uses_same_email_identity(self):
        google = self.auth.google_login(self.google_body(companyName='Example', consent=True))
        google_id = self.auth.user_for_token(google['access_token'])['id']
        code = self.code('google@example.com')
        email = self.email.login_code({'email': 'google@example.com', 'code': code, 'role':'MERCHANT'})
        self.assertEqual(self.auth.user_for_token(email['access_token'])['id'], google_id)
        self.assertEqual(email['role'], 'MERCHANT')

    def test_new_google_subject_cannot_duplicate_verified_email(self):
        self.buyer('google@example.com')
        with self.assertRaises(ApiError) as err:
            self.auth.google_login(self.google_body(address='google@example.com',
                                                    companyName='Other', consent=True))
        self.assertEqual(err.exception.status, 409)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0], 1)

    def test_google_still_signs_in_and_role_is_server_side(self):
        session = self.auth.google_login(self.google_body(companyName='Example', consent=True))
        self.assertEqual(self.auth.user_for_token(session['access_token'])['role'], 'MERCHANT')
        returned = self.auth.google_login(self.google_body())
        self.assertEqual(self.auth.user_for_token(returned['access_token'])['id'],
                         self.auth.user_for_token(session['access_token'])['id'])
        with self.assertRaises(ApiError) as buyer_entry:
            self.auth.google_login(self.google_body(role='BUYER'))
        self.assertEqual(buyer_entry.exception.status, 403)

    def test_code_bad_attempt_limit_expiry_cooldown_and_rate_limit(self):
        code = self.code()
        with self.assertRaises(EmailError) as cooldown:
            self.email.send_code('buyer@example.com', 'login', '192.0.2.1')
        self.assertEqual(cooldown.exception.status, 429)
        for _ in range(5):
            with self.assertRaises(EmailError):
                self.email.login_code({'email': 'buyer@example.com', 'code': '999999' if code != '999999' else '888888'})
        with self.assertRaises(EmailError):
            self.email.login_code({'email': 'buyer@example.com', 'code': code})
        with self.auth.connect() as db:
            db.execute('UPDATE email_verification_codes SET created_at=?, expires_at=?',
                       (int(time.time()) - 61, int(time.time()) + 100))
        new_code = self.code()
        with self.assertRaises(EmailError):
            self.email.login_code({'email': 'buyer@example.com', 'code': code})
        with self.auth.connect() as db:
            db.execute('UPDATE email_verification_codes SET expires_at=0 WHERE code_hash=?',
                       (db.execute('SELECT code_hash FROM email_verification_codes ORDER BY created_at DESC LIMIT 1').fetchone()[0],))
        with self.assertRaises(EmailError):
            self.email.login_code({'email': 'buyer@example.com', 'code': new_code})

    def test_email_and_ip_hourly_send_limits(self):
        for i in range(5):
            if i:
                with self.auth.connect() as db:
                    db.execute('UPDATE email_verification_codes SET created_at=? WHERE email=? AND created_at>?',
                               (int(time.time()) - i * 61, 'limit@example.com', int(time.time()) - 60))
            self.code('limit@example.com')
        with self.auth.connect() as db:
            db.execute('UPDATE email_verification_codes SET created_at=? WHERE email=? AND created_at>?',
                       (int(time.time()) - 301, 'limit@example.com', int(time.time()) - 60))
        with self.assertRaises(EmailError) as email_limit:
            self.email.send_code('limit@example.com', 'login', '192.0.2.2')
        self.assertEqual(email_limit.exception.status, 429)
        for i in range(15):
            self.code('user%d@example.com' % i)
        with self.assertRaises(EmailError) as ip_limit:
            self.email.send_code('extra@example.com', 'login', '192.0.2.1')
        self.assertEqual(ip_limit.exception.status, 429)

    def test_password_set_login_and_reset_revokes_session(self):
        original = self.buyer()
        self.email.set_password(original['access_token'], {'password': 'Correct Horse 123!'})
        with self.assertRaises(EmailError):
            self.email.set_password(original['access_token'], {'password': 'Different pass 123!'})
        logged_in = self.email.login_password({'email': 'buyer@example.com', 'password': 'Correct Horse 123!', 'remember': True}, '192.0.2.1')
        self.assertEqual(logged_in['role'], 'BUYER')
        for address, password in [('buyer@example.com', 'wrong-password'),
                                  ('unknown@example.com', 'wrong-password')]:
            with self.assertRaises(EmailError) as err:
                self.email.login_password({'email': address, 'password': password}, '192.0.2.1')
            self.assertEqual(err.exception.message, 'Invalid email or password.')
        with self.auth.connect() as db:
            db.execute('UPDATE email_verification_codes SET created_at=? WHERE email=?',
                       (int(time.time()) - 61, 'buyer@example.com'))
        reset_code = self.code(purpose='reset_password')
        self.email.reset_password({'email': 'buyer@example.com', 'code': reset_code,
                                   'password': 'New secret password 123'})
        with self.assertRaises(ApiError):
            self.auth.user_for_token(logged_in['access_token'])
        with self.assertRaises(EmailError):
            self.email.reset_password({'email': 'buyer@example.com', 'code': reset_code,
                                       'password': 'Another password 123'})
        self.email.login_password({'email': 'buyer@example.com', 'password': 'New secret password 123'}, '192.0.2.1')

    def test_unknown_reset_does_not_disclose_account(self):
        response = self.email.send_code('nobody@example.com', 'reset_password', '192.0.2.1')
        self.assertEqual(response, {'retryAfter': 60})
        self.assertEqual(self.sent, [])

    def test_change_password_revokes_own_sessions_and_codes_only(self):
        original = self.buyer()
        other = self.buyer('other@example.com')
        self.email.set_password(original['access_token'], {'password':'Old password 123!'})
        second = self.email.login_password({'email':'buyer@example.com','password':'Old password 123!'})
        with self.auth.connect() as db:
            db.execute('UPDATE email_verification_codes SET created_at=created_at-61')
        reset = self.code(purpose='reset_password')
        result = self.email.change_password(original['access_token'], {'currentPassword':'Old password 123!','password':'New password 123!','userId':self.auth.user_for_token(other['access_token'])['id']})
        self.assertTrue(result['signedOut'])
        for session in (original,second):
            with self.assertRaises(ApiError):self.auth.user_for_token(session['access_token'])
        self.auth.user_for_token(other['access_token'])
        with self.assertRaises(EmailError):self.email.login_password({'email':'buyer@example.com','password':'Old password 123!'})
        self.email.login_password({'email':'buyer@example.com','password':'New password 123!'})
        with self.assertRaises(EmailError):self.email.reset_password({'email':'buyer@example.com','code':reset,'password':'Replayed password 123!'})
        with self.auth.connect() as db:
            stored=db.execute('SELECT password_hash FROM email_passwords').fetchone()[0]
            self.assertTrue(stored.startswith('pbkdf2_sha256$600000$'))
            self.assertNotIn('New password',stored)

    def test_change_password_rejects_wrong_current_password_and_limits_attempts(self):
        session=self.buyer();token=session['access_token']
        self.email.set_password(token, {'password':'Old password 123!'})
        for _ in range(10):
            with self.assertRaises(EmailError) as error:self.email.change_password(token, {'currentPassword':'Wrong password 123!','password':'New password 123!'},'192.0.2.50')
            self.assertEqual(error.exception.status,401)
        with self.assertRaises(EmailError) as limited:self.email.change_password(token, {'currentPassword':'Old password 123!','password':'New password 123!'},'192.0.2.50')
        self.assertEqual(limited.exception.status,429)
        self.auth.user_for_token(token)
        self.email.login_password({'email':'buyer@example.com','password':'Old password 123!'})

    def test_change_password_rechecks_session_after_hashing_and_requires_verified_email(self):
        token=self.buyer()['access_token']
        self.email.set_password(token, {'password':'Old password 123!'})
        from email_auth import password_hash
        def concurrent_logout(value):
            result=password_hash(value);self.auth.logout(token);return result
        with patch('email_auth.password_hash',side_effect=concurrent_logout):
            with self.assertRaises(EmailError) as stale:self.email.change_password(token,{'currentPassword':'Old password 123!','password':'New password 123!'})
        self.assertEqual(stale.exception.status,401)
        renewed=self.email.login_password({'email':'buyer@example.com','password':'Old password 123!'})
        with self.auth.connect() as db:db.execute('UPDATE users SET email_verified_at=NULL')
        with self.assertRaises(EmailError) as unverified:self.email.change_password(renewed['access_token'],{'currentPassword':'Old password 123!','password':'New password 123!'})
        self.assertEqual(unverified.exception.status,403)

    def test_http_cookie_login_and_buyer_role_enforcement(self):
        Handler.service, Handler.email_auth, Handler.buyer = self.auth, self.email, BuyerService(self.auth)
        Handler.trade = TradeService(self.auth)
        Handler.platform = Handler.trade.platform
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = 'http://127.0.0.1:%s' % server.server_port

        def call(path, data=None, cookie=None):
            headers = {'Content-Type': 'application/json'}
            if cookie:
                headers['Cookie'] = cookie
            request = urllib.request.Request(url + path, data=json.dumps(data).encode() if data is not None else None,
                                             headers=headers)
            with urllib.request.urlopen(request) as response:
                return response, json.load(response)

        try:
            with self.assertRaises(urllib.error.HTTPError) as unchecked:
                call('/autolink/auth/email/send-code', {'email': 'buyer@example.com'})
            self.assertEqual(unchecked.exception.code, 400)
            self.assertEqual(self.sent, [])
            _, sent = call('/autolink/auth/email/send-code', {'email': 'buyer@example.com', 'consent': True})
            self.assertEqual(sent['code'], 200)
            self.assertNotIn(self.sent[-1][1], json.dumps(sent))
            response, result = call('/autolink/auth/email/login',
                                    {'email': 'buyer@example.com', 'code': self.sent[-1][1], 'consent': True})
            cookie = response.headers['Set-Cookie']
            for flag in ('HttpOnly', 'Secure', 'SameSite=Lax'):
                self.assertIn(flag, cookie)
            self.assertEqual(result['data']['role'], 'BUYER')
            cookie_pair = cookie.split(';', 1)[0]
            _, current = call('/autolink/me', cookie=cookie_pair)
            self.assertEqual(current['data']['role'], 'BUYER')
            with self.assertRaises(urllib.error.HTTPError) as forbidden:
                call('/autolink/merchant/overview', cookie=cookie_pair)
            self.assertEqual(forbidden.exception.code, 403)
            _, overview = call('/autolink/buyer/overview', cookie=cookie_pair)
            self.assertEqual(overview['code'], 200)
            _, security = call('/autolink/auth/security', cookie=cookie_pair)
            self.assertTrue(security['data']['emailVerified'])
            self.assertNotIn('password_hash', json.dumps(security))
            call('/autolink/auth/password/set', {'password':'HTTP old password 123!'},cookie_pair)
            blocked=urllib.request.Request(url+'/autolink/auth/password/change',data=json.dumps({'currentPassword':'HTTP old password 123!','password':'HTTP new password 123!'}).encode(),headers={'Content-Type':'application/json','Cookie':cookie_pair,'Origin':'https://untrusted.example'})
            with self.assertRaises(urllib.error.HTTPError) as csrf:urllib.request.urlopen(blocked)
            self.assertEqual(csrf.exception.code,403)
            response, changed=call('/autolink/auth/password/change',{'currentPassword':'HTTP old password 123!','password':'HTTP new password 123!'},cookie_pair)
            self.assertTrue(changed['data']['signedOut'])
            self.assertIn('Max-Age=0',response.headers['Set-Cookie'])
            with self.assertRaises(urllib.error.HTTPError) as revoked:call('/autolink/me',cookie=cookie_pair)
            self.assertEqual(revoked.exception.code,401)
            response, logged=call('/autolink/auth/password/login',{'email':'buyer@example.com','password':'HTTP new password 123!'})
            self.assertEqual(logged['data']['role'],'BUYER')
            cookie_pair=response.headers['Set-Cookie'].split(';',1)[0]
            _, signed_out=call('/autolink/auth/logout-all',{},cookie_pair)
            self.assertTrue(signed_out['data']['signedOut'])
            with self.assertRaises(urllib.error.HTTPError):call('/autolink/auth/security',cookie=cookie_pair)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
