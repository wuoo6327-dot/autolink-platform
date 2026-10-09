"""Append-only admin comparisons. Merchant prices are never changed here."""
import hashlib
import json
import os
import time
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit

from buyer_service import BuyerError, text


SNAPSHOT_FIELDS = ('supplier_id', 'model_id', 'trim', 'model_year', 'energy_type', 'steering',
    'vehicle_condition', 'price_minor', 'currency', 'moq', 'stock', 'origin_port', 'location',
    'lead_time', 'incoterm', 'payment_terms', 'vin_available', 'colors', 'export_markets', 'valid_until')


class PriceReviews:
    def __init__(self, auth):
        self.auth = auth
        with auth.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS vehicle_price_reviews (
                id TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES supplier_vehicles(id),
                supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                reviewer_user_id TEXT NOT NULL REFERENCES users(id),
                listing_snapshot TEXT NOT NULL, listing_sha256 TEXT NOT NULL,
                reference_price_minor INTEGER NOT NULL CHECK(reference_price_minor>0),
                currency TEXT NOT NULL, incoterm TEXT NOT NULL, source_name TEXT NOT NULL,
                source_url TEXT NOT NULL, observed_on TEXT NOT NULL, reference_spec TEXT NOT NULL,
                review_note TEXT NOT NULL, created_at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS vehicle_price_reviews_listing ON vehicle_price_reviews(listing_id,created_at);
            ''')

    @staticmethod
    def admin(db, user):
        owner = os.environ.get('PLATFORM_ADMIN_EMAIL', '').strip().lower()
        row = db.execute("SELECT role,email FROM users WHERE id=? AND status='ACTIVE' AND deleted_at IS NULL", (user['id'],)).fetchone()
        if not row or row['role'] != 'PLATFORM_ADMIN' or (owner and row['email'].strip().lower() != owner):
            raise BuyerError(403, 'Platform admin required.')

    @staticmethod
    def snapshot(row):
        body = json.dumps({key: row[key] for key in SNAPSHOT_FIELDS}, sort_keys=True, separators=(',', ':'))
        return body, hashlib.sha256(body.encode()).hexdigest()

    @staticmethod
    def decorate(row, current_hash):
        result = dict(row)
        snapshot = json.loads(result.pop('listing_snapshot'))
        gap = (Decimal(result['reference_price_minor'] - snapshot['price_minor']) * 100 / result['reference_price_minor']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        result['listing_price_minor'] = snapshot['price_minor']
        result['discount_percent'] = float(gap)
        result['within_target'] = Decimal(5) <= (Decimal(result['reference_price_minor'] - snapshot['price_minor']) * 100 / result['reference_price_minor']) <= Decimal(10)
        result['current'] = result.pop('listing_sha256') == current_hash
        return result

    def history(self, admin, listing_id):
        with self.auth.connect() as db:
            self.admin(db, admin)
            listing = db.execute('SELECT * FROM supplier_vehicles WHERE id=?', (listing_id,)).fetchone()
            if not listing:
                raise BuyerError(404, 'Vehicle listing not found.')
            _, digest = self.snapshot(listing)
            rows = db.execute('SELECT * FROM vehicle_price_reviews WHERE listing_id=? ORDER BY rowid DESC LIMIT 50', (listing_id,)).fetchall()
            return [self.decorate(row, digest) for row in rows]

    def record(self, admin, listing_id, body):
        amount = body.get('referencePriceMinor')
        if isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= 10**12:
            raise BuyerError(400, 'Invalid market reference price.')
        if body.get('comparableConfirmed') is not True:
            raise BuyerError(400, 'Confirm matching vehicle configuration, currency and trade terms.')
        source = text(body.get('sourceName'), 'reference source', 300, True)
        url = text(body.get('sourceUrl'), 'reference URL', 1000)
        if url:
            try:
                parsed = urlsplit(url)
            except ValueError as exc:
                raise BuyerError(400, 'Invalid reference URL.') from exc
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise BuyerError(400, 'Invalid reference URL.')
        spec = text(body.get('referenceSpec'), 'comparable configuration', 2000, True)
        note = text(body.get('reviewNote'), 'price review note', 1000)
        try:
            observed = date.fromisoformat(body.get('observedOn', ''))
        except (ValueError, TypeError):
            raise BuyerError(400, 'Invalid reference date.')
        if observed > date.today():
            raise BuyerError(400, 'Reference date cannot be in the future.')
        now = int(time.time())
        ident = 'PRC-' + uuid.uuid4().hex[:16].upper()
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.admin(db, admin)
            row = db.execute("SELECT * FROM supplier_vehicles WHERE id=? AND archived_at IS NULL AND status='PENDING_REVIEW'", (listing_id,)).fetchone()
            if not row:
                raise BuyerError(404, 'Reviewable vehicle listing not found.')
            if body.get('currency') != row['currency'] or body.get('incoterm') != row['incoterm']:
                raise BuyerError(400, 'Reference currency and Incoterm must match the listing.')
            snapshot, digest = self.snapshot(row)
            db.execute('INSERT INTO vehicle_price_reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident, listing_id, row['supplier_id'], admin['id'], snapshot, digest, amount,
                 row['currency'], row['incoterm'], source, url, observed.isoformat(), spec, note, now))
            db.execute('INSERT INTO trade_audit VALUES (?,?,?,?,?,?,?,?)',
                ('AUD-'+uuid.uuid4().hex[:16].upper(), admin['id'], row['supplier_id'], 'VEHICLE_PRICE_REVIEW_RECORDED', 'vehicle', listing_id, now, json.dumps({'priceReviewId':ident})))
        return next(item for item in self.history(admin, listing_id) if item['id'] == ident)

    def require_current(self, db, listing, review_id, reason):
        row = db.execute('SELECT * FROM vehicle_price_reviews WHERE id=? AND listing_id=?', (review_id, listing['id'])).fetchone()
        _, digest = self.snapshot(listing)
        if not row or row['listing_sha256'] != digest:
            raise BuyerError(409, 'Record a current market price comparison before approval.')
        result = self.decorate(row, digest)
        if not result['within_target'] and not reason:
            raise BuyerError(400, 'Explain the manual approval outside the 5–10% reference range.')
        return result
