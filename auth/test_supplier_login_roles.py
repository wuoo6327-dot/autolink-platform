"""Supplier entry never changes the role of an existing identity.

All accounts and provider responses are synthetic and use an isolated SQLite DB.
"""

import tempfile
import time
import unittest
import uuid
import os
import json
import threading
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from app import ApiError, AuthService, Handler
from buyer_service import BuyerError, BuyerService
from email_auth import EmailAuthService, EmailError, password_hash
from trade_service import TradeService


class SupplierLoginRoleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.claims = {}
        self.sent = []
        self.auth = AuthService(Path(temporary.name) / "auth.sqlite3", "synthetic-client",
                                verifier=lambda credential, audience: self.claims[credential])
        self.email = EmailAuthService(self.auth, sender=lambda address, code, purpose:
                                      self.sent.append((address, code, purpose)))
        BuyerService(self.auth)
        self.trade = TradeService(self.auth)

    def account(self, name, role="BUYER", google=False, application=False):
        account_id = "synthetic-" + name
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("""INSERT INTO users
                (id,google_sub,email,display_name,company_name,role,created_at,email_verified_at)
                VALUES (?,?,?,?,?,?,?,?)""", (account_id, "google-" + name if google else None,
                    name + "@example.com", "Synthetic " + name, "Existing company", role, now - 1000, now - 1000))
            db.execute("INSERT INTO email_identities(email,user_id) VALUES (?,?)",
                       (name + "@example.com", account_id))
            db.execute("INSERT INTO email_passwords(user_id,password_hash,updated_at) VALUES (?,?,?)",
                       (account_id, password_hash("Synthetic login password 123!"), now - 1000))
            db.execute("INSERT INTO buyer_profiles(user_id,country,contact_person,updated_at) VALUES (?,?,?,?)",
                       (account_id, "Hong Kong", "Existing contact", now - 1000))
            db.execute("INSERT INTO buyer_saved_vehicles(user_id,vehicle_id,created_at) VALUES (?,?,?)",
                       (account_id, "geely-monjaro-2026", now - 1000))
            db.execute("INSERT INTO consents(user_id,terms_version,privacy_version,accepted_at) VALUES (?,?,?,?)",
                       (account_id, "existing-terms", "existing-privacy", now - 1000))
        if application:
            if role in ('MERCHANT','SUPPLIER'):
                self.trade.save_application(self.read_user(account_id), {
                    "companyName": "Existing registered company", "registrationNo": "SYNTHETIC-REG-001",
                    "country": "Hong Kong", "address": "Existing company address",
                    "contactName": "Existing sales contact", "contactPhone": "+85200000000"})
            else:
                # Model a private draft left by the old dual-role implementation.
                with self.auth.connect() as db:
                    db.execute("INSERT INTO supplier_profiles(user_id,published,updated_at) VALUES (?,0,?)",
                               (account_id,now-1000))
                    db.execute("INSERT INTO supplier_applications(supplier_id,registration_no,address,contact_name,contact_phone,status,updated_at) VALUES (?,?,?,?,?,'DRAFT',?)",
                               (account_id,'SYNTHETIC-REG-001','Existing company address','Existing sales contact','+85200000000',now-1000))
            with self.auth.connect() as db:
                db.execute("UPDATE supplier_applications SET status='REQUIRES_CHANGES',review_reason=? WHERE supplier_id=?",
                           ("Existing private review note", account_id))
        return account_id

    def read_user(self, account_id):
        with self.auth.connect() as db:
            return dict(db.execute("SELECT * FROM users WHERE id=?", (account_id,)).fetchone())

    def preserved_data(self, account_id):
        with self.auth.connect() as db:
            data = {"identity": tuple(db.execute("""SELECT id,google_sub,email,display_name,company_name,created_at
                       FROM users WHERE id=?""", (account_id,)).fetchone())}
            for table, key in (("email_passwords", "user_id"), ("buyer_profiles", "user_id"),
                               ("buyer_saved_vehicles", "user_id"), ("consents", "user_id"),
                               ("supplier_profiles", "user_id"), ("supplier_applications", "supplier_id"),
                               ("supplier_team_members", "user_id")):
                data[table] = [tuple(row) for row in db.execute("SELECT * FROM " + table + " WHERE " + key + "=?", (account_id,))]
            data["user_count"] = db.execute("SELECT count(*) FROM users").fetchone()[0]
            return data

    def code_login(self, name, role="BUYER"):
        address = name + "@example.com"
        self.email.send_code(address, "login", "192.0.2.20")
        return self.email.login_code({"email": address, "code": self.sent[-1][1], "role": role})

    def password_login(self, name, role="BUYER", password="Synthetic login password 123!"):
        return self.email.login_password({"email": name + "@example.com", "password": password,
                                          "role": role}, "192.0.2.20")

    def google_body(self, name, role="BUYER", verified=True):
        nonce = self.auth.challenge()["nonce"]
        credential = "x" * 130 + uuid.uuid4().hex
        self.claims[credential] = {"sub": "google-" + name, "email": name + "@example.com",
                                   "email_verified": verified, "nonce": nonce}
        return {"credential": credential, "nonce": nonce, "role": role}

    def login(self, method, name, role):
        if method == "password":
            return self.password_login(name, role)
        if method == "code":
            return self.code_login(name, role)
        return self.auth.google_login(self.google_body(name, role))

    def test_supplier_entry_rejects_buyer_without_changing_data_for_each_provider(self):
        for method in ("password", "code", "google"):
            with self.subTest(provider=method):
                account_id = self.account(method, google=method == "google", application=True)
                before = self.preserved_data(account_id)
                with self.assertRaises((EmailError, ApiError)) as denied:
                    self.login(method, method, "MERCHANT")
                self.assertEqual(denied.exception.status, 403)
                self.assertEqual(self.read_user(account_id)['role'], 'BUYER')
                self.assertEqual(self.preserved_data(account_id), before)
                if method == "code":
                    with self.auth.connect() as db:
                        db.execute("UPDATE email_verification_codes SET created_at=0 WHERE email=?", (method + "@example.com",))
                again = self.login(method, method, "BUYER")
                self.assertEqual(again["role"], "BUYER")
                self.assertEqual(self.auth.user_for_token(again["access_token"])["id"], account_id)

    def test_regular_buyer_entry_never_promotes_for_each_provider(self):
        for method in ("password", "code", "google"):
            with self.subTest(provider=method):
                name = "ordinary-" + method
                account_id = self.account(name, google=method == "google")
                before = self.preserved_data(account_id)
                result = self.login(method, name, "BUYER")
                self.assertEqual(result["role"], "BUYER")
                self.assertEqual(self.read_user(account_id)["role"], "BUYER")
                self.assertEqual(self.preserved_data(account_id), before)

    def test_existing_supplier_and_admin_roles_are_preserved_for_each_provider(self):
        for original_role in ("MERCHANT", "SUPPLIER", "PLATFORM_ADMIN"):
            for method in ("password", "code", "google"):
                with self.subTest(role=original_role, provider=method):
                    name = original_role.lower() + "-" + method
                    account_id = self.account(name, role=original_role, google=method == "google", application=True)
                    before = self.preserved_data(account_id)
                    result = self.login(method, name, "MERCHANT")
                    self.assertEqual(result["role"], original_role)
                    self.assertEqual(self.read_user(account_id)["role"], original_role)
                    self.assertEqual(self.preserved_data(account_id), before)
                    if method == 'code':
                        with self.auth.connect() as db:
                            db.execute('UPDATE email_verification_codes SET created_at=0 WHERE email=?', (name+'@example.com',))
                    with self.assertRaises((EmailError, ApiError)) as denied:
                        self.login(method, name, 'BUYER')
                    self.assertEqual(denied.exception.status, 403)

    def test_failed_password_does_not_change_role_or_business_data(self):
        account_id = self.account("bad-password", application=True)
        before = self.preserved_data(account_id)
        with self.assertRaises(EmailError) as denied:
            self.password_login("bad-password", "MERCHANT", "Incorrect password")
        self.assertEqual(denied.exception.status, 401)
        self.assertEqual(self.read_user(account_id)["role"], "BUYER")
        self.assertEqual(self.preserved_data(account_id), before)

    def test_invalid_code_does_not_change_role_or_consume_valid_code(self):
        account_id = self.account("bad-code", application=True)
        before = self.preserved_data(account_id)
        self.email.send_code("bad-code@example.com", "login", "192.0.2.20")
        code = self.sent[-1][1]
        with self.assertRaises(EmailError) as denied:
            self.email.login_code({"email": "bad-code@example.com", "code": "111111" if code != "111111" else "222222", "role": "MERCHANT"})
        self.assertEqual(denied.exception.status, 401)
        self.assertEqual(self.read_user(account_id)["role"], "BUYER")
        self.assertEqual(self.preserved_data(account_id), before)
        with self.auth.connect() as db:
            self.assertIsNone(db.execute("SELECT used_at FROM email_verification_codes").fetchone()[0])

    def test_invalid_google_identity_and_nonce_do_not_change_role(self):
        account_id = self.account("bad-google", google=True, application=True)
        before = self.preserved_data(account_id)
        for case in ("unverified", "nonce", "signature"):
            with self.subTest(case=case):
                body = self.google_body("bad-google", "MERCHANT", verified=case != "unverified")
                if case == "nonce":
                    self.claims[body["credential"]]["nonce"] = "unrelated-nonce"
                elif case == "signature":
                    del self.claims[body["credential"]]
                with self.assertRaises(ApiError) as denied:
                    self.auth.google_login(body)
                self.assertEqual(denied.exception.status, 401)
                self.assertEqual(self.read_user(account_id)["role"], "BUYER")
                self.assertEqual(self.preserved_data(account_id), before)

    def test_requesting_admin_role_cannot_promote_password_or_code_account(self):
        account_id = self.account("admin-hint")
        with self.assertRaises(EmailError) as denied:
            self.password_login("admin-hint", "PLATFORM_ADMIN")
        self.assertEqual(denied.exception.status, 400)
        self.email.send_code("admin-hint@example.com", "login", "192.0.2.20")
        with self.assertRaises(EmailError) as denied:
            self.email.login_code({"email": "admin-hint@example.com", "code": self.sent[-1][1], "role": "PLATFORM_ADMIN"})
        self.assertEqual(denied.exception.status, 400)
        self.assertEqual(self.read_user(account_id)["role"], "BUYER")

    def test_google_client_admin_hint_cannot_change_existing_account_role(self):
        account_id = self.account("google-admin-hint", google=True)
        before = self.preserved_data(account_id)
        try:
            result = self.auth.google_login(self.google_body("google-admin-hint", "PLATFORM_ADMIN"))
        except ApiError as denied:
            self.assertEqual(denied.status, 400)
        else:
            self.assertEqual(result["role"], "BUYER")
            self.assertEqual(self.auth.user_for_token(result["access_token"])["id"], account_id)
        self.assertEqual(self.read_user(account_id)["role"], "BUYER")
        self.assertEqual(self.preserved_data(account_id), before)

    def test_supplier_sign_in_does_not_approve_application_or_allow_publication(self):
        account_id = self.account("applicant", role="MERCHANT", application=True)
        result = self.password_login("applicant", "MERCHANT")
        principal = self.trade.require_supplier(result["access_token"], approved=False)
        self.assertEqual(principal["supplier_role"], "OWNER")
        self.assertEqual(self.trade.application(principal)["status"], "REQUIRES_CHANGES")
        with self.assertRaises(BuyerError) as denied:
            self.trade.require_supplier(result["access_token"], approved=True)
        self.assertEqual(denied.exception.status, 403)
        with self.assertRaises(BuyerError) as denied:
            self.trade.transition_vehicle(principal, "nonexistent-listing", "online")
        self.assertEqual(denied.exception.status, 403)
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT published FROM supplier_profiles WHERE user_id=?", (account_id,)).fetchone()[0], 0)
        self.assertEqual(self.trade.supplier_list(public=True), [])

    def test_existing_team_scope_stays_sales_and_other_company_is_denied(self):
        owner = self.account("owner", role="MERCHANT", application=True)
        other = self.account("other-owner", role="MERCHANT", application=True)
        staff = self.account("sales", role="MERCHANT", application=True)
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET status='APPROVED' WHERE supplier_id IN (?,?)", (owner, other))
            db.execute("INSERT INTO supplier_team_members(supplier_id,user_id,role,status,joined_at) VALUES (?,?,'SALES','ACTIVE',?)",
                       (owner, staff, int(time.time())))
        before = self.preserved_data(staff)
        result = self.password_login("sales", "MERCHANT")
        principal = self.trade.require_supplier(result["access_token"], approved=True, supplier_id=owner)
        self.assertEqual((principal["id"], principal["actor_user_id"], principal["supplier_role"]), (owner, staff, "SALES"))
        self.assertEqual(self.preserved_data(staff), before)
        with self.assertRaises(BuyerError) as denied:
            self.trade.require_supplier(result["access_token"], approved=True, supplier_id=other)
        self.assertEqual(denied.exception.status, 404)
        with self.assertRaises(BuyerError) as denied:
            self.trade.team.owner(principal)
        self.assertEqual(denied.exception.status, 403)
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_team_members SET status='REMOVED' WHERE supplier_id=? AND user_id=?", (owner, staff))
        with self.assertRaises(BuyerError) as denied:
            self.trade.require_supplier(result["access_token"], approved=True, supplier_id=owner)
        self.assertEqual(denied.exception.status, 404)

    def test_admin_can_return_only_unsubmitted_supplier_to_buyer_access(self):
        admin_id = self.account('access-admin', role='PLATFORM_ADMIN')
        target = self.account('access-target', role='MERCHANT', application=True)
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET status='DRAFT',submitted_at=NULL WHERE supplier_id=?", (target,))
            db.execute("INSERT INTO supplier_documents(id,supplier_id,kind,filename,content_type,stored_name,bytes,uploaded_at) VALUES (?,?,?,?,?,?,?,?)",
                       ('DOC-SYNTHETIC',target,'BUSINESS_LICENSE','private.pdf','application/pdf','synthetic-private',20,int(time.time())))
        session = self.auth.session_for_user(target)['access_token']
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL':'access-admin@example.com'}):
            with self.assertRaises(BuyerError) as denied:
                self.trade.clear_supplier_access(self.read_user(admin_id), target,
                    {'confirmEmail':'other@example.com','reason':'Correct account role'})
            self.assertEqual(denied.exception.status, 409)
            result = self.trade.clear_supplier_access(self.read_user(admin_id), target,
                {'confirmEmail':'access-target@example.com','reason':'Correct account role'})
        self.assertEqual(result['role'], 'BUYER')
        self.assertEqual(self.read_user(target)['role'], 'BUYER')
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_applications WHERE supplier_id=?', (target,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_profiles WHERE user_id=?', (target,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM supplier_documents WHERE supplier_id=?', (target,)).fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM buyer_profiles WHERE user_id=?', (target,)).fetchone()[0], 1)
        with self.assertRaises(ApiError):
            self.auth.user_for_token(session)
        buyer_session = self.password_login('access-target', 'BUYER')['access_token']
        with self.assertRaises(BuyerError) as denied:
            self.trade.require_supplier(buyer_session)
        self.assertEqual(denied.exception.status, 403)

    def test_admin_erasure_removes_empty_accounts_and_blocks_business_history(self):
        admin_id = self.account('erase-admin', role='PLATFORM_ADMIN')
        empty_id = self.account('erase-empty')
        busy_id = self.account('erase-busy')
        draft_id = self.account('erase-draft', role='MERCHANT', application=True)
        token = self.auth.session_for_user(empty_id)['access_token']
        with self.auth.connect() as db:
            self.trade.audit(db, busy_id, 'BUYER_REQUEST_CREATED', 'request', 'synthetic-request')
        request = {'confirmEmail':'erase-empty@example.com','reasonCode':'USER_REQUEST',
                   'confirmation':'DELETE'}
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL':'erase-admin@example.com'}):
            with self.assertRaises(BuyerError) as denied:
                self.trade.erase_user_personal_data(self.read_user(busy_id), empty_id, request)
            self.assertEqual(denied.exception.status, 403)
            with self.assertRaises(BuyerError) as denied:
                self.trade.erase_user_personal_data(self.read_user(admin_id), empty_id,
                    {**request,'confirmEmail':'wrong@example.com'})
            self.assertEqual(denied.exception.status, 409)
            with self.assertRaises(BuyerError) as denied:
                self.trade.erase_user_personal_data(self.read_user(admin_id), busy_id,
                    {**request,'confirmEmail':'erase-busy@example.com'})
            self.assertEqual(denied.exception.status, 409)
            with self.assertRaises(BuyerError) as denied:
                self.trade.erase_user_personal_data(self.read_user(admin_id), draft_id,
                    {**request,'confirmEmail':'erase-draft@example.com'})
            self.assertEqual(denied.exception.status, 409)
            result = self.trade.erase_user_personal_data(self.read_user(admin_id), empty_id, request)
        self.assertTrue(result['personalDataErased'])
        with self.auth.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM users WHERE id=?', (empty_id,)).fetchone())
            self.assertIsNone(db.execute('SELECT 1 FROM email_identities WHERE email=?', ('erase-empty@example.com',)).fetchone())
            self.assertIsNone(db.execute('PRAGMA foreign_key_check').fetchone())
            self.assertEqual(db.execute("SELECT count(*) FROM trade_audit WHERE action='USER_PERSONAL_DATA_ERASED' AND entity_id=?", (empty_id,)).fetchone()[0], 1)
            self.assertIsNotNone(db.execute('SELECT 1 FROM users WHERE id=?', (busy_id,)).fetchone())
        with self.assertRaises(ApiError):
            self.auth.user_for_token(token)

    def test_admin_account_actions_reject_buyer_and_cross_origin_http(self):
        admin_id=self.account('http-admin',role='PLATFORM_ADMIN')
        target=self.account('http-target')
        class LocalHandler(Handler):
            pass
        LocalHandler.service=self.auth
        LocalHandler.trade=self.trade
        LocalHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1',0),LocalHandler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        tokens={name:self.auth.session_for_user(name)['access_token'] for name in (admin_id,target)}
        path=f'/autolink/admin/users/{target}/erase-personal-data'
        body={'confirmEmail':'http-target@example.com','confirmation':'DELETE','reasonCode':'USER_REQUEST'}
        def call(actor,origin='https://autolinkglobal.com'):
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                data=json.dumps(body).encode(),headers={'Content-Type':'application/json',
                'Origin':origin,'Cookie':'autolink_session='+tokens[actor]})
            try:response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:response=error
            with response:return response.status
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL':'http-admin@example.com'}):
            self.assertEqual(call(target),403)
            self.assertEqual(call(admin_id,'https://untrusted.example'),403)
            self.assertEqual(call(admin_id),200)
        with self.auth.connect() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM users WHERE id=?',(target,)).fetchone())


if __name__ == "__main__":
    unittest.main()
