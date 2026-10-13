"""Exact supplier aggregates, read-only reporting and fresh assignment isolation."""
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from app import Handler
from buyer_service import BuyerError
import test_trade


class SupplierOverviewTests(unittest.TestCase):
    approved_vehicle = test_trade.TradeFlowTests.approved_vehicle

    def setUp(self):
        test_trade.TradeFlowTests.setUp(self)
        with self.auth.connect() as db:
            db.execute("UPDATE users SET role='MERCHANT' WHERE id='buyer-b'")
        self.users['buyer-b']=self.auth.user_for_token(self.auth.session_for_user('buyer-b')['access_token'])
        self.listing = self.approved_vehicle()
        self.owner = self.users['supplier-a']
        self.buyer = self.users['buyer-a']
        self.inquiry = self.trade.create_inquiry(self.buyer, {
            'listingId': self.listing, 'quantity': 2, 'destinationCountry': 'Saudi Arabia'})

    def quote(self, **extra):
        return self.trade.create_quote(self.owner, self.inquiry['id'], {
            'unitPriceMinor': 1850000, 'validUntil': str(date.today() + timedelta(days=2)), **extra})

    def sales(self):
        recipient = self.users['buyer-b']
        invitation = self.trade.team.invite(self.owner, {'email': recipient['email']})
        self.trade.team.accept(recipient, invitation['id'])
        return self.trade.team.principal(recipient, self.owner['id'], approved=True)

    @staticmethod
    def copy_row(db, table, source_id, new_id, **changes):
        # Isolated fixture cloning bypasses anti-spam limits to exercise >200 rows.
        row = dict(db.execute(f'SELECT * FROM {table} WHERE id=?', (source_id,)).fetchone())
        row.update(id=new_id, **changes)
        columns = ','.join(row)
        db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))

    def test_exact_counts_exceed_list_cap_and_only_actually_sent_quotes_count(self):
        sent = self.quote(send=True)
        draft = self.quote()
        now = int(time.time())
        with self.auth.connect() as db:
            for n in range(204):
                self.copy_row(db, 'supplier_vehicles', self.listing, 'VEH-BULK-'+str(n), status='DRAFT')
                self.copy_row(db, 'trade_quotes', draft['id'], 'QUO-BULK-'+str(n))
            self.copy_row(db, 'supplier_vehicles', self.listing, 'VEH-REVIEW', status='PENDING_REVIEW')
            self.copy_row(db, 'supplier_vehicles', self.listing, 'VEH-ARCHIVED', status='ARCHIVED', archived_at=now)
            for n in range(205):
                self.copy_row(db, 'buyer_inquiries', self.inquiry['id'], 'INQ-BULK-'+str(n), status='CLOSED')
            db.execute("UPDATE trade_quotes SET status='CANCELLED' WHERE id=?", (draft['id'],))
            self.copy_row(db, 'trade_quotes', sent['id'], 'QUO-CANCELLED-SENT', status='CANCELLED')
            self.copy_row(db, 'trade_quotes', sent['id'], 'QUO-EXPIRED', valid_until=str(date.today()-timedelta(days=1)))
            self.copy_row(db, 'trade_quotes', sent['id'], 'QUO-ARCHIVED', archived_at=now)
        self.assertEqual(len(self.trade.supplier_inquiries(self.owner)), 200)
        report = self.trade.supplier_overview(self.owner)
        self.assertEqual(report['counts'], {'inquiries': 206, 'activeInquiries': 1, 'sentQuotes': 3,
            'acceptedIntents': 0, 'buyers': 1, 'vehicles': 206, 'pendingVehicleReviews': 1, 'onlineVehicles': 1})
        self.assertEqual(report['quoteStatuses']['DRAFT'], 204)
        self.assertEqual(report['quoteStatuses']['CANCELLED'], 2)
        self.assertEqual(report['quoteStatuses']['EXPIRED'], 1)
        self.assertEqual(report['quoteStatuses']['SENT'], 1)
        self.assertEqual(report['vehicleStatuses']['ARCHIVED'], 1)
        self.assertEqual(report['inquiryStatuses']['CLOSED'], 205)
        self.assertEqual(len(report['recentInquiries']), 5)

    def test_reporting_uses_real_event_times_and_does_not_mutate_read_state(self):
        sent = self.quote(send=True)
        draft = self.quote()
        self.trade.update_crm(self.owner, self.buyer['id'], {'status': 'HIGH_INTENT', 'note': 'Private follow-up'})
        now = int(time.time())
        since = now-30*86400
        with self.auth.connect() as db:
            db.execute('UPDATE buyer_inquiries SET created_at=? WHERE id=?', (since, self.inquiry['id']))
            self.copy_row(db, 'buyer_inquiries', self.inquiry['id'], 'INQ-OLD', created_at=since-1)
            self.copy_row(db, 'buyer_inquiries', self.inquiry['id'], 'INQ-FUTURE', created_at=now+1)
            self.copy_row(db, 'trade_quotes', sent['id'], 'QUO-OLD', sent_at=since-1)
            self.copy_row(db, 'trade_quotes', sent['id'], 'QUO-FUTURE', sent_at=now+1)
            db.execute('UPDATE trade_quotes SET created_at=?,sent_at=?,valid_until=? WHERE id=?',
                (since-100, now, str(date.today()-timedelta(days=1)), sent['id']))
            note = db.execute('SELECT id FROM supplier_crm_notes').fetchone()[0]
            db.execute('UPDATE supplier_crm_notes SET created_at=? WHERE id=?', (since, note))
            self.copy_row(db, 'supplier_crm_notes', note, 'NOTE-OLD', created_at=since-1)
            self.copy_row(db, 'supplier_crm_notes', note, 'NOTE-FUTURE', created_at=now+1)
            before = [tuple(r) for r in db.execute('SELECT id,status,viewed_at,updated_at FROM trade_quotes ORDER BY id')]
            inquiry_before = tuple(db.execute('SELECT status,viewed_at,updated_at FROM buyer_inquiries WHERE id=?', (self.inquiry['id'],)).fetchone())
        with patch('trade_service.time.time', return_value=now):
            report = self.trade.supplier_overview(self.owner)
        self.assertEqual(report['period'], {'from': since, 'until': now, 'inquiriesReceived': 1, 'quotesSent': 1, 'followUpNotes': 1})
        self.assertEqual(report['quoteStatuses']['EXPIRED'], 1)
        self.assertEqual(report['quoteStatuses']['DRAFT'], 1)
        self.assertEqual(report['customerStatuses']['HIGH_INTENT'], 1)
        with self.auth.connect() as db:
            self.assertEqual(before, [tuple(r) for r in db.execute('SELECT id,status,viewed_at,updated_at FROM trade_quotes ORDER BY id')])
            self.assertEqual(inquiry_before, tuple(db.execute('SELECT status,viewed_at,updated_at FROM buyer_inquiries WHERE id=?', (self.inquiry['id'],)).fetchone()))
        self.assertNotIn('Private follow-up', json.dumps(report))

    def test_sales_assignment_and_company_isolation_are_live(self):
        self.approved_vehicle('supplier-b')
        other = self.trade.supplier_overview(self.users['supplier-b'])
        self.assertEqual(other['counts']['inquiries'], 0)
        self.assertEqual(other['recentInquiries'], [])
        sales = self.sales()
        self.quote(send=True)
        self.trade.update_crm(self.owner, 'buyer-a', {'status': 'FOLLOW_UP', 'note': 'Owned note'})
        report = self.trade.supplier_overview(sales)
        self.assertEqual(report['scope'], 'ASSIGNED')
        self.assertEqual(report['counts'], {'inquiries': 0, 'activeInquiries': 0, 'sentQuotes': 0, 'acceptedIntents': 0, 'buyers': 0})
        self.assertIsNone(report['vehicleStatuses'])
        self.assertNotIn('vehicles', report['counts'])
        self.trade.team.assign(self.owner, 'buyer-a', {'userId': 'buyer-b'})
        report = self.trade.supplier_overview(sales)
        self.assertEqual(report['counts']['inquiries'], 1)
        self.assertEqual(report['counts']['sentQuotes'], 1)
        self.assertEqual(report['counts']['buyers'], 1)
        self.assertEqual(report['period']['followUpNotes'], 1)
        self.assertEqual(report['recentInquiries'][0]['id'], self.inquiry['id'])
        self.trade.team.assign(self.owner, 'buyer-a', {'userId': ''})
        self.assertEqual(self.trade.supplier_overview(sales)['counts']['inquiries'], 0)
        self.trade.team.remove(self.owner, 'buyer-b')
        with self.assertRaises(BuyerError) as denied:
            self.trade.supplier_overview(sales)
        self.assertEqual(denied.exception.status, 403)

    def test_fresh_owner_and_sales_revocation_deny_stale_principals(self):
        sales = self.sales()
        now = int(time.time())
        for account, changes in (
            ('supplier-a', ["status='SUSPENDED'", "role='BUYER'", 'deleted_at=1', 'email_verified_at=NULL']),
            ('buyer-b', ["status='SUSPENDED'", "role='BUYER'", "role='PLATFORM_ADMIN'", 'deleted_at=1', 'email_verified_at=NULL']),
        ):
            for change in changes:
                with self.subTest(account=account, change=change):
                    with self.auth.connect() as db:
                        db.execute(f'UPDATE users SET {change} WHERE id=?', (account,))
                    for principal in ([self.owner, sales] if account=='supplier-a' else [sales]):
                        with self.assertRaises(BuyerError) as denied:
                            self.trade.supplier_overview(principal)
                        self.assertEqual(denied.exception.status, 403)
                    with self.auth.connect() as db:
                        db.execute("UPDATE users SET status='ACTIVE',role=?,deleted_at=NULL,email_verified_at=? WHERE id=?",
                            ('MERCHANT', now, account))
        with self.auth.connect() as db:
            db.execute("UPDATE supplier_applications SET status='SUSPENDED' WHERE supplier_id='supplier-a'")
        for principal in (self.owner, sales):
            with self.assertRaises(BuyerError):
                self.trade.supplier_overview(principal)

    def test_http_requires_verified_approved_workspace_and_no_sensitive_fields(self):
        self.approved_vehicle('supplier-b')
        self.sales()
        class TestHandler(Handler):
            pass
        TestHandler.service=self.auth
        TestHandler.trade=self.trade
        TestHandler.platform=self.trade.platform
        server=ThreadingHTTPServer(('127.0.0.1', 0), TestHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def get(account=None, company=None):
            headers={}
            if account:
                headers['Cookie']='autolink_session='+self.auth.session_for_user(account)['access_token']
            if company:
                headers['X-Autolink-Supplier']=company
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/autolink/supplier/overview', headers=headers)
            try:
                response=urllib.request.urlopen(request)
            except urllib.error.HTTPError as error:
                response=error
            with response:
                return response.status, json.loads(response.read()), response.headers
        self.assertEqual(get()[0], 401)
        self.assertEqual(get('buyer-a')[0], 403)
        self.assertEqual(get('supplier-b','supplier-a')[0], 404)
        code, body, headers=get('supplier-a')
        self.assertEqual(code, 200)
        self.assertIn('no-store', headers['Cache-Control'])
        self.assertEqual(body['data']['counts']['inquiries'], 1)
        self.assertEqual(get('buyer-b','supplier-a')[1]['data']['scope'], 'ASSIGNED')
        for forbidden in ('email','password','token','review_reason','address','note','assigned_to'):
            self.assertNotIn('"'+forbidden+'"', json.dumps(body))
        self.trade.team.remove(self.owner, 'buyer-b')
        self.assertNotEqual(get('buyer-b','supplier-a')[0], 200)


if __name__=='__main__':
    unittest.main()
