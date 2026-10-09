import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import ApiError, AuthService, digest
from email_auth import EmailAuthService


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.claims = {}

        def verify(credential, audience):
            self.assertEqual(audience, "test-client.apps.googleusercontent.com")
            return self.claims[credential]

        self.service = AuthService(
            Path(self.temp.name) / "users.sqlite3",
            "test-client.apps.googleusercontent.com",
            verifier=verify,
        )

        EmailAuthService(self.service, sender=lambda *_: None)

    def tearDown(self):
        self.temp.cleanup()

    def credential(self, nonce, sub="google-sub-1", email="person@gmail.com", verified=True):
        credential = "token-" + str(len(self.claims)) + "x" * 130
        self.claims[credential] = {
            "sub": sub, "email": email, "name": "Example Person",
            "email_verified": verified, "nonce": nonce,
        }
        return credential

    def start(self, sub="google-sub-1", email="person@gmail.com", verified=True):
        nonce = self.service.challenge()["nonce"]
        return {"nonce": nonce, "credential": self.credential(nonce, sub, email, verified)}

    def test_registration_requires_consent_and_creates_session(self):
        first = self.start()
        self.assertEqual(self.service.google_login(first), {"registrationRequired": True})
        self.assertEqual(self.service.google_login({**self.start(), "companyName": "", "consent": False}),
                         {"registrationRequired": True})
        registered = self.service.google_login({**self.start(), "companyName": "  Example Motors  ", "consent": True})
        token = registered["access_token"]
        user = self.service.user_for_token(token)
        self.assertEqual(user["google_sub"], "google-sub-1")
        self.assertEqual(user["company_name"], "Example Motors")
        with self.service.connect() as db:
            consent = db.execute("SELECT terms_version,privacy_version,accepted_at FROM consents WHERE user_id=?", (user["id"],)).fetchone()
        self.assertEqual((consent["terms_version"], consent["privacy_version"]), ("1.0", "1.0"))
        self.assertGreater(consent["accepted_at"], 0)
        returning = self.service.google_login(self.start())
        self.assertEqual(self.service.user_for_token(returning["access_token"])["id"], user["id"])
        self.service.logout(token)
        with self.assertRaises(ApiError):
            self.service.user_for_token(token)

    def test_nonce_mismatch_and_replay_are_rejected(self):
        body = self.start()
        with self.assertRaises(ApiError) as mismatch:
            self.service.google_login({**body, "nonce": "different" * 5})
        self.assertEqual(mismatch.exception.status, 401)
        self.assertEqual(self.service.google_login(body), {"registrationRequired": True})
        with self.assertRaises(ApiError) as replay:
            self.service.google_login(body)
        self.assertEqual(replay.exception.status, 401)

    def test_expired_nonce_and_unverified_email_are_rejected(self):
        body = self.start()
        with self.service.connect() as db:
            db.execute("UPDATE challenges SET expires_at=0 WHERE nonce_hash=?", (digest(body["nonce"]),))
        with self.assertRaises(ApiError):
            self.service.google_login(body)
        with self.assertRaises(ApiError):
            self.service.google_login(self.start(verified=False))

    def test_same_verified_email_cannot_create_duplicate_account(self):
        first = self.service.google_login({**self.start(), "companyName": "One", "consent": True})
        with self.assertRaises(ApiError) as raised:
            self.service.google_login({**self.start(sub="google-sub-2"), "companyName": "Two", "consent": True})
        self.assertEqual(raised.exception.status, 409)
        with self.service.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users").fetchone()[0], 1)

    def test_account_deletion_preserves_history_and_revokes_sessions(self):
        first = self.service.google_login({**self.start(), "companyName": "One", "consent": True})
        second = self.service.google_login(self.start())
        user_id = self.service.user_for_token(first["access_token"])["id"]
        self.assertEqual(self.service.delete_account(first["access_token"]), {"deleted": True})
        for token in (first["access_token"], second["access_token"]):
            with self.assertRaises(ApiError):
                self.service.user_for_token(token)
        with self.assertRaises(ApiError):
            self.service.google_login(self.start())
        with self.service.connect() as db:
            row = db.execute("SELECT status,deleted_at FROM users WHERE id=?", (user_id,)).fetchone()
            self.assertEqual(row["status"], "DELETED")
            self.assertIsNotNone(row["deleted_at"])
            self.assertEqual(db.execute("SELECT count(*) FROM consents").fetchone()[0], 1)

    @unittest.skip("Legacy social OAuth draft is not installed or enabled in the production API.")
    def test_social_callback_registration_and_returning_login(self):
        with patch("social.enabled", return_value=True), patch("social.authorization_url", side_effect=lambda p, s, n: "https://provider.test/?state=" + s):
            url = self.service.oauth_start("linkedin")
        state = url.split("state=", 1)[1]
        with patch("social.exchange", return_value={"subject": "li-123", "email": "person@gmail.com", "name": "Example Person"}):
            ticket = self.service.oauth_callback("linkedin", state, "one-time-code")
        with self.assertRaises(ApiError):
            self.service.oauth_callback("linkedin", state, "one-time-code")
        self.assertEqual(self.service.oauth_finish({"ticket": ticket}), {"registrationRequired": True})
        session = self.service.oauth_finish({"ticket": ticket, "companyName": "  Example Motors  ", "consent": True})
        user = self.service.user_for_token(session["access_token"])
        self.assertEqual(user["company_name"], "Example Motors")
        self.assertTrue(user["google_sub"].startswith("unlinked:"))
        with self.assertRaises(ApiError):
            self.service.oauth_finish({"ticket": ticket})
        with patch("social.enabled", return_value=True), patch("social.authorization_url", side_effect=lambda p, s, n: "https://provider.test/?state=" + s):
            state = self.service.oauth_start("linkedin").split("state=", 1)[1]
        with patch("social.exchange", return_value={"subject": "li-123", "email": "person@gmail.com", "name": "Example Person"}):
            ticket = self.service.oauth_callback("linkedin", state, "new-code")
        returning = self.service.oauth_finish({"ticket": ticket})
        self.assertEqual(self.service.user_for_token(returning["access_token"])["id"], user["id"])

    @unittest.skip("Legacy social OAuth draft is not installed or enabled in the production API.")
    def test_same_email_across_providers_does_not_link_accounts(self):
        google = self.service.google_login({**self.start(), "companyName": "Google Co", "consent": True})
        with patch("social.enabled", return_value=True), patch("social.authorization_url", side_effect=lambda p, s, n: "https://provider.test/?state=" + s):
            state = self.service.oauth_start("facebook").split("state=", 1)[1]
        with patch("social.exchange", return_value={"subject": "fb-123", "email": "person@gmail.com", "name": "Example Person"}):
            ticket = self.service.oauth_callback("facebook", state, "code")
        facebook = self.service.oauth_finish({"ticket": ticket, "companyName": "Facebook Co", "consent": True})
        self.assertNotEqual(self.service.user_for_token(google["access_token"])["id"],
                            self.service.user_for_token(facebook["access_token"])["id"])
        self.service.delete_account(facebook["access_token"])
        with self.service.connect() as db:
            self.assertIsNone(db.execute("SELECT * FROM identities WHERE provider='facebook' AND subject='fb-123'").fetchone())


if __name__ == "__main__":
    unittest.main()
