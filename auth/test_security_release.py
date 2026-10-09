"""Authorization regressions use synthetic users and temporary SQLite only."""
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app import ApiError, AuthService
from buyer_service import BuyerError, BuyerService
from email_auth import EmailAuthService
from platform_service import PlatformService
from trade_service import TradeService
import image_service


class SecurityReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        owner_env = patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': ''})
        owner_env.start(); self.addCleanup(owner_env.stop)
        self.image_root = Path(self.temp.name) / 'images'
        images = patch.object(image_service, 'ROOT', self.image_root)
        images.start(); self.addCleanup(images.stop)
        self.auth = AuthService(Path(self.temp.name) / 'test.sqlite3', 'synthetic-client', verifier=lambda *_: {})
        self.email = EmailAuthService(self.auth, sender=lambda *_: None)
        self.buyer = BuyerService(self.auth)
        self.trade = TradeService(self.auth)
        self.tokens = {}
        now = int(time.time())
        for name, role in (('buyer', 'BUYER'), ('legacy', 'MERCHANT'), ('supplier', 'SUPPLIER'),
                           ('admin', 'PLATFORM_ADMIN'), ('other-admin', 'PLATFORM_ADMIN')):
            with self.auth.connect() as db:
                db.execute("INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) VALUES (?,?,?,?,?,?,?)",
                           (name, name+'@example.com', name, 'Synthetic '+name, role, now, now))
            self.tokens[name] = self.auth.session_for_user(name)['access_token']

    def user(self, name):
        return self.auth.user_for_token(self.tokens[name])

    def approved(self, name='buyer'):
        self.trade.save_application(self.user(name), {'companyName': 'Synthetic company', 'registrationNo': 'QA-REG',
            'country': 'China', 'address': 'Synthetic warehouse', 'contactName': 'QA', 'contactPhone': '+860000'})
        # Synthetic fixture approval bypasses workflows covered by separate suites.
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET status='APPROVED' WHERE supplier_id=?", (name,))
            db.execute("UPDATE supplier_profiles SET published=1 WHERE user_id=?", (name,))
        return self.user(name)

    def private_image(self):
        owner = self.approved()
        listing = self.trade.save_vehicle(owner, {'modelId': 'zeekr-9x-2026', 'modelYear': 2026,
                                                  'priceMinor': 100000, 'stock': 2, 'moq': 1,
                                                  'originPort': 'Synthetic port', 'validUntil': '2099-01-01'})
        stored = 'synthetic-private.jpg'
        self.image_root.mkdir(exist_ok=True)
        (self.image_root/stored).write_bytes(b'SYNTHETIC PRIVATE IMAGE')
        with self.auth.connect() as db:
            db.execute("INSERT INTO vehicle_images(id,listing_id,supplier_id,filename,stored_name,bytes,width,height,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       ('image', listing['id'], 'buyer', stored, stored, 23, 100, 100, int(time.time())))
        return owner

    def test_private_images_recheck_owner_email_and_account_revocation(self):
        owner = self.private_image()
        stale_admin = self.user('admin')
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': ' ADMIN@EXAMPLE.COM '}):
            self.assertEqual(self.trade.images.bytes('image', owner), b'SYNTHETIC PRIVATE IMAGE')
            self.assertEqual(self.trade.images.bytes('image', stale_admin), b'SYNTHETIC PRIVATE IMAGE')
            for user in (None, self.user('legacy'), self.user('other-admin')):
                with self.subTest(user=user and user['id']), self.assertRaises(BuyerError) as denied:
                    self.trade.images.bytes('image', user)
                self.assertEqual(denied.exception.status, 404)
            with self.auth.connect() as db: db.execute("UPDATE users SET status='SUSPENDED' WHERE id='admin'")
            with self.assertRaises(BuyerError): self.trade.images.bytes('image', stale_admin)

    def test_platform_owner_cannot_delete_with_other_admins_or_role_changes(self):
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': ' ADMIN@EXAMPLE.COM '}):
            for role in ('PLATFORM_ADMIN', 'BUYER'):
                with self.auth.connect() as db: db.execute("UPDATE users SET role=? WHERE id='admin'", (role,))
                self.assertFalse(self.auth.account_deletion_allowed(self.user('admin')))
                with self.assertRaises(ApiError) as denied: self.auth.delete_account(self.tokens['admin'])
                self.assertEqual(denied.exception.status, 403)
                self.assertEqual(self.user('admin')['status'], 'ACTIVE')

    def test_last_active_admin_is_protected(self):
        with self.auth.connect() as db: db.execute("UPDATE users SET status='SUSPENDED' WHERE id='other-admin'")
        self.assertFalse(self.auth.account_deletion_allowed(self.user('admin')))
        with self.assertRaises(ApiError) as denied: self.auth.delete_account(self.tokens['admin'])
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(self.user('admin')['status'], 'ACTIVE')

    def test_concurrent_admin_deletions_leave_one_active_admin(self):
        def delete(name):
            try:
                self.auth.delete_account(self.tokens[name]); return 200
            except ApiError as exc: return exc.status
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(delete, ('admin', 'other-admin'))), [200, 403])
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM users WHERE role='PLATFORM_ADMIN' AND status='ACTIVE' AND deleted_at IS NULL").fetchone()[0], 1)

    def test_business_deletion_revokes_sessions_and_preserves_records(self):
        self.approved('legacy')
        self.assertTrue(self.auth.account_deletion_allowed(self.user('legacy')))
        second = self.auth.session_for_user('legacy')['access_token']
        self.assertTrue(self.auth.delete_account(self.tokens['legacy'])['deleted'])
        for token in (self.tokens['legacy'], second):
            with self.assertRaises(ApiError): self.auth.user_for_token(token)
        with self.auth.connect() as db:
            row = db.execute("SELECT role,status,deleted_at FROM users WHERE id='legacy'").fetchone()
            self.assertEqual((row['role'], row['status']), ('MERCHANT', 'DELETED'))
            self.assertIsNotNone(row['deleted_at'])
            self.assertEqual(db.execute("SELECT count(*) FROM supplier_applications WHERE supplier_id='legacy'").fetchone()[0], 1)
        with self.assertRaises(ApiError): self.auth.delete_account('invalid-synthetic-token')

