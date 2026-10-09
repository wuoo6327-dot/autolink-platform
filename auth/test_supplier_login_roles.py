"""Supplier entry repairs legacy roles without granting reviewed business access.

All accounts and provider responses are synthetic and use an isolated SQLite DB.
"""

import tempfile
import time
import unittest
import uuid
from pathlib import Path

from app import ApiError, AuthService
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
            self.trade.save_application(self.read_user(account_id), {
                "companyName": "Existing registered company", "registrationNo": "SYNTHETIC-REG-001",
                "country": "Hong Kong", "address": "Existing company address",
                "contactName": "Existing sales contact", "contactPhone": "+85200000000"})
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

    def test_supplier_entry_preserves_legacy_identity_and_business_data_for_each_provider(self):
        for method in ("password", "code", "google"):
            with self.subTest(provider=method):
                account_id = self.account(method, google=method == "google", application=True)
                before = self.preserved_data(account_id)
                result = self.login(method, method, "MERCHANT")
                user = self.auth.user_for_token(result["access_token"])
                self.assertEqual((user["id"], user["role"], result["role"]), (account_id, "MERCHANT", "MERCHANT"))
                self.assertEqual(self.preserved_data(account_id), before)
                # A second login from the buyer page cannot downgrade the supplier.
                if method == "code":
                    with self.auth.connect() as db:
                        db.execute("UPDATE email_verification_codes SET created_at=0 WHERE email=?", (method + "@example.com",))
                again = self.login(method, method, "BUYER")
                self.assertEqual(again["role"], "MERCHANT")
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
        account_id = self.account("applicant", application=True)
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
        staff = self.account("sales", application=True)
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


if __name__ == "__main__":
    unittest.main()
