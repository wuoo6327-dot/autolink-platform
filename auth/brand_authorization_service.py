"""Supplier-specific manufacturer authorization claims, separate from company and stock review."""

from datetime import date
import time

from buyer_service import BuyerError, text
from trade_service import ident


TYPES = {
    'AUTHORIZED_DEALER': 'Authorized dealer',
    'AUTHORIZED_EXPORTER': 'Authorized exporter',
    'AUTHORIZED_DISTRIBUTOR': 'Authorized distributor',
}


class BrandAuthorizationService:
    def __init__(self, trade):
        self.trade = trade
        self.auth = trade.auth
        with self.auth.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS supplier_brand_authorizations (
                    id TEXT PRIMARY KEY,
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    brand_id TEXT NOT NULL REFERENCES catalog_brands(id),
                    authorization_type TEXT NOT NULL,
                    holder_legal_name TEXT NOT NULL,
                    issuer_legal_name TEXT NOT NULL,
                    business_scope TEXT NOT NULL,
                    territories TEXT NOT NULL,
                    authorization_chain TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    evidence_document_id TEXT NOT NULL REFERENCES supplier_documents(id),
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    reviewed_by TEXT REFERENCES users(id),
                    reviewed_at INTEGER,
                    review_reason TEXT NOT NULL DEFAULT '',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS supplier_brand_auth_owner
                    ON supplier_brand_authorizations(supplier_id,brand_id,status,valid_until);
            ''')

    @staticmethod
    def _parse_date(value, label):
        if not isinstance(value, str):
            raise BuyerError(400, 'Invalid ' + label + '.')
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise BuyerError(400, 'Invalid ' + label + '.') from exc
        if parsed.isoformat() != value:
            raise BuyerError(400, 'Invalid ' + label + '.')
        return parsed

    def rows(self, supplier_id, public=False):
        with self.auth.connect() as db:
            if public:
                rows = db.execute('''SELECT a.id,a.brand_id,b.name AS brand_name,
                    a.authorization_type,a.business_scope,a.territories,a.valid_from,a.valid_until,
                    d.stored_name
                    FROM supplier_brand_authorizations a
                    JOIN catalog_brands b ON b.id=a.brand_id
                    JOIN supplier_documents d ON d.id=a.evidence_document_id
                    JOIN supplier_profiles p ON p.user_id=a.supplier_id
                    JOIN supplier_applications s ON s.supplier_id=a.supplier_id
                    JOIN users u ON u.id=a.supplier_id
                    WHERE a.supplier_id=? AND a.status='APPROVED'
                      AND a.valid_from<=? AND a.valid_until>=? AND b.active=1
                      AND p.published=1 AND s.status='APPROVED'
                      AND u.status='ACTIVE' AND u.deleted_at IS NULL
                      AND lower(a.holder_legal_name)=lower(u.company_name)
                      AND u.email_verified_at IS NOT NULL AND u.is_test_workspace=0
                    ORDER BY b.name,a.valid_until''', (supplier_id, date.today().isoformat(),
                        date.today().isoformat())).fetchall()
                from trade_service import DOCUMENT_ROOT
                return [{**{key:row[key] for key in row.keys() if key!='stored_name'},
                         'authorization_label': TYPES[row['authorization_type']]}
                        for row in rows if (DOCUMENT_ROOT / row['stored_name']).is_file()]
            rows = db.execute('''SELECT a.*,b.name AS brand_name,d.filename AS evidence_filename
                FROM supplier_brand_authorizations a JOIN catalog_brands b ON b.id=a.brand_id
                JOIN supplier_documents d ON d.id=a.evidence_document_id
                WHERE a.supplier_id=? ORDER BY a.created_at DESC''', (supplier_id,)).fetchall()
            return [dict(row) for row in rows]

    def submit(self, supplier, body):
        if not isinstance(body, dict):
            raise BuyerError(400, 'Invalid authorization claim.')
        allowed = {'brandId','authorizationType','holderLegalName','issuerLegalName',
            'businessScope','territories','authorizationChain','validFrom','validUntil',
            'evidenceDocumentId'}
        if set(body) - allowed:
            raise BuyerError(400, 'Invalid authorization claim fields.')
        brand_id = text(body.get('brandId'), 'brand', 100, True)
        kind = body.get('authorizationType')
        if kind not in TYPES:
            raise BuyerError(400, 'Select the documented authorization type.')
        holder = text(body.get('holderLegalName'), 'authorization holder', 160, True)
        issuer = text(body.get('issuerLegalName'), 'authorization issuer', 160, True)
        scope = text(body.get('businessScope'), 'business scope', 500, True)
        territories = text(body.get('territories'), 'territories', 500, True)
        chain = text(body.get('authorizationChain'), 'authorization chain', 1000, True)
        start = self._parse_date(body.get('validFrom'), 'start date')
        end = self._parse_date(body.get('validUntil'), 'end date')
        if start > end or end < date.today():
            raise BuyerError(400, 'Authorization validity has ended or is reversed.')
        document_id = text(body.get('evidenceDocumentId'), 'evidence document', 100, True)
        claim_id, now = ident('BAU'), int(time.time())
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.trade.active_company_owner(db, supplier)
            company = db.execute('SELECT company_name FROM users WHERE id=?',
                (supplier['id'],)).fetchone()
            if not company or holder.casefold() != company['company_name'].casefold():
                raise BuyerError(400, 'Authorization holder must match the reviewed company legal name.')
            if not db.execute('SELECT 1 FROM catalog_brands WHERE id=? AND active=1',
                    (brand_id,)).fetchone():
                raise BuyerError(400, 'Choose an active catalog brand.')
            evidence = db.execute('''SELECT 1 FROM supplier_documents WHERE id=? AND supplier_id=?
                AND kind='BRAND_AUTHORIZATION' ''', (document_id, supplier['id'])).fetchone()
            if not evidence:
                raise BuyerError(400, 'Upload a private brand authorization document first.')
            if db.execute('''SELECT 1 FROM supplier_brand_authorizations WHERE supplier_id=?
                AND brand_id=? AND status IN ('PENDING','APPROVED')''',
                (supplier['id'],brand_id)).fetchone():
                raise BuyerError(409, 'A pending or approved claim already exists for this brand.')
            db.execute('''INSERT INTO supplier_brand_authorizations
                (id,supplier_id,brand_id,authorization_type,holder_legal_name,
                 issuer_legal_name,business_scope,territories,authorization_chain,
                 valid_from,valid_until,evidence_document_id,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (claim_id,supplier['id'],brand_id,kind,holder,issuer,scope,territories,
                 chain,start.isoformat(),end.isoformat(),document_id,'PENDING',now,now))
            self.trade.audit(db,self.trade.team.actor(supplier),'BRAND_AUTHORIZATION_SUBMITTED',
                'brand_authorization',claim_id,supplier['id'],brand_id)
        return next(row for row in self.rows(supplier['id']) if row['id']==claim_id)

    def review(self, admin, claim_id, body):
        if not isinstance(body, dict) or set(body) - {'decision','reason','evidenceChecked'}:
            raise BuyerError(400, 'Invalid review decision.')
        decision = body.get('decision')
        if decision not in ('APPROVED','REJECTED','REVOKED'):
            raise BuyerError(400, 'Invalid review decision.')
        reason = text(body.get('reason'), 'review reason', 1000)
        if decision in ('REJECTED','REVOKED') and not reason:
            raise BuyerError(400, 'Give a reason for rejection or revocation.')
        if decision == 'APPROVED' and body.get('evidenceChecked') is not True:
            raise BuyerError(400, 'Confirm the issuer, authorization chain, scope, territory and validity evidence.')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.trade.catalog.admin(db, admin)
            row = db.execute('''SELECT a.*,d.stored_name,d.kind FROM supplier_brand_authorizations a
                JOIN supplier_documents d ON d.id=a.evidence_document_id WHERE a.id=?''',
                (claim_id,)).fetchone()
            if not row:
                raise BuyerError(404, 'Authorization claim not found.')
            if decision == 'REVOKED':
                if row['status'] != 'APPROVED':
                    raise BuyerError(409, 'Only an approved authorization can be revoked.')
            elif row['status'] != 'PENDING':
                raise BuyerError(409, 'Only a pending authorization can be reviewed.')
            if decision == 'APPROVED':
                if row['valid_from'] > date.today().isoformat() or row['valid_until'] < date.today().isoformat():
                    raise BuyerError(409, 'Authorization must be currently effective.')
                company = db.execute('''SELECT u.company_name FROM supplier_applications s
                    JOIN users u ON u.id=s.supplier_id WHERE s.supplier_id=? AND s.status='APPROVED'
                    AND u.status='ACTIVE' AND u.deleted_at IS NULL''', (row['supplier_id'],)).fetchone()
                brand = db.execute('SELECT 1 FROM catalog_brands WHERE id=? AND active=1',
                    (row['brand_id'],)).fetchone()
                from trade_service import DOCUMENT_ROOT
                if (not company or company['company_name'].casefold() != row['holder_legal_name'].casefold()
                        or not brand or row['kind'] != 'BRAND_AUTHORIZATION'
                        or not (DOCUMENT_ROOT / row['stored_name']).is_file()):
                    raise BuyerError(409, 'Current company, brand or private evidence failed review gates.')
            now = int(time.time())
            db.execute('''UPDATE supplier_brand_authorizations SET status=?,reviewed_by=?,
                reviewed_at=?,review_reason=?,updated_at=? WHERE id=?''',
                (decision,admin['id'],now,reason,now,claim_id))
            self.trade.audit(db,admin['id'],'BRAND_AUTHORIZATION_'+decision,
                'brand_authorization',claim_id,row['supplier_id'],row['brand_id'])
        return next(item for item in self.rows(row['supplier_id']) if item['id']==claim_id)
