"""Versioned online agreement confirmations, separate from supplier approval."""
import hashlib
import json
import time
import uuid
from pathlib import Path

from buyer_service import BuyerError


class SupplierAgreementService:
    def __init__(self, auth):
        self.auth = auth
        self.document = json.loads(Path(__file__).with_name('supplier-agreement.json').read_text())
        if hashlib.sha256(self.document['body'].encode()).hexdigest() != self.document['bodySha256']:
            raise RuntimeError('Supplier agreement content hash mismatch.')
        with auth.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS supplier_agreement_versions (
                    version TEXT PRIMARY KEY, body_sha256 TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL, document_status TEXT NOT NULL,
                    language TEXT NOT NULL, body TEXT NOT NULL, created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS supplier_agreement_confirmations (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES users(id),
                    actor_user_id TEXT NOT NULL REFERENCES users(id),
                    version TEXT NOT NULL REFERENCES supplier_agreement_versions(version),
                    company_name TEXT NOT NULL, registration_no TEXT NOT NULL,
                    address TEXT NOT NULL, confirmed_email TEXT NOT NULL,
                    confirmed_name TEXT NOT NULL, verification_method TEXT NOT NULL,
                    privacy_version TEXT NOT NULL, accepted_at INTEGER NOT NULL,
                    UNIQUE(supplier_id,version)
                );
                CREATE TABLE IF NOT EXISTS supplier_agreement_confirmation_revisions (
                    id TEXT PRIMARY KEY, confirmation_id TEXT NOT NULL REFERENCES supplier_agreement_confirmations(id),
                    actor_user_id TEXT NOT NULL REFERENCES users(id), company_name TEXT NOT NULL,
                    registration_no TEXT NOT NULL, address TEXT NOT NULL,
                    confirmed_email TEXT NOT NULL, confirmed_name TEXT NOT NULL, accepted_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS agreement_revision_parent ON supplier_agreement_confirmation_revisions(confirmation_id,accepted_at);
            ''')
            doc = self.document
            existing = db.execute('SELECT body_sha256,source_sha256,body,document_status FROM supplier_agreement_versions WHERE version=?',
                                  (doc['version'],)).fetchone()
            if existing and tuple(existing) != (doc['bodySha256'], doc['sourceSha256'], doc['body'], doc['status']):
                raise RuntimeError('An existing supplier agreement version cannot be rewritten.')
            db.execute('INSERT OR IGNORE INTO supplier_agreement_versions VALUES (?,?,?,?,?,?,?)',
                       (doc['version'], doc['bodySha256'], doc['sourceSha256'], doc['status'],
                        doc['language'], doc['body'], int(time.time())))

    @staticmethod
    def owner(user):
        if (user.get('supplier_role', 'OWNER') != 'OWNER' or
                user.get('actor_user_id', user['id']) != user['id']):
            raise BuyerError(403, 'Only the company owner can confirm this agreement.')

    def effective(self, db, supplier_id):
        row = db.execute('SELECT * FROM supplier_agreement_confirmations WHERE supplier_id=? AND version=?',
                         (supplier_id, self.document['version'])).fetchone()
        if not row:
            return None
        result = dict(row)
        revision = db.execute('SELECT * FROM supplier_agreement_confirmation_revisions WHERE confirmation_id=? ORDER BY rowid DESC LIMIT 1', (row['id'],)).fetchone()
        if revision:
            result.update(dict(revision))
        return result

    def matching(self, db, supplier_id, company_name, registration_no, address):
        row = self.effective(db, supplier_id)
        if row and (row['company_name'], row['registration_no'], row['address']) == (company_name, registration_no, address):
            return {key: row[key] for key in ('id', 'version', 'company_name', 'accepted_at')}
        return None

    def require_current(self, db, supplier_id, company_name, registration_no, address):
        record = self.matching(db, supplier_id, company_name, registration_no, address)
        if not record:
            raise BuyerError(409, 'Save company details and confirm the current supplier agreement before submitting.')
        return record

    def current(self, user):
        self.owner(user)
        with self.auth.connect() as db:
            company = db.execute('SELECT u.company_name,a.registration_no,a.address FROM users u JOIN supplier_applications a ON a.supplier_id=u.id WHERE u.id=?', (user['id'],)).fetchone()
            row = self.matching(db, user['id'], *tuple(company)) if company else None
        return {'version': self.document['version'], 'bodySha256': self.document['bodySha256'],
                'documentStatus': self.document['status'],
                'confirmation': row, 'needsReconfirmation': bool(company and not row)}

    def confirm(self, user, body):
        self.owner(user)
        fields = {'version', 'bodySha256', 'consent', 'privacyAcknowledged', 'authorized'}
        if not isinstance(body, dict) or set(body) != fields:
            raise BuyerError(400, 'Invalid agreement confirmation fields.')
        if any(body.get(key) is not True for key in ('consent', 'privacyAcknowledged', 'authorized')):
            raise BuyerError(400, 'Confirm your authorization, the agreement and the privacy policy.')
        if body['version'] != self.document['version'] or body['bodySha256'] != self.document['bodySha256']:
            raise BuyerError(409, 'Agreement version changed. Reload before confirming.')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            actor = db.execute("SELECT * FROM users WHERE id=? AND status='ACTIVE' AND deleted_at IS NULL AND email_verified_at IS NOT NULL AND is_test_workspace=0 AND role IN ('BUYER','MERCHANT','SUPPLIER')", (user['id'],)).fetchone()
            if not actor:
                raise BuyerError(403, 'A verified active supplier account is required.')
            application = db.execute('SELECT registration_no,address,status FROM supplier_applications WHERE supplier_id=?', (user['id'],)).fetchone()
            if (not application or not actor['company_name'] or not application['registration_no'] or
                    not application['address'] or application['status'] == 'SUSPENDED'):
                raise BuyerError(409, 'Save your company name, registration number and address before confirming.')
            prior = self.effective(db, user['id'])
            matching = self.matching(db, user['id'], actor['company_name'], application['registration_no'], application['address'])
            if not matching:
                now = int(time.time())
                ident = 'AGR-' + uuid.uuid4().hex[:16].upper()
                if prior:
                    parent = prior.get('confirmation_id', prior['id'])
                    db.execute('INSERT INTO supplier_agreement_confirmation_revisions VALUES (?,?,?,?,?,?,?,?,?)',
                               (ident, parent, actor['id'], actor['company_name'], application['registration_no'], application['address'], actor['email'], actor['display_name'], now))
                else:
                    db.execute('INSERT INTO supplier_agreement_confirmations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                           (ident, user['id'], actor['id'], self.document['version'], actor['company_name'],
                            application['registration_no'], application['address'], actor['email'],
                            actor['display_name'], 'VERIFIED_EMAIL_SESSION', '1.0', now))
                db.execute('INSERT INTO trade_audit VALUES (?,?,?,?,?,?,?,?)',
                           ('AUD-' + uuid.uuid4().hex[:16].upper(), actor['id'], user['id'],
                            'SUPPLIER_AGREEMENT_CONFIRMED', 'agreement', ident, now,
                            json.dumps({'version': self.document['version'], 'bodySha256': self.document['bodySha256'],
                                        'documentStatus': self.document['status']}, separators=(',', ':'))))
        return self.current(user)
