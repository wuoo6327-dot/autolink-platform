"""Cookie account closure, private media and HEAD regressions on loopback only."""
import json
import os
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import Handler
import test_security_release as capability_fixtures


class SecurityReleaseHTTPTests(unittest.TestCase):
    user = capability_fixtures.SecurityReleaseTests.user
    approved = capability_fixtures.SecurityReleaseTests.approved
    private_image = capability_fixtures.SecurityReleaseTests.private_image

    def setUp(self):
        capability_fixtures.SecurityReleaseTests.setUp(self)
        class LocalHandler(Handler):
            def log_message(self, *args):
                pass
        LocalHandler.service = self.auth
        LocalHandler.email_auth = self.email
        LocalHandler.buyer = self.buyer
        LocalHandler.trade = self.trade
        LocalHandler.platform = self.trade.platform
        server = ThreadingHTTPServer(('127.0.0.1', 0), LocalHandler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.base = 'http://127.0.0.1:' + str(server.server_port)

    def request(self, path='/autolink/me', method='GET', account='buyer', headers=None, token=None):
        request_headers = {'Content-Type': 'application/json'}
        if account:
            request_headers['Cookie'] = 'autolink_session=' + (token or self.tokens[account])
        request_headers.update(headers or {})
        body = b'{}' if method in ('POST', 'PUT', 'DELETE') else None
        req = urllib.request.Request(self.base+path, data=body, method=method, headers=request_headers)
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    def snapshot(self):
        with self.auth.connect() as db:
            return list(db.iterdump())

    def test_cookie_owner_and_last_admin_cannot_close_and_keep_all_sessions(self):
        second = self.auth.session_for_user('admin')['access_token']
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': ' ADMIN@EXAMPLE.COM '}):
            before = self.snapshot()
            status, _, body = self.request(account='admin')
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body)['data']['accountDeletionAllowed'])
            status, headers, _ = self.request(method='DELETE', account='admin', headers={'Origin': 'https://autolinkglobal.com'})
            self.assertEqual(status, 403)
            self.assertNotIn('Set-Cookie', headers)
            self.assertEqual(self.snapshot(), before)
            self.assertEqual(self.request(account='admin', token=second)[0], 200)
        with self.auth.connect() as db:
            db.execute("UPDATE users SET status='SUSPENDED' WHERE id='other-admin'")
        before = self.snapshot()
        self.assertFalse(json.loads(self.request(account='admin')[2])['data']['accountDeletionAllowed'])
        self.assertEqual(self.request(method='DELETE', account='admin')[0], 403)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.request(account='admin', token=second)[0], 200)

    def test_cookie_business_close_preserves_records_revokes_every_session_and_clears_cookie(self):
        self.approved('legacy')
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("INSERT INTO buyer_profiles(user_id,country,updated_at) VALUES ('legacy','Kenya',?)", (now,))
            db.execute("INSERT INTO buyer_memberships(id,user_id,plan,status,start_at,end_at) VALUES ('paid','legacy','annual','ACTIVE',?,?)", (now-1, now+3600))
            preserved = {table: [tuple(row) for row in db.execute('SELECT * FROM '+table)]
                         for table in ('buyer_profiles', 'buyer_memberships', 'supplier_applications')}
        second = self.auth.session_for_user('legacy')['access_token']
        self.assertTrue(json.loads(self.request(account='legacy')[2])['data']['accountDeletionAllowed'])
        status, headers, body = self.request(method='DELETE', account='legacy', headers={'Origin': 'https://autolinkglobal.com'})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['data']['deleted'])
        for flag in ('autolink_session=', 'Max-Age=0', 'Path=/', 'HttpOnly', 'SameSite=Lax'):
            self.assertIn(flag, headers['Set-Cookie'])
        for token in (self.tokens['legacy'], second):
            self.assertEqual(self.request(account='legacy', token=token)[0], 401)
        with self.auth.connect() as db:
            row = db.execute("SELECT role,status,deleted_at FROM users WHERE id='legacy'").fetchone()
            self.assertEqual((row['role'], row['status']), ('MERCHANT', 'DELETED'))
            self.assertIsNotNone(row['deleted_at'])
            self.assertEqual(db.execute("SELECT count(*) FROM sessions WHERE user_id='legacy'").fetchone()[0], 0)
            self.assertEqual({table: [tuple(row) for row in db.execute('SELECT * FROM '+table)] for table in preserved}, preserved)
        self.assertEqual(self.request(account='buyer')[0], 200)

    def test_cross_site_and_invalid_origin_never_close_cookie_accounts(self):
        for headers in ({'Origin': 'https://foreign.example'}, {'Sec-Fetch-Site': 'cross-site'},
                        {'Origin': 'https://autolinkglobal.com', 'Sec-Fetch-Site': 'cross-site'},
                        {'Origin': 'null'}):
            with self.subTest(headers=headers):
                before = self.snapshot()
                self.assertEqual(self.request(method='DELETE', headers=headers)[0], 403)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(self.request()[0], 200)
        for account, token in ((None, None), ('buyer', 'invalid-synthetic-cookie')):
            before = self.snapshot()
            self.assertEqual(self.request(method='DELETE', account=account, token=token)[0], 401)
            self.assertEqual(self.snapshot(), before)

    def test_private_images_allow_company_and_platform_owner_then_revoke_immediately(self):
        self.private_image()
        path = '/autolink/public/vehicle-images/image'
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': 'admin@example.com'}):
            for account in ('buyer', 'admin'):
                status, headers, body = self.request(path, account=account)
                self.assertEqual(status, 200)
                self.assertEqual(body, b'SYNTHETIC PRIVATE IMAGE')
                self.assertNotIn('X-Robots-Tag', headers)
                self.assertEqual(headers['Cache-Control'], 'no-store')
            for account in (None, 'legacy', 'other-admin'):
                with self.subTest(account=account):
                    self.assertEqual(self.request(path, account=account)[0], 404)
            with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': 'other-admin@example.com'}):
                self.assertEqual(self.request(path, account='admin')[0], 404)
            for account in ('buyer', 'admin'):
                with self.auth.connect() as db:
                    db.execute('UPDATE users SET status=? WHERE id=?', ('SUSPENDED', account))
                self.assertEqual(self.request(path, account=account)[0], 404)

