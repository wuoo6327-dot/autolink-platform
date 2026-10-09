"""Owner restriction is checked on every admin HTTP request, not just navigation."""
import os
import unittest
from unittest.mock import patch
import test_trade
import test_pagination


class AdminOwnerTests(unittest.TestCase):
    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        self.patch = patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': ' ADMIN@EXAMPLE.COM '})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def serve(self):
        return test_pagination.BusinessPaginationTests.serve(self)

    def test_owner_only_blocks_other_admins_buyers_suppliers_and_anonymous(self):
        with self.auth.connect() as db:
            db.execute("UPDATE users SET role='PLATFORM_ADMIN' WHERE id='buyer-b'")
        call = self.serve()
        for path in ('/autolink/admin/overview', '/autolink/admin/users?page=1',
                     '/autolink/admin/support?page=1', '/autolink/admin/vehicles?page=1',
                     '/autolink/admin/email', '/autolink/admin/documents/NOT-A-DOCUMENT'):
            for identity in ('buyer-b', 'buyer-a', 'supplier-a', None):
                with self.subTest(path=path, identity=identity):
                    self.assertEqual(call(identity, path)[0], 401 if identity is None else 403)
        self.assertEqual(call('admin', '/autolink/admin/overview')[0], 200)
        self.assertEqual(call('admin', '/autolink/admin/support?page=1')[0], 200)

    def test_current_status_and_role_still_required_and_revocation_is_immediate(self):
        call = self.serve()
        self.assertEqual(call('admin', '/autolink/admin/overview')[0], 200)
        for column, value, restored in (('role', 'BUYER', 'PLATFORM_ADMIN'),
                                         ('status', 'SUSPENDED', 'ACTIVE')):
            with self.auth.connect() as db:
                db.execute(f'UPDATE users SET {column}=? WHERE id=?', (value, 'admin'))
            self.assertIn(call('admin', '/autolink/admin/overview')[0], (401, 403))
            with self.auth.connect() as db:
                db.execute(f'UPDATE users SET {column}=? WHERE id=?', (restored, 'admin'))
        with patch.dict(os.environ, {'PLATFORM_ADMIN_EMAIL': 'different@example.com'}):
            self.assertEqual(call('admin', '/autolink/admin/overview')[0], 403)
        self.assertEqual(call('admin', '/autolink/admin/overview')[0], 200)
