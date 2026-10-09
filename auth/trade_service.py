"""Database-backed supplier listings, inquiries, quotes and reviews.

This extends the live users, supplier_profiles and buyer_inquiries tables.
The maintained catalogue remains model reference data, never an offer of stock.
"""

from __future__ import annotations

import re
import base64
import binascii
import os
import time
import uuid
import json
import ipaddress
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, unquote, quote
from xml.etree import ElementTree

from platform_service import PlatformService
from image_service import ListingImages
from price_review_service import PriceReviews
from verification_service import PHOTO_KINDS, evidence_fields, require_evidence, sanitize_photo
from supplier_agreement_service import SupplierAgreementService
from team_service import SupplierTeam
from catalog_service import CatalogService
from buyer_service import BuyerError, BuyerService, positive_int, text
from email_auth import EmailError, normalized_email
from pagination import query_list, list_items


INQUIRY_STATES = {"SUBMITTED", "VIEWED", "CONTACTED", "QUOTED", "NEGOTIATING", "CLOSED"}
QUOTE_STATES = {"DRAFT", "SENT", "VIEWED", "ACCEPTED", "REJECTED", "EXPIRED", "CANCELLED"}
LISTING_STATES = {"DRAFT", "PENDING_REVIEW", "APPROVED", "REJECTED", "ONLINE", "OFFLINE", "SOLD_OUT", "ARCHIVED"}
TERMS = {"FOB", "CIF", "CFR", "EXW"}
DOCUMENT_ROOT = Path(os.environ.get("SUPPLIER_DOCUMENT_ROOT", "/data/private/supplier-documents"))
DOCUMENT_TYPES = {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg"}
# Aliases p/a/u are shared by public directory, inventory and sitemap queries.
PUBLIC_SUPPLIER_WHERE = """p.published=1 AND a.status='APPROVED' AND u.status='ACTIVE'
    AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL AND u.is_test_workspace=0
    AND u.role IN ('BUYER','MERCHANT','SUPPLIER')"""
PUBLIC_VEHICLE_WHERE = """v.archived_at IS NULL AND v.status='ONLINE' AND """ + PUBLIC_SUPPLIER_WHERE + """
    AND EXISTS (SELECT 1 FROM catalog_models cm JOIN catalog_brands cb ON cb.id=cm.brand_id
        WHERE cm.id=v.model_id AND cm.active=1 AND cb.active=1)"""
SITEMAP_ORIGIN = 'https://autolinkglobal.com'
SITEMAP_PAGE_SIZE = 5000
SITEMAP_STATIC_PATHS = ('/', '/trade/vehicles', '/trade/models', '/trade/brands',
    '/trade/suppliers', '/membership', '/support')


def ident(prefix: str) -> str:
    return prefix + "-" + uuid.uuid4().hex[:16].upper()


def money_minor(value, label="price", optional=False, allow_zero=False):
    if value in (None, "") and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not (0 if allow_zero else 1) <= value <= 10**12:
        raise BuyerError(400, f"Invalid {label}.")
    return value


def iso_date(value, label="valid until"):
    if not isinstance(value, str):
        raise BuyerError(400, f"Invalid {label}.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise BuyerError(400, f"Invalid {label}.") from exc
    if parsed < date.today():
        raise BuyerError(400, f"{label.title()} cannot be in the past.")
    return value


class TradeService:
    def __init__(self, auth):
        self.auth = auth
        self.agreement = SupplierAgreementService(auth)
        self.catalog = CatalogService(auth)
        self.platform = PlatformService(auth)
        with auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS supplier_applications (
                    supplier_id TEXT PRIMARY KEY REFERENCES supplier_profiles(user_id),
                    registration_no TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    contact_name TEXT NOT NULL DEFAULT '', contact_phone TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '', overview TEXT NOT NULL DEFAULT '',
                    established_year INTEGER, main_brands TEXT NOT NULL DEFAULT '',
                    main_markets TEXT NOT NULL DEFAULT '', export_experience TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'DRAFT', submitted_at INTEGER,
                    reviewed_by TEXT REFERENCES users(id), reviewed_at INTEGER,
                    review_reason TEXT NOT NULL DEFAULT '', updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS supplier_applications_status ON supplier_applications(status,submitted_at);
                CREATE TABLE IF NOT EXISTS supplier_vehicles (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    model_id TEXT NOT NULL, trim TEXT NOT NULL DEFAULT '', model_year INTEGER NOT NULL,
                    energy_type TEXT NOT NULL DEFAULT '', steering TEXT NOT NULL DEFAULT 'LHD',
                    vehicle_condition TEXT NOT NULL DEFAULT 'NEW',
                    price_minor INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
                    moq INTEGER NOT NULL, stock INTEGER NOT NULL, origin_port TEXT NOT NULL,
                    location TEXT NOT NULL DEFAULT '', lead_time TEXT NOT NULL DEFAULT '',
                    incoterm TEXT NOT NULL DEFAULT 'FOB', payment_terms TEXT NOT NULL DEFAULT '',
                    vin_available INTEGER NOT NULL DEFAULT 0, colors TEXT NOT NULL DEFAULT '',
                    export_markets TEXT NOT NULL DEFAULT '', valid_until TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'DRAFT',
                    review_reason TEXT NOT NULL DEFAULT '', reviewed_by TEXT REFERENCES users(id),
                    reviewed_at INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    archived_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS supplier_vehicles_owner ON supplier_vehicles(supplier_id,status,updated_at DESC);
                CREATE INDEX IF NOT EXISTS supplier_vehicles_public ON supplier_vehicles(status,model_id,updated_at DESC);
                CREATE TABLE IF NOT EXISTS trade_quotes (
                    id TEXT PRIMARY KEY, inquiry_id TEXT NOT NULL REFERENCES buyer_inquiries(id),
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    buyer_id TEXT NOT NULL REFERENCES users(id),
                    vehicle_id TEXT NOT NULL, trim TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL,
                    unit_price_minor INTEGER NOT NULL, total_price_minor INTEGER NOT NULL,
                    shipping_cost_minor INTEGER, currency TEXT NOT NULL,
                    incoterm TEXT NOT NULL, origin_port TEXT NOT NULL,
                    destination_port TEXT NOT NULL DEFAULT '', payment_terms TEXT NOT NULL DEFAULT '',
                    lead_time TEXT NOT NULL DEFAULT '', valid_until TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'DRAFT',
                    sent_at INTEGER, viewed_at INTEGER, responded_at INTEGER,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
                    archived_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS trade_quotes_buyer ON trade_quotes(buyer_id,status,created_at DESC);
                CREATE INDEX IF NOT EXISTS trade_quotes_supplier ON trade_quotes(supplier_id,inquiry_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS supplier_crm (
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    buyer_id TEXT NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL DEFAULT 'NEW', tag TEXT NOT NULL DEFAULT '',
                    assigned_to TEXT, updated_at INTEGER NOT NULL,
                    PRIMARY KEY(supplier_id,buyer_id)
                );
                CREATE TABLE IF NOT EXISTS supplier_crm_notes (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL, buyer_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL REFERENCES users(id), note TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    FOREIGN KEY(supplier_id,buyer_id) REFERENCES supplier_crm(supplier_id,buyer_id)
                );
                CREATE TABLE IF NOT EXISTS buyer_vehicle_views (
                    user_id TEXT NOT NULL REFERENCES users(id), listing_id TEXT NOT NULL REFERENCES supplier_vehicles(id),
                    viewed_at INTEGER NOT NULL, PRIMARY KEY(user_id,listing_id)
                );
                CREATE INDEX IF NOT EXISTS buyer_vehicle_views_recent ON buyer_vehicle_views(user_id,viewed_at DESC);
                CREATE INDEX IF NOT EXISTS buyer_vehicle_views_listing ON buyer_vehicle_views(listing_id,viewed_at);
                CREATE TABLE IF NOT EXISTS trade_audit (
                    id TEXT PRIMARY KEY, actor_user_id TEXT NOT NULL REFERENCES users(id),
                    supplier_id TEXT, action TEXT NOT NULL, entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL, created_at INTEGER NOT NULL, metadata TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS trade_audit_entity ON trade_audit(entity_type,entity_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS supplier_documents (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    kind TEXT NOT NULL, filename TEXT NOT NULL, content_type TEXT NOT NULL,
                    stored_name TEXT NOT NULL UNIQUE, bytes INTEGER NOT NULL, uploaded_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS supplier_documents_owner ON supplier_documents(supplier_id,uploaded_at DESC);
                CREATE TABLE IF NOT EXISTS inquiry_rate_events (
                    id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL REFERENCES users(id),
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS inquiry_rate_buyer ON inquiry_rate_events(buyer_id,created_at);
                CREATE TABLE IF NOT EXISTS buyer_request_responses (
                    request_id TEXT NOT NULL REFERENCES buyer_requests(id),
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    inquiry_id TEXT NOT NULL UNIQUE REFERENCES buyer_inquiries(id),
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(request_id,supplier_id)
                );
                CREATE INDEX IF NOT EXISTS request_responses_supplier ON buyer_request_responses(supplier_id,created_at DESC);
            """)
            self.add_column(db, "buyer_inquiries", "listing_id", "TEXT REFERENCES supplier_vehicles(id)")
            self.add_column(db, "supplier_applications", "city", "TEXT NOT NULL DEFAULT ''")
            for name in ('premises_address', 'inventory_basis', 'inventory_as_of'):
                self.add_column(db, 'supplier_applications', name, "TEXT NOT NULL DEFAULT ''")
            self.add_column(db, 'supplier_applications', 'inventory_count', 'INTEGER')
            self.add_column(db, 'supplier_applications', 'evidence_version', 'INTEGER NOT NULL DEFAULT 1')
            for name in ("logo_url", "public_contact_name", "public_contact_email", "public_contact_phone",
                         "public_contact_website", "public_contact_address"):
                self.add_column(db, "supplier_profiles", name, "TEXT NOT NULL DEFAULT ''")
            self.add_column(db, "supplier_profiles", "public_contact_enabled", "INTEGER NOT NULL DEFAULT 0")
            self.add_column(db, "buyer_inquiries", "target_price_minor", "INTEGER")
            self.add_column(db, "buyer_inquiries", "currency", "TEXT NOT NULL DEFAULT 'USD'")
            self.add_column(db, "buyer_inquiries", "viewed_at", "INTEGER")
            self.add_column(db, "buyer_inquiries", "assigned_to", "TEXT")
            self.add_column(db, "buyer_inquiries", "last_contact_at", "INTEGER")
            self.add_column(db, "buyer_inquiries", "request_id", "TEXT REFERENCES buyer_requests(id)")
            db.execute("CREATE INDEX IF NOT EXISTS buyer_inquiries_supplier ON buyer_inquiries(supplier_id,status,created_at DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS buyer_inquiries_listing ON buyer_inquiries(listing_id)")
            db.executescript("""
                CREATE TRIGGER IF NOT EXISTS test_supplier_no_publish_insert
                BEFORE INSERT ON supplier_profiles WHEN NEW.published!=0 AND EXISTS
                (SELECT 1 FROM users WHERE id=NEW.user_id AND is_test_workspace=1)
                BEGIN SELECT RAISE(ABORT,'Test supplier cannot be published'); END;
                CREATE TRIGGER IF NOT EXISTS test_supplier_no_publish_update
                BEFORE UPDATE OF published ON supplier_profiles WHEN NEW.published!=0 AND EXISTS
                (SELECT 1 FROM users WHERE id=NEW.user_id AND is_test_workspace=1)
                BEGIN SELECT RAISE(ABORT,'Test supplier cannot be published'); END;
                CREATE TRIGGER IF NOT EXISTS test_vehicle_drafts_insert
                BEFORE INSERT ON supplier_vehicles WHEN NEW.status NOT IN ('DRAFT','ARCHIVED') AND EXISTS
                (SELECT 1 FROM users WHERE id=NEW.supplier_id AND is_test_workspace=1)
                BEGIN SELECT RAISE(ABORT,'Test vehicles must remain private drafts'); END;
                CREATE TRIGGER IF NOT EXISTS test_vehicle_drafts_update
                BEFORE UPDATE OF status ON supplier_vehicles WHEN NEW.status NOT IN ('DRAFT','ARCHIVED') AND EXISTS
                (SELECT 1 FROM users WHERE id=NEW.supplier_id AND is_test_workspace=1)
                BEGIN SELECT RAISE(ABORT,'Test vehicles must remain private drafts'); END;
            """)
        self.images = ListingImages(auth)
        self.price_reviews = PriceReviews(auth)
        self.team = SupplierTeam(auth)

    @staticmethod
    def add_column(db, table, name, declaration):
        columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if name not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

    def audit(self, db, actor, action, entity_type, entity_id, supplier_id=None, metadata=""):
        db.execute("INSERT INTO trade_audit VALUES (?,?,?,?,?,?,?,?)",
                   (ident("AUD"), actor, supplier_id, action, entity_type, entity_id, int(time.time()), metadata[:1000]))

    def require_supplier(self, token, approved=False, supplier_id=None):
        user = self.auth.user_for_token(token)
        if user["role"] not in ("BUYER", "MERCHANT", "SUPPLIER"):
            raise BuyerError(403, "Supplier account required.")
        if not user["email_verified_at"]:
            raise BuyerError(403, "Verify your email before applying as a supplier.")
        return self.team.principal(user, supplier_id, approved)

    def require_admin(self, token):
        user = self.auth.user_for_token(token)
        owner_email = os.environ.get("PLATFORM_ADMIN_EMAIL", "").strip().lower()
        if user["role"] != "PLATFORM_ADMIN" or (owner_email and user["email"].strip().lower() != owner_email):
            raise BuyerError(403, "Platform admin required.")
        return user

    def supplier_publication(self, db, supplier_id):
        """Read-only guidance for an authorized owner or platform reviewer.

        Visibility uses the public directory's exact predicate. Missing current
        onboarding evidence is reported separately, including legacy approvals;
        this must never add a new publication gate or change an approval.
        """
        row = db.execute("""SELECT u.id,u.company_name,u.role,u.status AS account_status,
            u.deleted_at,u.email_verified_at,u.is_test_workspace,p.user_id AS profile_id,
            p.published,p.country,a.supplier_id AS application_id,a.status AS application_status,
            a.registration_no,a.address,a.contact_name,a.contact_phone,a.premises_address,
            a.inventory_count,a.inventory_basis,a.inventory_as_of
            FROM users u LEFT JOIN supplier_profiles p ON p.user_id=u.id
            LEFT JOIN supplier_applications a ON a.supplier_id=u.id WHERE u.id=?""",
            (supplier_id,)).fetchone()
        visible = bool(db.execute("""SELECT EXISTS(SELECT 1 FROM supplier_profiles p
            JOIN supplier_applications a ON a.supplier_id=p.user_id
            JOIN users u ON u.id=p.user_id WHERE p.user_id=? AND """ +
            PUBLIC_SUPPLIER_WHERE + ")", (supplier_id,)).fetchone()[0])
        field_columns = (('companyName','company_name'),('registrationNo','registration_no'),
            ('address','address'),('country','country'),('contactName','contact_name'),
            ('contactPhone','contact_phone'),('premisesAddress','premises_address'),
            ('inventoryCount','inventory_count'),('inventoryBasis','inventory_basis'),
            ('inventoryAsOf','inventory_as_of'))
        missing_fields = [name for name,column in field_columns
            if row is None or row[column] is None or isinstance(row[column],str) and not row[column].strip()]
        document_kinds = {entry[0] for entry in db.execute(
            'SELECT kind FROM supplier_documents WHERE supplier_id=?', (supplier_id,))}
        missing_documents = [kind for kind in ('BUSINESS_LICENSE','PREMISES_PHOTO','INVENTORY_PHOTO')
            if kind not in document_kinds]
        agreement = self.agreement.matching(db,supplier_id,row['company_name'],row['registration_no'],row['address']) \
            if row and row['application_id'] else None
        complete = not missing_fields and not missing_documents and bool(agreement)
        reasons = []
        status = row['application_status'] if row else None
        if not visible:
            if row is None:
                reasons.append('ACCOUNT_MISSING')
            else:
                if row['account_status'] != 'ACTIVE':reasons.append('ACCOUNT_INACTIVE')
                if row['deleted_at'] is not None:reasons.append('ACCOUNT_DELETED')
                if row['email_verified_at'] is None:reasons.append('EMAIL_UNVERIFIED')
                if row['is_test_workspace'] != 0:reasons.append('TEST_WORKSPACE')
                if row['role'] not in ('BUYER','MERCHANT','SUPPLIER'):reasons.append('ACCOUNT_ROLE_INELIGIBLE')
                if row['application_id'] is None:
                    reasons.append('APPLICATION_MISSING')
                elif status != 'APPROVED':
                    reasons.append('APPLICATION_'+status if status in
                        ('DRAFT','PENDING','REJECTED','REQUIRES_CHANGES','SUSPENDED') else 'APPLICATION_NOT_APPROVED')
                elif not row['published']:
                    reasons.append('PROFILE_UNPUBLISHED')
            if not reasons:reasons.append('PUBLICATION_NOT_READY')
        if any(reason in reasons for reason in ('ACCOUNT_MISSING','ACCOUNT_INACTIVE','ACCOUNT_DELETED',
                'TEST_WORKSPACE','ACCOUNT_ROLE_INELIGIBLE')):
            action = 'contact_support'
        elif 'EMAIL_UNVERIFIED' in reasons:
            action = 'verify_email'
        elif status == 'PENDING':
            action = 'await_review'
        elif status == 'APPROVED':
            action = 'create_vehicle' if visible and complete else 'contact_support'
        elif status == 'SUSPENDED':
            action = 'contact_support'
        elif missing_fields:
            action = 'save_application'
        elif missing_documents:
            action = 'upload_documents'
        elif not agreement:
            action = 'confirm_agreement'
        else:
            action = 'submit_application'
        return {'visible':visible,'reasons':reasons,'nextAction':action,
            'requiredFields':missing_fields,'requiredDocumentKinds':missing_documents,
            'agreementConfirmed':bool(agreement),'requirementsComplete':bool(complete)}

    def vehicle_publication(self, db, row, supplier_publication=None):
        """Explain private/admin listing visibility without exposing documents."""
        supplier = supplier_publication or self.supplier_publication(db,row['supplier_id'])
        visible = bool(db.execute("""SELECT EXISTS(SELECT 1 FROM supplier_vehicles v
            JOIN supplier_profiles p ON p.user_id=v.supplier_id
            JOIN supplier_applications a ON a.supplier_id=v.supplier_id
            JOIN users u ON u.id=v.supplier_id WHERE v.id=? AND """ +
            PUBLIC_VEHICLE_WHERE + ")", (row['id'],)).fetchone()[0])
        model = db.execute("""SELECT m.active AS model_active,b.active AS brand_active
            FROM catalog_models m LEFT JOIN catalog_brands b ON b.id=m.brand_id WHERE m.id=?""",
            (row['model_id'],)).fetchone()
        reasons = []
        if not visible:
            reasons.extend(supplier['reasons'])
            if row['archived_at'] is not None or row['status'] == 'ARCHIVED':
                reasons.append('VEHICLE_ARCHIVED')
            elif row['status'] != 'ONLINE':
                reasons.append({'DRAFT':'VEHICLE_DRAFT','PENDING_REVIEW':'VEHICLE_PENDING_REVIEW',
                    'APPROVED':'VEHICLE_APPROVED_NOT_ONLINE','REJECTED':'VEHICLE_REJECTED',
                    'OFFLINE':'VEHICLE_OFFLINE','SOLD_OUT':'VEHICLE_SOLD_OUT'}.get(row['status'],'VEHICLE_NOT_ONLINE'))
            if model is None or not model['model_active']:reasons.append('CATALOG_MODEL_INACTIVE')
            if model is not None and not model['brand_active']:reasons.append('CATALOG_BRAND_INACTIVE')
            if not reasons:reasons.append('PUBLICATION_NOT_READY')
        if visible:
            action = 'view_public_listing'
        elif not supplier['visible']:
            action = 'contact_support'
        elif row['archived_at'] is not None or row['status'] == 'ARCHIVED':
            action = 'restore_vehicle'
        elif model is None or not model['model_active'] or not model['brand_active']:
            action = 'edit_vehicle'
        elif row['status'] in ('APPROVED','OFFLINE','SOLD_OUT'):
            action = 'put_online'
        elif row['status'] == 'PENDING_REVIEW':
            action = 'await_review'
        else:
            action = 'edit_vehicle'
        return {'visible':visible,'reasons':reasons,'nextAction':action}

    def application(self, user):
        with self.auth.connect() as db:
            row = db.execute("""SELECT a.*,p.country,u.company_name FROM supplier_applications a
                JOIN supplier_profiles p ON p.user_id=a.supplier_id JOIN users u ON u.id=a.supplier_id
                WHERE a.supplier_id=?""", (user["id"],)).fetchone()
            confirmation = self.agreement.matching(db, user['id'], row['company_name'], row['registration_no'], row['address']) if row else None
            publication = self.supplier_publication(db,user['id'])
        result = dict(row) if row else {"supplier_id": user["id"], "status": "DRAFT"}
        result['agreementConfirmation'] = dict(confirmation) if confirmation else None
        result['publication'] = publication
        return result

    def documents(self, supplier_id):
        with self.auth.connect() as db:
            rows = db.execute("""SELECT id,supplier_id,kind,filename,content_type,bytes,uploaded_at
                FROM supplier_documents WHERE supplier_id=? ORDER BY uploaded_at DESC""", (supplier_id,)).fetchall()
        return [dict(row) for row in rows]

    def add_document(self, user, body):
        kind = body.get("kind")
        if kind not in ("BUSINESS_LICENSE", "EXPORT_LICENSE", "OTHER") and kind not in PHOTO_KINDS:
            raise BuyerError(400, "Invalid document kind.")
        filename = text(body.get("filename"), "filename", 160, True)
        if "/" in filename or "\\" in filename or filename.startswith("."):
            raise BuyerError(400, "Invalid filename.")
        content_type = body.get("contentType")
        extension = DOCUMENT_TYPES.get(content_type)
        if not extension or Path(filename).suffix.lower() not in (extension, ".jpeg" if extension==".jpg" else extension):
            raise BuyerError(400, "PDF, PNG or JPEG required.")
        encoded = body.get("base64")
        if not isinstance(encoded, str) or len(encoded) > 7_000_000:
            raise BuyerError(413, "Document is too large.")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise BuyerError(400, "Invalid document encoding.") from exc
        if not 20 <= len(data) <= 5_000_000:
            raise BuyerError(413, "Document must be 5 MB or smaller.")
        valid = (content_type=="application/pdf" and data.startswith(b"%PDF-") or
                 content_type=="image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") or
                 content_type=="image/jpeg" and data.startswith(b"\xff\xd8\xff"))
        if not valid:
            raise BuyerError(400, "File content does not match its type.")
        if kind in PHOTO_KINDS:
            data = sanitize_photo(data, content_type)
            content_type, extension = 'image/jpeg', '.jpg'
        with self.auth.connect() as db:
            application = db.execute("SELECT status FROM supplier_applications WHERE supplier_id=?", (user["id"],)).fetchone()
            if application and application["status"] not in ("DRAFT", "REQUIRES_CHANGES", "REJECTED"):
                raise BuyerError(409, "Documents cannot be uploaded in the current application state.")
            count = db.execute("SELECT count(*) FROM supplier_documents WHERE supplier_id=?", (user["id"],)).fetchone()[0]
            if count >= 6:
                raise BuyerError(409, "Maximum six documents per supplier.")
        DOCUMENT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
        document_id=ident("DOC")
        stored_name=uuid.uuid4().hex+extension
        path=DOCUMENT_ROOT/stored_name
        try:
            with path.open("xb") as file:
                os.chmod(path,0o600)
                file.write(data)
            with self.auth.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                application = db.execute("SELECT status FROM supplier_applications WHERE supplier_id=?", (user["id"],)).fetchone()
                if application and application["status"] not in ("DRAFT", "REQUIRES_CHANGES", "REJECTED"):
                    raise BuyerError(409, "Application state changed. Please reload.")
                # A verified owner may upload evidence before completing the form.
                # Only a private draft is created; approval, agreement and role gates remain.
                if not application:
                    now = int(time.time())
                    db.execute("INSERT OR IGNORE INTO supplier_profiles(user_id,published,country,description,updated_at) VALUES (?,0,'','',?)",
                               (user["id"], now))
                    db.execute("INSERT INTO supplier_applications(supplier_id,status,updated_at,evidence_version) VALUES (?,'DRAFT',?,2)",
                               (user["id"], now))
                if db.execute("SELECT count(*) FROM supplier_documents WHERE supplier_id=?", (user["id"],)).fetchone()[0] >= 6:
                    raise BuyerError(409, "Maximum six documents per supplier.")
                db.execute("INSERT INTO supplier_documents VALUES (?,?,?,?,?,?,?,?)",
                           (document_id,user["id"],kind,filename,content_type,stored_name,len(data),int(time.time())))
                self.audit(db,user["id"],"DOCUMENT_UPLOADED","document",document_id,user["id"],kind)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return next(row for row in self.documents(user["id"]) if row["id"]==document_id)

    def document_bytes(self, document_id, user):
        with self.auth.connect() as db:
            row=db.execute("SELECT * FROM supplier_documents WHERE id=?",(document_id,)).fetchone()
        if not row or user["role"]!="PLATFORM_ADMIN" and row["supplier_id"]!=user["id"]:
            raise BuyerError(404, "Document not found.")
        return {"filename":row["filename"], "contentType":row["content_type"], "data":(DOCUMENT_ROOT/row["stored_name"]).read_bytes()}

    def save_application(self, user, body):
        fields = {
            "company_name": text(body.get("companyName"), "company name", 160, True),
            "registration_no": text(body.get("registrationNo"), "registration number", 100, True),
            "address": text(body.get("address"), "address", 320, True),
            "country": text(body.get("country"), "country", 120, True),
            "city": text(body.get("city"), "city", 120),
            "contact_name": text(body.get("contactName"), "contact name", 160, True),
            "contact_phone": text(body.get("contactPhone"), "contact phone", 80, True),
            "website": text(body.get("website"), "website", 320),
            "overview": text(body.get("overview"), "overview", 3000),
            "main_brands": text(body.get("mainBrands"), "main brands", 500),
            "main_markets": text(body.get("mainMarkets"), "main markets", 500),
            "export_experience": text(body.get("exportExperience"), "export experience", 2000),
        }
        year = body.get("establishedYear")
        if year is not None and (isinstance(year, bool) or not isinstance(year, int) or not 1850 <= year <= date.today().year):
            raise BuyerError(400, "Invalid established year.")
        if fields["website"] and not re.fullmatch(r"https?://[^\s]+", fields["website"]):
            raise BuyerError(400, "Invalid company website.")
        evidence = evidence_fields(body)
        submit = body.get("submit") is True
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT status FROM supplier_applications WHERE supplier_id=?", (user["id"],)).fetchone()
            if submit and not db.execute("SELECT 1 FROM supplier_documents WHERE supplier_id=? AND kind='BUSINESS_LICENSE'", (user["id"],)).fetchone():
                raise BuyerError(409, "Save draft and upload a business license before submitting.")
            if submit:
                require_evidence(db, user["id"], evidence)
                self.agreement.require_current(db, user['id'], fields['company_name'], fields['registration_no'], fields['address'])
            if existing and existing["status"] in ("PENDING", "APPROVED", "SUSPENDED"):
                raise BuyerError(409, "This application cannot be edited in its current state.")
            db.execute("INSERT OR IGNORE INTO supplier_profiles(user_id,published,country,description,updated_at) VALUES (?,0,?,?,?)",
                       (user["id"], fields["country"], fields["overview"], now))
            db.execute("UPDATE supplier_profiles SET country=?,description=?,updated_at=? WHERE user_id=?",
                       (fields["country"], fields["overview"], now, user["id"]))
            db.execute("UPDATE users SET company_name=? WHERE id=?", (fields["company_name"], user["id"]))
            status = "PENDING" if submit else "DRAFT"
            db.execute("""INSERT INTO supplier_applications(supplier_id,registration_no,address,city,contact_name,contact_phone,
                website,overview,established_year,main_brands,main_markets,export_experience,status,submitted_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(supplier_id) DO UPDATE SET
                registration_no=excluded.registration_no,address=excluded.address,city=excluded.city,contact_name=excluded.contact_name,
                contact_phone=excluded.contact_phone,website=excluded.website,overview=excluded.overview,
                established_year=excluded.established_year,main_brands=excluded.main_brands,
                main_markets=excluded.main_markets,export_experience=excluded.export_experience,
                status=excluded.status,submitted_at=excluded.submitted_at,updated_at=excluded.updated_at""",
                (user["id"],fields["registration_no"],fields["address"],fields["city"],fields["contact_name"],
                 fields["contact_phone"],fields["website"],fields["overview"],year,fields["main_brands"],
                 fields["main_markets"],fields["export_experience"],status,now if submit else None,now))
            db.execute("""UPDATE supplier_applications SET premises_address=?,inventory_count=?,
                inventory_basis=?,inventory_as_of=?,evidence_version=2 WHERE supplier_id=?""",
                (evidence['premises_address'], evidence['inventory_count'], evidence['inventory_basis'], evidence['inventory_as_of'], user['id']))
            if submit:
                self.audit(db,user["id"],"SUPPLIER_SUBMITTED","supplier",user["id"],user["id"])
        return self.application(user)

    def review_supplier(self, admin, supplier_id, body):
        decision = body.get("decision")
        if decision not in ("APPROVED", "REJECTED", "REQUIRES_CHANGES", "SUSPENDED"):
            raise BuyerError(400, "Invalid review decision.")
        reason = text(body.get("reason"), "review reason", 1000)
        if decision != "APPROVED" and not reason:
            raise BuyerError(400, "Review reason required.")
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM supplier_applications WHERE supplier_id=?", (supplier_id,)).fetchone()
            if not row or row["status"] not in ("PENDING", "APPROVED", "SUSPENDED"):
                raise BuyerError(404, "Reviewable supplier application not found.")
            if decision == "APPROVED" and not db.execute("SELECT 1 FROM supplier_documents WHERE supplier_id=? AND kind='BUSINESS_LICENSE'",(supplier_id,)).fetchone():
                raise BuyerError(409, "A business license document is required before approval.")
            if decision == 'APPROVED' and row['status'] == 'PENDING':
                company_name = db.execute('SELECT company_name FROM users WHERE id=?', (supplier_id,)).fetchone()[0]
                self.agreement.require_current(db, supplier_id, company_name, row['registration_no'], row['address'])
            if decision == 'APPROVED' and row['evidence_version'] >= 2:
                require_evidence(db, supplier_id, row)
            db.execute("UPDATE supplier_applications SET status=?,reviewed_by=?,reviewed_at=?,review_reason=?,updated_at=? WHERE supplier_id=?",
                       (decision,admin["id"],now,reason,now,supplier_id))
            db.execute("UPDATE supplier_profiles SET published=?,updated_at=? WHERE user_id=?",
                       (1 if decision=="APPROVED" else 0,now,supplier_id))
            if decision == "SUSPENDED":
                db.execute("UPDATE supplier_vehicles SET status='OFFLINE',updated_at=? WHERE supplier_id=? AND status='ONLINE'", (now,supplier_id))
            PlatformService.notify(db,supplier_id,"SUPPLIER_"+decision,supplier_id,"/supplier/application")
            self.audit(db,admin["id"],"SUPPLIER_"+decision,"supplier",supplier_id,supplier_id,reason)
        return {"supplierId":supplier_id,"status":decision}

    def supplier_list(self, public=True, status=None, page=None, supplier_id=None):
        with self.auth.connect() as db:
            if public:
                rows = db.execute("""SELECT p.user_id AS id,u.company_name,p.country,p.description,a.city,a.website,
                    a.established_year,a.main_brands,a.main_markets,a.export_experience,u.created_at AS joined_at,
                    p.logo_url,p.public_contact_enabled,p.public_contact_name,p.public_contact_email,
                    p.public_contact_phone,p.public_contact_website,p.public_contact_address
                    FROM supplier_profiles p JOIN supplier_applications a ON a.supplier_id=p.user_id
                    JOIN users u ON u.id=p.user_id WHERE """ + PUBLIC_SUPPLIER_WHERE +
                    " ORDER BY a.reviewed_at DESC").fetchall()
            else:
                sql = """SELECT a.*,u.company_name,u.email,p.country FROM supplier_applications a
                    JOIN users u ON u.id=a.supplier_id JOIN supplier_profiles p ON p.user_id=a.supplier_id
                    WHERE (? IS NULL OR a.status=?)"""
                args = [status, status]
                if supplier_id is not None:
                    sql += ' AND a.supplier_id=?'
                    args.append(text(supplier_id, 'supplier ID', 100, True))
                rows = query_list(db, sql, args, order='a.updated_at DESC,a.supplier_id DESC', page=page, legacy_limit=200)
                for row in list_items(rows):
                    row['publication'] = self.supplier_publication(db,row['supplier_id'])
        results = [dict(r) for r in rows] if public else rows
        if public:
            for supplier in results:
                enabled = supplier.pop("public_contact_enabled") == 1
                contact = {key: supplier.pop("public_contact_" + key)
                           for key in ("name", "email", "phone", "website", "address")}
                supplier["contact"] = contact if enabled else None
        return results

    def public_supplier(self, supplier_id):
        return next((s for s in self.supplier_list() if s["id"]==supplier_id), None)

    def sitemap_xml(self, filename='sitemap.xml'):
        """Public URLs only, read from maintained tables; bounded XML shards.

        This never serializes full user/listing rows, private files, inquiries,
        quotes or contact details. Counts and shard rows use one read snapshot.
        """
        supplier_from = """supplier_profiles p JOIN supplier_applications a ON a.supplier_id=p.user_id
            JOIN users u ON u.id=p.user_id"""
        sections = {
            'brands': ('catalog_brands b', 'b.active=1', 'b.id', 'b.updated_at', '/trade/brands/'),
            'models': ('catalog_models m JOIN catalog_brands b ON b.id=m.brand_id',
                       'm.active=1 AND b.active=1', 'm.id', 'max(m.updated_at,b.updated_at)', '/trade/models/'),
            'suppliers': (supplier_from, PUBLIC_SUPPLIER_WHERE, 'p.user_id',
                          'max(p.updated_at,a.updated_at)', '/trade/suppliers/'),
            'vehicles': ("""supplier_vehicles v JOIN supplier_profiles p ON p.user_id=v.supplier_id
                JOIN supplier_applications a ON a.supplier_id=v.supplier_id JOIN users u ON u.id=v.supplier_id""",
                         PUBLIC_VEHICLE_WHERE, 'v.id', 'max(v.updated_at,p.updated_at,a.updated_at)', '/trade/vehicles/'),
        }
        namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        root = ElementTree.Element('sitemapindex' if filename=='sitemap.xml' else 'urlset', xmlns=namespace)
        with self.auth.connect() as db:
            db.execute('BEGIN')
            if filename=='sitemap.xml':
                children = ['static-1.xml']
                for category,(source,where,*_) in sections.items():
                    count = db.execute('SELECT count(*) FROM '+source+' WHERE '+where).fetchone()[0]
                    pages = max(1, (count+SITEMAP_PAGE_SIZE-1)//SITEMAP_PAGE_SIZE)
                    if len(children)+pages > 50000:
                        raise BuyerError(503, 'Sitemap capacity exceeded.')
                    children.extend(category+'-'+str(page)+'.xml' for page in range(1,pages+1))
                for child in children:
                    node = ElementTree.SubElement(root, 'sitemap')
                    ElementTree.SubElement(node, 'loc').text = SITEMAP_ORIGIN+'/sitemaps/'+child
            elif filename=='static-1.xml':
                for path in SITEMAP_STATIC_PATHS:
                    node = ElementTree.SubElement(root,'url')
                    ElementTree.SubElement(node,'loc').text = SITEMAP_ORIGIN+path
            else:
                match = re.fullmatch(r'(brands|models|suppliers|vehicles)-([1-9][0-9]{0,4})\.xml',filename)
                if not match:
                    raise BuyerError(404,'Sitemap not found.')
                category,page = match[1],int(match[2])
                source,where,key,modified,prefix = sections[category]
                count = db.execute('SELECT count(*) FROM '+source+' WHERE '+where).fetchone()[0]
                if page > max(1,(count+SITEMAP_PAGE_SIZE-1)//SITEMAP_PAGE_SIZE):
                    raise BuyerError(404,'Sitemap not found.')
                rows = db.execute('SELECT '+key+' AS id,'+modified+' AS modified FROM '+source+
                    ' WHERE '+where+' ORDER BY '+key+' LIMIT ? OFFSET ?',
                    (SITEMAP_PAGE_SIZE,(page-1)*SITEMAP_PAGE_SIZE))
                for row in rows:
                    node = ElementTree.SubElement(root,'url')
                    ElementTree.SubElement(node,'loc').text = SITEMAP_ORIGIN+prefix+quote(row['id'],safe='')
                    # Actual stored content modification, never generation time.
                    if row['modified']:
                        ElementTree.SubElement(node,'lastmod').text = datetime.fromtimestamp(
                            row['modified'],timezone.utc).isoformat(timespec='seconds')
        payload = ElementTree.tostring(root,encoding='utf-8',xml_declaration=True)
        if len(payload)>52428800:
            raise BuyerError(503,'Sitemap capacity exceeded.')
        return payload

    @staticmethod
    def public_profile_url(value, label, logo=False):
        value = text(value, label, 1000)
        if not value:
            return ""
        try:
            parsed = urlsplit(value)
            host = (parsed.hostname or "").encode("idna").decode().lower()
            port = parsed.port
            if (parsed.scheme not in (("https",) if logo else ("http", "https")) or
                    parsed.username is not None or parsed.password is not None or port not in (None, 80, 443) or
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) or "." not in host or
                    host.endswith((".localhost", ".local", ".internal")) or
                    any(ord(c) < 33 or ord(c) == 127 for c in value) or "\\" in value):
                raise ValueError()
            try:
                address = ipaddress.ip_address(host)
            except ValueError:
                address = None
            if address is not None:
                raise ValueError()  # Public company URLs must use a domain, not an IP address.
            if logo and host in ("autolinkglobal.com", "www.autolinkglobal.com"):
                path = unquote(parsed.path)
                if not path.startswith("/assets/") or ".." in path.split("/") or "\\" in path:
                    raise ValueError()  # Never embed authenticated APIs or verification documents.
        except (ValueError, UnicodeError) as exc:
            raise BuyerError(400, f"Invalid {label}.") from exc
        return value

    def supplier_profile(self, supplier):
        with self.auth.connect() as db:
            self.active_company_owner(db, supplier)
            row = db.execute("""SELECT p.user_id AS id,u.company_name,p.country,a.city,p.description,p.logo_url,
                p.public_contact_name AS contact_name,p.public_contact_email AS contact_email,
                p.public_contact_phone AS contact_phone,p.public_contact_website AS contact_website,
                p.public_contact_address AS contact_address,p.public_contact_enabled AS contact_enabled,p.updated_at
                FROM supplier_profiles p JOIN users u ON u.id=p.user_id
                JOIN supplier_applications a ON a.supplier_id=p.user_id WHERE p.user_id=?""",
                (supplier["id"],)).fetchone()
        return dict(row)

    def save_supplier_profile(self, supplier, body):
        allowed = {"description", "logoUrl", "contactName", "contactEmail", "contactPhone",
                   "contactWebsite", "contactAddress", "publishContact"}
        if not isinstance(body, dict) or set(body) - allowed:
            raise BuyerError(400, "Invalid public profile fields.")
        enabled = body.get("publishContact", False)
        if not isinstance(enabled, bool):
            raise BuyerError(400, "Contact publication consent must be true or false.")
        fields = {"description": text(body.get("description"), "company overview", 3000),
                  "logo_url": self.public_profile_url(body.get("logoUrl"), "public logo URL", logo=True),
                  "public_contact_name": text(body.get("contactName"), "public contact name", 160),
                  "public_contact_email": text(body.get("contactEmail"), "public contact email", 320),
                  "public_contact_phone": text(body.get("contactPhone"), "public contact phone", 80),
                  "public_contact_website": self.public_profile_url(body.get("contactWebsite"), "public contact website"),
                  "public_contact_address": text(body.get("contactAddress"), "public business address", 320)}
        if any(any(ord(c) < 32 and c not in "\n\t" or ord(c) == 127 for c in value) for value in fields.values()):
            raise BuyerError(400, "Invalid public profile text.")
        email = fields["public_contact_email"]
        if email:
            try:
                fields["public_contact_email"] = normalized_email(email)
            except EmailError as exc:
                raise BuyerError(400, "Enter a valid public contact email.") from exc
        phone = fields["public_contact_phone"]
        if phone and (not re.fullmatch(r"[+0-9(). -]{5,80}", phone) or not re.search(r"[0-9]", phone)):
            raise BuyerError(400, "Invalid public contact phone.")
        if enabled and not any(fields[key] for key in ("public_contact_email", "public_contact_phone", "public_contact_website")):
            raise BuyerError(400, "Add an email, phone or website before publishing contact details.")
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.active_company_owner(db, supplier)
            db.execute("UPDATE supplier_profiles SET " + ",".join(key + "=?" for key in fields) +
                       ",public_contact_enabled=?,updated_at=? WHERE user_id=?",
                       (*fields.values(), int(enabled), int(time.time()), supplier["id"]))
            self.audit(db, self.team.actor(supplier), "COMPANY_PUBLIC_PROFILE_CHANGED", "supplier", supplier["id"],
                       supplier["id"], json.dumps({"contactPublished": enabled, "fields": sorted(body)}))
        return self.supplier_profile(supplier)

    @staticmethod
    def search_filters(filters):
        """Validate public filters once, including callers outside the HTTP handler."""
        filters = dict(filters or {})
        for key, maximum in (("keyword",80),("brand",120),("model",120),("vehicleType",80),
                             ("energyType",80),("condition",20),("steering",10),("incoterm",10),("sort",20)):
            if filters.get(key) is not None:
                filters[key] = text(filters[key], key, maximum)
        for key, lower, upper in (("year",1990,2100),("minStock",0,1000000),
                                  ("minPriceMinor",0,10**12),("maxPriceMinor",0,10**12)):
            value = filters.get(key)
            if value in (None, ""):
                filters.pop(key, None)
                continue
            if isinstance(value, bool) or not (isinstance(value, int) or
                    isinstance(value, str) and re.fullmatch(r"[0-9]{1,16}",value)):
                raise BuyerError(400, "Invalid search filter.")
            number = int(value)
            if not lower <= number <= upper:
                raise BuyerError(400, "Invalid search filter.")
            filters[key] = number
        if (filters.get("minPriceMinor") is not None and filters.get("maxPriceMinor") is not None
                and filters["minPriceMinor"] > filters["maxPriceMinor"]):
            raise BuyerError(400, "Minimum price cannot exceed maximum price.")
        for key, allowed in (("condition",{"NEW","USED"}),("steering",{"LHD","RHD"}),
                             ("incoterm",{"FOB","CIF","CFR","EXW"}),
                             ("sort",{"newest","price_asc","price_desc","popular"})):
            if filters.get(key) and filters[key] not in allowed:
                raise BuyerError(400, "Invalid search filter.")
        return filters

    def vehicle_rows(self, supplier_id=None, public=False, status=None, limit=25, offset=0, filters=None, page=None):
        filters = self.search_filters(filters) if public else (filters or {})
        with self.auth.connect() as db:
            where = ["v.archived_at IS NOT NULL" if status == "ARCHIVED" and not public else "v.archived_at IS NULL"]
            args = []
            if public:
                where.append(PUBLIC_VEHICLE_WHERE)
            if supplier_id:
                where.append("v.supplier_id=?")
                args.append(supplier_id)
            if status and not public:
                where.append("v.status=?")
                args.append(status)
            if public:
                if filters.get("keyword"):
                    where.append("(lower(v.model_id) LIKE ? ESCAPE '\\' OR lower(v.trim) LIKE ? ESCAPE '\\' OR EXISTS (SELECT 1 FROM catalog_models cm JOIN catalog_brands cb ON cb.id=cm.brand_id WHERE cm.id=v.model_id AND lower(cb.name || ' ' || cm.name) LIKE ? ESCAPE '\\'))")
                    keyword = filters["keyword"].lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    term = "%" + keyword + "%"
                    args.extend((term, term, term))
                if filters.get("brand"):
                    models = [key for key, item in self.catalog.items() if item.get("brand", "").casefold() == filters["brand"].casefold()]
                    where.append("v.model_id IN (" + ",".join("?" for _ in models) + ")" if models else "1=0")
                    args.extend(models)
                for input_name, catalog_key in (("model","model"),("vehicleType","bodyType")):
                    if filters.get(input_name):
                        models=[key for key,item in self.catalog.items() if str(item.get(catalog_key,"")).casefold()==str(filters[input_name]).casefold()]
                        where.append("v.model_id IN ("+",".join("?" for _ in models)+")" if models else "1=0")
                        args.extend(models)
                for input_name, column in (("energyType","energy_type"),("condition","vehicle_condition"),
                                           ("steering","steering"),("incoterm","incoterm")):
                    if filters.get(input_name):
                        aliases={"Electric":("Electric","EV"),"EV":("Electric","EV"),
                                 "Plug-in Hybrid":("Plug-in Hybrid","PHEV"),"PHEV":("Plug-in Hybrid","PHEV"),
                                 "Gasoline":("Gasoline","ICE"),"ICE":("Gasoline","ICE")}
                        values=aliases.get(filters[input_name],(filters[input_name],)) if input_name=="energyType" else (filters[input_name],)
                        where.append(f"v.{column} IN ("+",".join("?" for _ in values)+")")
                        args.extend(values)
                for input_name, operator in (("minPriceMinor",">="),("maxPriceMinor","<=")):
                    if filters.get(input_name) is not None:
                        where.append(f"v.price_minor{operator}?")
                        args.append(filters[input_name])
                for input_name, column, operator in (("year","model_year","="),("minStock","stock",">=")):
                    if filters.get(input_name) is not None:
                        where.append(f"v.{column}{operator}?")
                        args.append(filters[input_name])
            condition = " AND ".join(where)
            order = {"newest":"v.updated_at DESC", "price_asc":"v.price_minor ASC",
                     "price_desc":"v.price_minor DESC",
                     "popular":"(SELECT count(*) FROM buyer_vehicle_views bv JOIN users viewer ON viewer.id=bv.user_id WHERE bv.listing_id=v.id AND bv.viewed_at>=? AND viewer.status='ACTIVE' AND viewer.deleted_at IS NULL AND viewer.role='BUYER' AND viewer.email_verified_at IS NOT NULL) DESC, v.updated_at DESC"}.get(filters.get("sort"),"v.updated_at DESC")
            order_args = (int(time.time())-30*86400,) if filters.get("sort") == "popular" else ()
            rows = query_list(db, """SELECT v.*,u.company_name AS supplier_name,p.country AS supplier_country,a.status AS supplier_status
                FROM supplier_vehicles v JOIN users u ON u.id=v.supplier_id
                JOIN supplier_profiles p ON p.user_id=v.supplier_id
                LEFT JOIN supplier_applications a ON a.supplier_id=v.supplier_id WHERE """+condition,
                args, order=order+', v.id ASC', order_args=order_args, page=page,
                legacy_limit=limit, legacy_offset=offset)
            if not public:
                supplier_publications = {}
                for row in list_items(rows):
                    owner = row['supplier_id']
                    if owner not in supplier_publications:
                        supplier_publications[owner] = self.supplier_publication(db,owner)
                    row['publication'] = self.vehicle_publication(db,row,supplier_publications[owner])
        result = [self.decorate_vehicle(dict(r)) for r in list_items(rows)]
        if public:
            for row in result:
                for key in ("review_reason", "reviewed_by", "reviewed_at"):
                    row.pop(key, None)
        if isinstance(rows, dict):
            return {**rows, 'items': result}
        return result

    def saved_listings(self, buyer):
        with self.auth.connect() as db:
            ids = [row[0] for row in db.execute("""SELECT s.vehicle_id FROM buyer_saved_vehicles s
                JOIN supplier_vehicles v ON v.id=s.vehicle_id WHERE s.user_id=? ORDER BY s.created_at DESC""",
                (buyer["id"],))]
        result = []
        for listing_id in ids:
            try:
                result.append(self.vehicle(listing_id, public=True))
            except BuyerError:
                pass
        return result

    def save_listing(self, buyer, listing_id, add=True):
        if add:
            self.vehicle(listing_id, public=True)
        with self.auth.connect() as db:
            if add:
                db.execute("INSERT OR IGNORE INTO buyer_saved_vehicles(user_id,vehicle_id,created_at) VALUES (?,?,?)",
                           (buyer["id"],listing_id,int(time.time())))
            else:
                db.execute("DELETE FROM buyer_saved_vehicles WHERE user_id=? AND vehicle_id=?",(buyer["id"],listing_id))
        return self.saved_listings(buyer)

    def decorate_vehicle(self, row):
        model = self.catalog.get(row["model_id"], {})
        images=self.images.list(row["id"])
        image="/autolink/public/vehicle-images/"+images[0]["id"] if images else model.get("image") or model.get("images",[None])[0]
        return {**row,"brand":model.get("brand",""),"model":model.get("model",""),
                "image":image,"referenceImage":not bool(images),"images":["/autolink/public/vehicle-images/"+item["id"] for item in images],
                "verifiedSupplier":row.get("supplier_status")=="APPROVED"}

    def vehicle(self, listing_id, supplier_id=None, public=False, include_archived=False):
        with self.auth.connect() as db:
            row = db.execute("""SELECT v.*,u.company_name AS supplier_name,p.country AS supplier_country,
                a.status AS supplier_status,u.status AS account_status,p.published AS supplier_published FROM supplier_vehicles v JOIN users u ON u.id=v.supplier_id
                JOIN supplier_profiles p ON p.user_id=v.supplier_id
                LEFT JOIN supplier_applications a ON a.supplier_id=v.supplier_id WHERE v.id=?""" +
                (' AND '+PUBLIC_VEHICLE_WHERE if public else ''),(listing_id,)).fetchone()
        if not row or row["archived_at"] is not None and (public or not include_archived) or supplier_id and row["supplier_id"]!=supplier_id or public and (row["status"]!="ONLINE" or row["supplier_status"]!="APPROVED" or row["account_status"]!="ACTIVE" or not row["supplier_published"] or not self.catalog.enabled(row["model_id"])):
            raise BuyerError(404, "Vehicle listing not found.")
        result = self.decorate_vehicle(dict(row))
        if not public:
            with self.auth.connect() as db:
                result['publication'] = self.vehicle_publication(db,result)
        if public:
            for key in ("review_reason", "reviewed_by", "reviewed_at"):
                result.pop(key, None)
        return result

    def save_vehicle(self, user, body, listing_id=None):
        model_id = text(body.get("modelId"),"model",100,True)
        if not self.catalog.enabled(model_id):
            raise BuyerError(400, "Unknown catalogue model.")
        year = body.get("modelYear")
        if isinstance(year,bool) or not isinstance(year,int) or not 1990 <= year <= date.today().year+2:
            raise BuyerError(400, "Invalid model year.")
        steering = body.get("steering","LHD")
        condition = body.get("condition","NEW")
        term = body.get("incoterm","FOB")
        if steering not in ("LHD","RHD") or condition not in ("NEW","USED") or term not in TERMS:
            raise BuyerError(400, "Invalid vehicle trade information.")
        stock = positive_int(body.get("stock"),"stock")
        moq = positive_int(body.get("moq"),"minimum order")
        if moq>stock:
            raise BuyerError(400, "MOQ cannot exceed stock.")
        currency=text(body.get("currency","USD"),"currency",3,True).upper()
        if not re.fullmatch(r"[A-Z]{3}",currency):
            raise BuyerError(400,"Invalid currency.")
        values = (model_id,text(body.get("trim"),"trim",200),year,text(body.get("energyType"),"energy type",80),
                  steering,condition,money_minor(body.get("priceMinor")),currency,
                  moq,stock,text(body.get("originPort"),"origin port",120,True),text(body.get("location"),"location",160),
                  text(body.get("leadTime"),"lead time",120),term,text(body.get("paymentTerms"),"payment terms",500),
                  1 if body.get("vinAvailable") is True else 0,text(body.get("colors"),"colors",300),
                  text(body.get("exportMarkets"),"export markets",500),iso_date(body.get("validUntil")),
                  text(body.get("description"),"description",3000))
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if listing_id:
                row = db.execute("SELECT status,price_minor,stock FROM supplier_vehicles WHERE id=? AND supplier_id=? AND archived_at IS NULL",(listing_id,user["id"])).fetchone()
                if not row:
                    raise BuyerError(404,"Vehicle listing not found.")
                if row["status"] not in ("DRAFT","REJECTED","APPROVED","OFFLINE","SOLD_OUT"):
                    raise BuyerError(409,"This listing cannot be edited now.")
                db.execute("""UPDATE supplier_vehicles SET model_id=?,trim=?,model_year=?,energy_type=?,steering=?,
                    vehicle_condition=?,price_minor=?,currency=?,moq=?,stock=?,origin_port=?,location=?,lead_time=?,
                    incoterm=?,payment_terms=?,vin_available=?,colors=?,export_markets=?,valid_until=?,description=?,
                    status='DRAFT',review_reason='',updated_at=? WHERE id=? AND supplier_id=?""",(*values,now,listing_id,user["id"]))
                self.audit(db,user["id"],"VEHICLE_CHANGED","vehicle",listing_id,user["id"])
                for column, value, action in (("price_minor", body["priceMinor"], "VEHICLE_PRICE_CHANGED"),
                                               ("stock", stock, "VEHICLE_INVENTORY_CHANGED")):
                    if row[column] != value:
                        self.audit(db, self.team.actor(user), action, "vehicle", listing_id, user["id"],
                                   json.dumps({"previous": row[column], "current": value}))
            else:
                listing_id = ident("VEH")
                db.execute("""INSERT INTO supplier_vehicles(id,supplier_id,model_id,trim,model_year,energy_type,
                    steering,vehicle_condition,price_minor,currency,moq,stock,origin_port,location,lead_time,incoterm,
                    payment_terms,vin_available,colors,export_markets,valid_until,description,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(listing_id,user["id"],*values,now,now))
                self.audit(db,user["id"],"VEHICLE_CREATED","vehicle",listing_id,user["id"])
        return self.vehicle(listing_id,supplier_id=user["id"])

    def active_company_owner(self, db, supplier):
        self.team.owner(supplier)
        active = db.execute("""SELECT 1 FROM supplier_applications a JOIN users u ON u.id=a.supplier_id
            WHERE a.supplier_id=? AND a.status='APPROVED' AND u.status='ACTIVE'
            AND u.role IN ('BUYER','MERCHANT','SUPPLIER') AND u.deleted_at IS NULL
            AND u.email_verified_at IS NOT NULL""", (supplier["id"],)).fetchone()
        if not active or self.team.actor(supplier) != supplier["id"]:
            raise BuyerError(403, "An approved company owner is required.")

    def copy_vehicle(self, supplier, listing_id):
        self.team.owner(supplier)
        copied_id = ident("VEH")
        files = []
        try:
            with self.auth.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                # Recheck the owner and company in the same transaction as the
                # copy, rather than relying on a stale request principal.
                self.active_company_owner(db, supplier)
                row = db.execute("SELECT * FROM supplier_vehicles WHERE id=? AND supplier_id=?",
                                 (listing_id, supplier["id"])).fetchone()
                if not row:
                    raise BuyerError(404, "Vehicle listing not found.")
                fields = ("model_id", "trim", "model_year", "energy_type", "steering", "vehicle_condition",
                          "price_minor", "currency", "moq", "stock", "origin_port", "location", "lead_time",
                          "incoterm", "payment_terms", "vin_available", "colors", "export_markets", "valid_until", "description")
                now = int(time.time())
                db.execute("INSERT INTO supplier_vehicles(id,supplier_id," + ",".join(fields) +
                           ",status,created_at,updated_at) VALUES (" + ",".join("?" for _ in range(len(fields)+5)) + ")",
                           (copied_id, supplier["id"], *(row[field] for field in fields), "DRAFT", now, now))
                files = self.images.copy_into(db, supplier["id"], listing_id, copied_id)
                self.audit(db, self.team.actor(supplier), "VEHICLE_COPIED", "vehicle", copied_id, supplier["id"],
                           json.dumps({"source_listing": listing_id}))
        except Exception:
            for path in files:
                path.unlink(missing_ok=True)
            raise
        return self.vehicle(copied_id, supplier_id=supplier["id"])

    def transition_vehicle(self, user, listing_id, action):
        self.team.owner(user)
        target = {"submit":"PENDING_REVIEW","online":"ONLINE","offline":"OFFLINE","sold-out":"SOLD_OUT","archive":"ARCHIVED","restore":"DRAFT"}.get(action)
        if user.get("is_test_workspace") and action not in ("archive", "restore"):
            raise BuyerError(403,"Test vehicles must remain private drafts.")
        if not target:
            raise BuyerError(400,"Invalid vehicle action.")
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.active_company_owner(db, user)
            row = db.execute("SELECT status,valid_until,model_id,archived_at FROM supplier_vehicles WHERE id=? AND supplier_id=?",
                             (listing_id,user["id"])).fetchone()
            if not row:
                raise BuyerError(404,"Vehicle listing not found.")
            if row["archived_at"] is not None and action != "restore":
                raise BuyerError(404, "Vehicle listing not found.")
            allowed = {"submit":("DRAFT","REJECTED"),"online":("APPROVED","OFFLINE","SOLD_OUT"),
                       "offline":("ONLINE",),"sold-out":("ONLINE",),"archive":("DRAFT","REJECTED","APPROVED","OFFLINE","SOLD_OUT"),
                       "restore":("ARCHIVED",)}
            if row["status"] not in allowed[action]:
                raise BuyerError(409,"Vehicle cannot change to that status.")
            if action == "submit":
                self.images.require_stock_photos(db, listing_id, user["id"])
                iso_date(row["valid_until"])
                if not self.catalog.enabled(row["model_id"]):
                    raise BuyerError(409, "Update the listing to an active catalogue model before review.")
            now=int(time.time())
            db.execute("UPDATE supplier_vehicles SET status=?,updated_at=?,archived_at=? WHERE id=? AND supplier_id=?",
                       (target,now,now if action=="archive" else None,listing_id,user["id"]))
            if action == "restore":
                db.execute("UPDATE supplier_vehicles SET review_reason='',reviewed_by=NULL,reviewed_at=NULL WHERE id=? AND supplier_id=?",
                           (listing_id, user["id"]))
            self.audit(db,self.team.actor(user),"VEHICLE_RESTORED" if action == "restore" else "VEHICLE_"+target,"vehicle",listing_id,user["id"])
        return self.vehicle(listing_id,supplier_id=user["id"]) if action!="archive" else {"archived":True}

    def review_vehicle(self, admin, listing_id, body):
        decision=body.get("decision")
        if decision not in ("APPROVED","REJECTED"):
            raise BuyerError(400,"Invalid review decision.")
        reason=text(body.get("reason"),"review reason",1000)
        if decision=="REJECTED" and not reason:
            raise BuyerError(400,"Review reason required.")
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.price_reviews.admin(db, admin)
            row=db.execute("SELECT * FROM supplier_vehicles WHERE id=?",(listing_id,)).fetchone()
            if not row or row["status"]!="PENDING_REVIEW":
                raise BuyerError(404,"Reviewable vehicle listing not found.")
            if decision == "APPROVED":
                iso_date(row["valid_until"])
                self.images.require_stock_photos(db, listing_id, row["supplier_id"])
                self.price_reviews.require_current(db, row, body.get("priceReviewId"), reason)
            db.execute("UPDATE supplier_vehicles SET status=?,review_reason=?,reviewed_by=?,reviewed_at=?,updated_at=? WHERE id=?",
                       (decision,reason,admin["id"],now,now,listing_id))
            PlatformService.notify(db,row["supplier_id"],"VEHICLE_"+decision,listing_id,"/supplier/vehicles/"+listing_id)
            self.audit(db,admin["id"],"VEHICLE_"+decision,"vehicle",listing_id,row["supplier_id"],json.dumps({"reason":reason,"priceReviewId":body.get("priceReviewId")}))
        return self.vehicle(listing_id)

    def record_view(self, buyer, listing_id):
        self.vehicle(listing_id,public=True)
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("INSERT INTO buyer_vehicle_views(user_id,listing_id,viewed_at) VALUES (?,?,?) ON CONFLICT(user_id,listing_id) DO UPDATE SET viewed_at=excluded.viewed_at",(buyer["id"],listing_id,now))
            db.execute("DELETE FROM buyer_vehicle_views WHERE user_id=? AND listing_id NOT IN (SELECT listing_id FROM buyer_vehicle_views WHERE user_id=? ORDER BY viewed_at DESC LIMIT 50)",(buyer["id"],buyer["id"]))
        return {"viewed":True}

    def recent_views(self, buyer):
        with self.auth.connect() as db:
            ids=[r[0] for r in db.execute("SELECT listing_id FROM buyer_vehicle_views WHERE user_id=? ORDER BY viewed_at DESC LIMIT 50",(buyer["id"],))]
        result=[]
        for listing_id in ids:
            try: result.append(self.vehicle(listing_id,public=True))
            except BuyerError: pass
        return result

    def create_inquiry(self, buyer, body):
        if buyer["role"]!="BUYER":
            raise BuyerError(403,"Buyer account required.")
        if not buyer.get("email_verified_at"):
            raise BuyerError(403,"Verify your email before sending an inquiry.")
        listing_id=text(body.get("listingId"),"listing",100,True)
        listing=self.vehicle(listing_id,public=True)
        quantity=positive_int(body.get("quantity"),"quantity")
        if quantity<listing["moq"]:
            raise BuyerError(400,"Quantity is below this supplier's MOQ.")
        country=text(body.get("destinationCountry"),"destination country",120,True)
        port=text(body.get("destinationPort"),"destination port",120)
        incoterm=body.get("incoterm","FOB")
        if incoterm not in TERMS:
            raise BuyerError(400,"Invalid Incoterm.")
        target=money_minor(body.get("targetPriceMinor"),"target price",optional=True)
        note=text(body.get("message"),"message",2000)
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM inquiry_rate_events WHERE created_at<?",(now-86400,))
            hourly=db.execute("SELECT count(*) FROM inquiry_rate_events WHERE buyer_id=? AND created_at>?",(buyer["id"],now-3600)).fetchone()[0]
            limited = self.platform.membership_policy_enabled() and not self.platform.member_in_db(db,buyer)
            daily=db.execute("SELECT count(*) FROM inquiry_rate_events WHERE buyer_id=? AND created_at>=?",(buyer["id"],now-86400)).fetchone()[0]
            lifetime=db.execute("SELECT count(*) FROM buyer_inquiries WHERE buyer_id=? AND request_id IS NULL",(buyer["id"],)).fetchone()[0]
            if limited and lifetime>=1:
                raise BuyerError(429,"Free accounts can send one inquiry in total. Apply for membership to send more.")
            if hourly>=10 or daily >= 30:
                raise BuyerError(429,"Inquiry limit reached. Please try again later.")
            duplicate=db.execute("""SELECT 1 FROM buyer_inquiries WHERE buyer_id=? AND listing_id=? AND created_at>?
                AND status!='CLOSED'""",(buyer["id"],listing_id,now-300)).fetchone()
            if duplicate:
                raise BuyerError(409,"This inquiry was already submitted recently.")
            inquiry_id=ident("INQ")
            db.execute("""INSERT INTO buyer_inquiries(id,buyer_id,vehicle_id,supplier_id,quantity,destination_country,
                destination_port,trade_term,note,status,created_at,updated_at,listing_id,target_price_minor,currency)
                VALUES (?,?,?,?,?,?,?,?,?,'SUBMITTED',?,?,?,?,?)""",
                (inquiry_id,buyer["id"],listing["model_id"],listing["supplier_id"],quantity,country,port,
                 incoterm,note,now,now,listing_id,target,listing["currency"]))
            db.execute("INSERT INTO inquiry_rate_events VALUES (?,?,?)",(ident("RATE"),buyer["id"],now))
            db.execute("INSERT OR IGNORE INTO supplier_crm(supplier_id,buyer_id,updated_at) VALUES (?,?,?)",(listing["supplier_id"],buyer["id"],now))
            assigned=db.execute("SELECT assigned_to FROM supplier_crm WHERE supplier_id=? AND buyer_id=?",(listing["supplier_id"],buyer["id"])).fetchone()[0]
            if assigned:
                db.execute("UPDATE buyer_inquiries SET assigned_to=? WHERE id=?",(assigned,inquiry_id))
                if assigned!=listing["supplier_id"]:
                    PlatformService.notify(db,assigned,"NEW_INQUIRY",inquiry_id,"/supplier/inquiries/"+inquiry_id+"?company="+listing["supplier_id"])
            PlatformService.notify(db,listing["supplier_id"],"NEW_INQUIRY",inquiry_id,"/supplier/inquiries/"+inquiry_id)
            self.audit(db,buyer["id"],"INQUIRY_SUBMITTED","inquiry",inquiry_id,listing["supplier_id"])
        return self.buyer_inquiry(buyer,inquiry_id)

    def buyer_inquiry(self, buyer, inquiry_id):
        with self.auth.connect() as db:
            row=db.execute("""SELECT i.*,u.company_name AS supplier_name FROM buyer_inquiries i
                LEFT JOIN users u ON u.id=i.supplier_id WHERE i.id=? AND i.buyer_id=?""",(inquiry_id,buyer["id"])).fetchone()
        if not row:
            raise BuyerError(404,"Inquiry not found.")
        return dict(row)

    def supplier_overview(self, supplier):
        """Exact counts in a single read snapshot; never aggregate a paged inbox.

        Sales reports follow current buyer assignments. Expiry is calculated for
        reporting without marking quotations viewed or changing records on GET.
        """
        now = int(time.time())
        since = now - 30 * 86400
        sales = supplier.get('supplier_role', 'OWNER') == 'SALES'
        if supplier.get('supplier_role', 'OWNER') not in ('OWNER', 'SALES'):
            raise BuyerError(403, 'Supplier access required.')
        with self.auth.connect() as db:
            db.execute('BEGIN')
            if sales:
                self.team.check_assignment(db, supplier)
            else:
                self.team.active_owner(db, supplier)
            company = supplier['id']
            actor = self.team.actor(supplier)
            inquiry_where = 'i.supplier_id=? AND i.listing_id IS NOT NULL'
            quote_where = 'q.supplier_id=? AND q.archived_at IS NULL'
            crm_where = 'c.supplier_id=?'
            inquiry_params = quote_params = crm_params = (company,)
            if sales:
                inquiry_where += ' AND i.assigned_to=?'
                inquiry_params += (actor,)
                quote_where += ''' AND EXISTS (SELECT 1 FROM buyer_inquiries qi
                    WHERE qi.id=q.inquiry_id AND qi.supplier_id=q.supplier_id
                    AND qi.buyer_id=q.buyer_id AND qi.assigned_to=?)'''
                quote_params += (actor,)
                crm_where += ' AND c.assigned_to=?'
                crm_params += (actor,)

            def grouped(table, where, params, expression='status'):
                return {row['state']: row['count'] for row in db.execute(
                    f'SELECT {expression} AS state,count(*) AS count FROM {table} WHERE {where} GROUP BY state', params)}

            inquiry_counts = grouped('buyer_inquiries i', inquiry_where, inquiry_params, 'i.status')
            # valid_until is a calendar date, inclusive of that day.
            quote_counts = grouped('trade_quotes q', quote_where, (str(date.today()),) + quote_params,
                "CASE WHEN q.status IN ('SENT','VIEWED') AND q.valid_until<? THEN 'EXPIRED' ELSE q.status END")
            crm_counts = grouped('supplier_crm c', crm_where, crm_params, 'c.status')
            vehicle_counts = None if sales else grouped('supplier_vehicles', 'supplier_id=?', (company,))
            counts = {
                'inquiries': sum(inquiry_counts.values()),
                'activeInquiries': sum(count for state, count in inquiry_counts.items() if state != 'CLOSED'),
                'sentQuotes': db.execute(f'SELECT count(*) FROM trade_quotes q WHERE {quote_where} AND q.sent_at IS NOT NULL', quote_params).fetchone()[0],
                'acceptedIntents': quote_counts.get('ACCEPTED', 0),
                'buyers': sum(crm_counts.values()),
            }
            if not sales:
                counts.update({
                    'vehicles': sum(count for state, count in vehicle_counts.items() if state != 'ARCHIVED'),
                    'pendingVehicleReviews': vehicle_counts.get('PENDING_REVIEW', 0),
                    'onlineVehicles': vehicle_counts.get('ONLINE', 0),
                })
            period = {
                'from': since, 'until': now,
                'inquiriesReceived': db.execute(f'SELECT count(*) FROM buyer_inquiries i WHERE {inquiry_where} AND i.created_at BETWEEN ? AND ?', inquiry_params + (since, now)).fetchone()[0],
                'quotesSent': db.execute(f'SELECT count(*) FROM trade_quotes q WHERE {quote_where} AND q.sent_at BETWEEN ? AND ?', quote_params + (since, now)).fetchone()[0],
                'followUpNotes': db.execute(f'''SELECT count(*) FROM supplier_crm_notes n
                    JOIN supplier_crm c ON c.supplier_id=n.supplier_id AND c.buyer_id=n.buyer_id
                    WHERE {crm_where} AND n.created_at BETWEEN ? AND ?''', crm_params + (since, now)).fetchone()[0],
            }
            recent = [dict(row) for row in db.execute(f'''SELECT i.id,i.vehicle_id,i.listing_id,
                i.quantity,i.destination_country,i.trade_term,i.status,i.created_at,i.updated_at,
                u.display_name AS buyer_name,u.company_name AS buyer_company
                FROM buyer_inquiries i JOIN users u ON u.id=i.buyer_id
                WHERE {inquiry_where} ORDER BY i.updated_at DESC,i.id DESC LIMIT 5''', inquiry_params)]
        return {
            'scope': 'ASSIGNED' if sales else 'COMPANY', 'generatedAt': now,
            'counts': counts, 'period': period, 'recentInquiries': recent,
            'inquiryStatuses': {state: inquiry_counts.get(state, 0) for state in sorted(INQUIRY_STATES)},
            'quoteStatuses': {state: quote_counts.get(state, 0) for state in sorted(QUOTE_STATES)},
            'customerStatuses': {state: crm_counts.get(state, 0) for state in ('NEW','FOLLOW_UP','HIGH_INTENT','DEAL','LOST')},
            'vehicleStatuses': None if sales else {state: vehicle_counts.get(state, 0) for state in sorted(LISTING_STATES)},
        }

    def supplier_inquiries(self, supplier, inquiry_id=None, page=None):
        with self.auth.connect() as db:
            self.team.check_assignment(db,supplier)
            sql="""SELECT i.*,u.display_name AS buyer_name,u.company_name AS buyer_company,u.email AS buyer_email
                FROM buyer_inquiries i JOIN users u ON u.id=i.buyer_id WHERE i.supplier_id=? AND i.listing_id IS NOT NULL"""
            args=[supplier["id"]]
            if supplier.get("supplier_role")=="SALES":
                sql+=" AND i.assigned_to=?";args.append(self.team.actor(supplier))
            if inquiry_id:
                sql+=" AND i.id=?";args.append(inquiry_id)
            rows=query_list(db,sql,args,order='i.updated_at DESC,i.id DESC',page=None if inquiry_id else page,legacy_limit=200)
            if inquiry_id and rows and rows[0]["viewed_at"] is None:
                now=int(time.time())
                db.execute("""UPDATE buyer_inquiries SET status=CASE WHEN status='SUBMITTED' THEN 'VIEWED' ELSE status END,
                    viewed_at=?,updated_at=? WHERE id=? AND supplier_id=? AND viewed_at IS NULL""",
                    (now,now,inquiry_id,supplier["id"]))
                if rows[0]["status"]=="SUBMITTED":
                    rows[0]["status"]="VIEWED"
                rows[0]["viewed_at"]=now
                rows[0]["updated_at"]=now
        return rows

    def update_inquiry(self, supplier, inquiry_id, body):
        status=body.get("status")
        if status not in ("CONTACTED","NEGOTIATING","CLOSED"):
            raise BuyerError(400,"Invalid inquiry status.")
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.team.check_assignment(db,supplier,inquiry=inquiry_id)
            row=db.execute("SELECT id FROM buyer_inquiries WHERE id=? AND supplier_id=? AND listing_id IS NOT NULL",(inquiry_id,supplier["id"])).fetchone()
            if not row:
                raise BuyerError(404,"Inquiry not found.")
            db.execute("UPDATE buyer_inquiries SET status=?,last_contact_at=?,updated_at=? WHERE id=? AND supplier_id=?",(status,now,now,inquiry_id,supplier["id"]))
            self.audit(db,self.team.actor(supplier),"INQUIRY_"+status,"inquiry",inquiry_id,supplier["id"])
        return self.supplier_inquiries(supplier,inquiry_id)[0]

    def crm(self, supplier, page=None):
        with self.auth.connect() as db:
            self.team.check_assignment(db,supplier)
            sql="""SELECT c.*,u.display_name,u.company_name,u.email,b.country,
                (SELECT count(*) FROM buyer_inquiries i WHERE i.supplier_id=c.supplier_id AND i.buyer_id=c.buyer_id) AS inquiry_count
                FROM supplier_crm c JOIN users u ON u.id=c.buyer_id
                LEFT JOIN buyer_profiles b ON b.user_id=c.buyer_id WHERE c.supplier_id=?"""
            args=[supplier["id"]]
            if supplier.get("supplier_role")=="SALES":
                sql+=" AND c.assigned_to=?";args.append(self.team.actor(supplier))
            return query_list(db,sql,args,order='c.updated_at DESC,c.buyer_id DESC',page=page)

    def update_crm(self, supplier, buyer_id, body):
        status=body.get("status")
        if status not in ("NEW","FOLLOW_UP","HIGH_INTENT","DEAL","LOST"):
            raise BuyerError(400,"Invalid CRM status.")
        tag=text(body.get("tag"),"tag",120)
        note=text(body.get("note"),"note",2000)
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.team.check_assignment(db,supplier,buyer=buyer_id)
            row=db.execute("SELECT 1 FROM supplier_crm WHERE supplier_id=? AND buyer_id=?",(supplier["id"],buyer_id)).fetchone()
            if not row:
                raise BuyerError(404,"Buyer relationship not found.")
            db.execute("UPDATE supplier_crm SET status=?,tag=?,updated_at=? WHERE supplier_id=? AND buyer_id=?",(status,tag,now,supplier["id"],buyer_id))
            if note:
                db.execute("INSERT INTO supplier_crm_notes VALUES (?,?,?,?,?,?)",(ident("NOTE"),supplier["id"],buyer_id,self.team.actor(supplier),note,now))
            self.audit(db,self.team.actor(supplier),"CRM_UPDATED","buyer",buyer_id,supplier["id"])
        return next(c for c in self.crm(supplier) if c["buyer_id"]==buyer_id)

    def quote_rows(self, owner, supplier=False, inquiry_id=None, page=None):
        column="supplier_id" if supplier else "buyer_id"
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if supplier:
                self.team.check_assignment(db,owner)
            expiry_sql = "UPDATE trade_quotes SET status='EXPIRED',updated_at=? WHERE status IN ('SENT','VIEWED') AND valid_until<? AND archived_at IS NULL AND sent_at IS NOT NULL AND "+column+"=?"
            expiry_args = [int(time.time()), date.today().isoformat(), owner["id"]]
            if supplier and owner.get("supplier_role")=="SALES":
                expiry_sql += " AND EXISTS (SELECT 1 FROM buyer_inquiries i WHERE i.id=trade_quotes.inquiry_id AND i.supplier_id=trade_quotes.supplier_id AND i.assigned_to=?)"
                expiry_args.append(self.team.actor(owner))
            db.execute(expiry_sql, expiry_args)
            sql=f"""SELECT q.*,u.company_name AS supplier_name FROM trade_quotes q
                JOIN users u ON u.id=q.supplier_id WHERE q.{column}=? AND q.archived_at IS NULL"""
            args=[owner["id"]]
            if supplier and owner.get("supplier_role")=="SALES":
                sql+=" AND EXISTS (SELECT 1 FROM buyer_inquiries i WHERE i.id=q.inquiry_id AND i.supplier_id=q.supplier_id AND i.assigned_to=?)"
                args.append(self.team.actor(owner))
            if not supplier:
                sql+=" AND q.status!='DRAFT' AND q.sent_at IS NOT NULL"
            if inquiry_id:
                sql+=" AND q.inquiry_id=?";args.append(inquiry_id)
            rows=query_list(db,sql,args,order='q.created_at DESC,q.id DESC',page=page,legacy_limit=200)
        for row in list_items(rows):
            row["vehicle"] = self.catalog.get(row["vehicle_id"])
        return rows

    def prepare_quote(self,supplier,inquiry,listing,body):
        quantity=positive_int(body.get("quantity",inquiry["quantity"]),"quantity")
        unit=money_minor(body.get("unitPriceMinor"))
        currency=text(body.get("currency",listing["currency"]),"currency",3,True).upper()
        if not re.fullmatch(r"[A-Z]{3}",currency):raise BuyerError(400,"Invalid currency.")
        term=body.get("incoterm",inquiry["trade_term"] or listing["incoterm"])
        if term not in TERMS:raise BuyerError(400,"Invalid Incoterm.")
        shipping=money_minor(body.get("shippingCostMinor"),"shipping cost",optional=True,allow_zero=True)
        total=money_minor(unit*quantity+(shipping or 0),"total price")
        now=int(time.time());send=body.get("send") is True
        return {"id":ident("QUO"),"inquiry_id":inquiry["id"],"supplier_id":supplier["id"],
                "buyer_id":inquiry["buyer_id"],"vehicle_id":inquiry["vehicle_id"],"trim":listing["trim"],
                "quantity":quantity,"unit_price_minor":unit,"total_price_minor":total,
                "shipping_cost_minor":shipping,"currency":currency,"incoterm":term,
                "origin_port":text(body.get("originPort",listing["origin_port"]),"origin port",120,True),
                "destination_port":text(body.get("destinationPort",inquiry["destination_port"]),"destination port",120),
                "payment_terms":text(body.get("paymentTerms",listing["payment_terms"]),"payment terms",500),
                "lead_time":text(body.get("leadTime",listing["lead_time"]),"lead time",120),
                "valid_until":iso_date(body.get("validUntil")),"notes":text(body.get("notes"),"notes",2000),
                "status":"SENT" if send else "DRAFT","sent_at":now if send else None,"created_at":now,"updated_at":now}

    def insert_quote(self,db,supplier,inquiry,quote):
        columns=list(quote)
        db.execute("INSERT INTO trade_quotes("+",".join(columns)+") VALUES ("+",".join(":"+name for name in columns)+")",quote)
        if quote["status"]=="SENT":
            db.execute("UPDATE buyer_inquiries SET status='QUOTED',updated_at=? WHERE id=? AND supplier_id=?",(quote["updated_at"],inquiry["id"],supplier["id"]))
            PlatformService.notify(db,inquiry["buyer_id"],"NEW_QUOTE",quote["id"],"/buyer/quotes/"+quote["id"])
        self.audit(db,self.team.actor(supplier),"QUOTE_SENT" if quote["status"]=="SENT" else "QUOTE_CREATED","quote",quote["id"],supplier["id"])

    def create_quote(self, supplier, inquiry_id, body):
        with self.auth.connect() as db:
            self.team.check_assignment(db,supplier,inquiry=inquiry_id)
            inquiry=db.execute("SELECT * FROM buyer_inquiries WHERE id=? AND supplier_id=? AND listing_id IS NOT NULL",(inquiry_id,supplier["id"])).fetchone()
        if not inquiry:raise BuyerError(404,"Inquiry not found.")
        if inquiry["status"]=="CLOSED":raise BuyerError(409,"Inquiry is closed.")
        listing=self.vehicle(inquiry["listing_id"],supplier_id=supplier["id"])
        quote=self.prepare_quote(supplier,inquiry,listing,body)
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.team.check_assignment(db,supplier,inquiry=inquiry_id)
            current=db.execute("SELECT status FROM buyer_inquiries WHERE id=? AND supplier_id=?",(inquiry_id,supplier["id"])).fetchone()
            if not current or current["status"]=="CLOSED":raise BuyerError(409,"Inquiry is closed or unavailable.")
            self.insert_quote(db,supplier,inquiry,quote)
        return {**quote,"vehicle":self.catalog.get(quote["vehicle_id"])}

    def buying_requests(self,supplier,request_id=None,page=None):
        with self.auth.connect() as db:
            sql="""SELECT r.id,r.title,r.vehicle_id,r.brand,r.vehicle_type,r.energy,r.year,r.quantity,
                r.budget_minor,r.currency,r.destination_country,r.destination_port,r.trade_term,
                r.delivery_date,r.note,r.created_at,r.published_at,
                (SELECT b.inquiry_id FROM buyer_request_responses b WHERE b.request_id=r.id AND b.supplier_id=?) AS response_inquiry_id
                FROM buyer_requests r JOIN users u ON u.id=r.buyer_id
                WHERE r.distribution_consent=1 AND r.status IN ('PUBLISHED','RESPONSES_RECEIVED')
                AND u.status='ACTIVE' AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL"""
            args=[supplier["id"]]
            if request_id:sql+=" AND r.id=?";args.append(request_id)
            rows=query_list(db,sql,args,order='r.published_at DESC,r.id DESC',
                            page=None if request_id else page,legacy_limit=100)
        for row in list_items(rows):row["model"]=self.catalog.get(row["vehicle_id"])
        return rows

    def respond_to_request(self,supplier,request_id,body):
        listing_id=text(body.get("listingId"),"listing",100,True)
        listing=self.vehicle(listing_id,supplier_id=supplier["id"],public=True)
        now=int(time.time());inquiry_id=ident("INQ")
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            request=db.execute("""SELECT r.* FROM buyer_requests r JOIN users u ON u.id=r.buyer_id
                WHERE r.id=? AND r.distribution_consent=1 AND r.status IN ('PUBLISHED','RESPONSES_RECEIVED')
                AND u.status='ACTIVE' AND u.email_verified_at IS NOT NULL""",(request_id,)).fetchone()
            if not request:raise BuyerError(404,"Published buying request not found.")
            current_listing=db.execute("SELECT status FROM supplier_vehicles WHERE id=? AND supplier_id=?",(listing_id,supplier["id"])).fetchone()
            if not current_listing or current_listing["status"]!="ONLINE":raise BuyerError(409,"The listing is no longer online.")
            if db.execute("SELECT 1 FROM buyer_request_responses WHERE request_id=? AND supplier_id=?",(request_id,supplier["id"])).fetchone():
                raise BuyerError(409,"Your company already responded. Continue in the existing inquiry.")
            if db.execute("SELECT count(*) FROM buyer_request_responses WHERE supplier_id=? AND created_at>?",(supplier["id"],now-3600)).fetchone()[0]>=10:
                raise BuyerError(429,"Buying request response limit reached. Try again later.")
            model=self.catalog[listing["model_id"]]
            if request["vehicle_id"] and request["vehicle_id"]!=listing["model_id"] or request["brand"] and request["brand"].casefold()!=model["brand"].casefold():
                raise BuyerError(400,"Choose a listing matching the requested model and brand.")
            if request["quantity"]<listing["moq"]:raise BuyerError(400,"The request quantity is below the listing MOQ.")
            inquiry={"id":inquiry_id,"buyer_id":request["buyer_id"],"vehicle_id":listing["model_id"],
                     "quantity":request["quantity"],"destination_port":request["destination_port"],"trade_term":request["trade_term"]}
            quote=self.prepare_quote(supplier,inquiry,listing,{**body,"quantity":request["quantity"],"send":True})
            db.execute("""INSERT INTO buyer_inquiries(id,buyer_id,vehicle_id,supplier_id,quantity,destination_country,
                destination_port,trade_term,note,status,created_at,updated_at,listing_id,target_price_minor,currency,request_id)
                VALUES (?,?,?,?,?,?,?,?,?,'SUBMITTED',?,?,?,?,?,?)""",
                (inquiry_id,request["buyer_id"],listing["model_id"],supplier["id"],request["quantity"],request["destination_country"],
                 request["destination_port"],quote["incoterm"],request["note"],now,now,listing_id,request["budget_minor"],request["currency"] or listing["currency"],request_id))
            db.execute("INSERT INTO buyer_request_responses VALUES (?,?,?,?)",(request_id,supplier["id"],inquiry_id,now))
            db.execute("INSERT OR IGNORE INTO supplier_crm(supplier_id,buyer_id,updated_at) VALUES (?,?,?)",(supplier["id"],request["buyer_id"],now))
            db.execute("UPDATE buyer_requests SET status='RESPONSES_RECEIVED',updated_at=? WHERE id=?",(now,request_id))
            self.insert_quote(db,supplier,inquiry,quote)
            self.audit(db,supplier["id"],"BUYING_REQUEST_RESPONDED","request",request_id,supplier["id"])
        return {"inquiryId":inquiry_id,"quote":{**quote,"vehicle":model}}

    def send_quote(self, supplier, quote_id):
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT inquiry_id,buyer_id,valid_until FROM trade_quotes WHERE id=? AND supplier_id=? AND status='DRAFT'",(quote_id,supplier["id"])).fetchone()
            if not row:
                raise BuyerError(404,"Draft quote not found.")
            self.team.check_assignment(db,supplier,inquiry=row["inquiry_id"])
            if date.fromisoformat(row["valid_until"]) < date.today():
                raise BuyerError(409,"The draft quote has expired. Create a new quotation.")
            inquiry=db.execute("SELECT status FROM buyer_inquiries WHERE id=? AND supplier_id=?",(row["inquiry_id"],supplier["id"])).fetchone()
            if not inquiry or inquiry["status"]=="CLOSED":
                raise BuyerError(409,"Inquiry is closed or unavailable.")
            PlatformService.notify(db,row["buyer_id"],"NEW_QUOTE",quote_id,"/buyer/quotes/"+quote_id)
            db.execute("UPDATE trade_quotes SET status='SENT',sent_at=?,updated_at=? WHERE id=? AND supplier_id=?",(now,now,quote_id,supplier["id"]))
            db.execute("UPDATE buyer_inquiries SET status='QUOTED',updated_at=? WHERE id=? AND supplier_id=?",(now,row["inquiry_id"],supplier["id"]))
            self.audit(db,self.team.actor(supplier),"QUOTE_SENT","quote",quote_id,supplier["id"])
            result = dict(db.execute("""SELECT q.*,u.company_name AS supplier_name FROM trade_quotes q
                JOIN users u ON u.id=q.supplier_id WHERE q.id=? AND q.supplier_id=?""",
                (quote_id,supplier["id"])).fetchone())
        return {**result,"vehicle":self.catalog.get(result["vehicle_id"])}

    def supplier_quote(self, supplier, quote_id):
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("""SELECT q.*,u.company_name AS buyer_company,u.display_name AS buyer_name
                FROM trade_quotes q JOIN users u ON u.id=q.buyer_id
                WHERE q.id=? AND q.supplier_id=? AND q.archived_at IS NULL""", (quote_id,supplier["id"])).fetchone()
            if not row:
                raise BuyerError(404, "Quote not found.")
            self.team.check_assignment(db,supplier,inquiry=row["inquiry_id"])
            result=dict(row)
            if row["status"] in ("SENT","VIEWED") and date.fromisoformat(row["valid_until"])<date.today():
                now=int(time.time())
                db.execute("UPDATE trade_quotes SET status='EXPIRED',updated_at=? WHERE id=? AND supplier_id=?",
                           (now,quote_id,supplier["id"]))
                result.update(status="EXPIRED",updated_at=now)
        return {**result,"vehicle":self.catalog.get(result["vehicle_id"])}

    def buyer_quote(self, buyer, quote_id, response=None):
        now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM trade_quotes WHERE id=? AND buyer_id=? AND status!='DRAFT' AND sent_at IS NOT NULL AND archived_at IS NULL",(quote_id,buyer["id"])).fetchone()
            if not row:
                raise BuyerError(404,"Quote not found.")
            expired=date.fromisoformat(row["valid_until"])<date.today()
            if expired and row["status"] in ("SENT","VIEWED"):
                db.execute("UPDATE trade_quotes SET status='EXPIRED',updated_at=? WHERE id=?",(now,quote_id))
            elif response in ("ACCEPTED","REJECTED"):
                if self.platform.membership_policy_enabled() and not self.platform.member_in_db(db,buyer):
                    raise BuyerError(403,"Membership is required to view prices and contacts.")
                if row["status"] not in ("SENT","VIEWED"):
                    raise BuyerError(409,"Quote cannot be responded to.")
                db.execute("UPDATE trade_quotes SET status=?,responded_at=?,updated_at=? WHERE id=? AND buyer_id=?",(response,now,now,quote_id,buyer["id"]))
                PlatformService.notify(db,row["supplier_id"],"QUOTE_"+response,quote_id,"/supplier/quotes")
                self.audit(db,buyer["id"],"QUOTE_"+response,"quote",quote_id,row["supplier_id"])
            elif response:
                raise BuyerError(400,"Invalid quote response.")
            elif row["status"]=="SENT":
                db.execute("UPDATE trade_quotes SET status='VIEWED',viewed_at=?,updated_at=? WHERE id=? AND buyer_id=?",(now,now,quote_id,buyer["id"]))
            result=db.execute("""SELECT q.*,u.company_name AS supplier_name FROM trade_quotes q
                JOIN users u ON u.id=q.supplier_id WHERE q.id=? AND q.buyer_id=?""",(quote_id,buyer["id"])).fetchone()
        return {**dict(result), "vehicle": self.catalog.get(result["vehicle_id"]),
                "supplierContact": self.buyer_supplier_contact(buyer, result["inquiry_id"])}

    def buyer_supplier_contact(self, buyer, inquiry_id):
        """Only the inquiry owner may retrieve this business contact."""
        with self.auth.connect() as db:
            row=db.execute("""SELECT u.company_name,u.email,a.contact_name,a.contact_phone,a.website
                FROM buyer_inquiries i JOIN users u ON u.id=i.supplier_id
                JOIN supplier_applications a ON a.supplier_id=i.supplier_id
                WHERE i.id=? AND i.buyer_id=? AND u.status='ACTIVE' AND a.status='APPROVED'""",
                (inquiry_id,buyer["id"])).fetchone()
        return dict(row) if row else None

    def admin_overview(self):
        with self.auth.connect() as db:
            def count(sql): return db.execute(sql).fetchone()[0]
            return {"users":count("SELECT count(*) FROM users"),"buyers":count("SELECT count(*) FROM users WHERE role='BUYER'"),
                "suppliers":count("SELECT count(*) FROM supplier_applications WHERE status='APPROVED'"),
                "publicSuppliers":count("""SELECT count(*) FROM supplier_profiles p
                    JOIN supplier_applications a ON a.supplier_id=p.user_id
                    JOIN users u ON u.id=p.user_id WHERE """+PUBLIC_SUPPLIER_WHERE),
                "pendingSuppliers":count("SELECT count(*) FROM supplier_applications WHERE status='PENDING'"),
                "vehicles":count("SELECT count(*) FROM supplier_vehicles WHERE archived_at IS NULL"),
                "pendingVehicles":count("SELECT count(*) FROM supplier_vehicles WHERE status='PENDING_REVIEW'"),
                "onlineVehicles":count("SELECT count(*) FROM supplier_vehicles WHERE status='ONLINE'"),
                "publicVehicles":count("""SELECT count(*) FROM supplier_vehicles v
                    JOIN supplier_profiles p ON p.user_id=v.supplier_id
                    JOIN supplier_applications a ON a.supplier_id=v.supplier_id
                    JOIN users u ON u.id=v.supplier_id WHERE """+PUBLIC_VEHICLE_WHERE),
                "inquiries":count("SELECT count(*) FROM buyer_inquiries"),
                "quotes":count("SELECT count(*) FROM trade_quotes WHERE sent_at IS NOT NULL"),
                "memberships":count("SELECT count(*) FROM buyer_memberships WHERE status='ACTIVE' AND end_at>strftime('%s','now')"),
                "reports":count("SELECT count(*) FROM listing_reports")}

    def crm_detail(self, supplier, buyer_id, pages=None):
        relationship = next((row for row in self.crm(supplier) if row["buyer_id"] == buyer_id), None)
        if not relationship:
            raise BuyerError(404, "Buyer relationship not found.")
        with self.auth.connect() as db:
            db.execute('BEGIN')
            self.team.check_assignment(db, supplier, buyer=buyer_id)
            pages = pages or {}
            args = (supplier['id'], buyer_id)
            notes = query_list(db, 'SELECT id,actor_id,note,created_at FROM supplier_crm_notes WHERE supplier_id=? AND buyer_id=?', args,
                               order='created_at DESC,id DESC', page=pages.get('notesPage'), legacy_limit=100)
            inquiries = query_list(db, 'SELECT id,vehicle_id,quantity,status,created_at FROM buyer_inquiries WHERE supplier_id=? AND buyer_id=?', args,
                                   order='created_at DESC,id DESC', page=pages.get('inquiriesPage'), legacy_limit=100)
            quotes = query_list(db, 'SELECT id,status,total_price_minor,currency,created_at FROM trade_quotes WHERE supplier_id=? AND buyer_id=?', args,
                                order='created_at DESC,id DESC', page=pages.get('quotesPage'), legacy_limit=100)
        return {**relationship, "notes": notes, "inquiries": inquiries, "quotes": quotes}

    def cancel_quote(self, supplier, quote_id):
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status,inquiry_id,buyer_id,valid_until FROM trade_quotes WHERE id=? AND supplier_id=? AND archived_at IS NULL", (quote_id, supplier["id"])).fetchone()
            if not row:
                raise BuyerError(404, "Quote not found.")
            self.team.check_assignment(db,supplier,inquiry=row["inquiry_id"])
            if row["status"] not in ("DRAFT", "SENT", "VIEWED"):
                raise BuyerError(409, "This quote cannot be cancelled.")
            if row["status"] != "DRAFT" and date.fromisoformat(row["valid_until"]) < date.today():
                raise BuyerError(409, "This quote has expired.")
            db.execute("UPDATE trade_quotes SET status='CANCELLED',updated_at=? WHERE id=?", (int(time.time()), quote_id))
            if row["status"] != "DRAFT":
                PlatformService.notify(db, row["buyer_id"], "QUOTE_CANCELLED", quote_id, "/buyer/quotes/"+quote_id)
            self.audit(db, self.team.actor(supplier), "QUOTE_CANCELLED", "quote", quote_id, supplier["id"])
        return {"id": quote_id, "status": "CANCELLED"}

    def admin_users(self, keyword="", page=None):
        keyword = text(keyword, "search", 160)
        with self.auth.connect() as db:
            return query_list(db, "SELECT id,email,display_name,company_name,role,status,email_verified_at,created_at,last_login_at FROM users WHERE email LIKE ? OR company_name LIKE ?",
                              ("%"+keyword+"%", "%"+keyword+"%"), order='created_at DESC,id DESC', page=page, legacy_limit=100)

    def admin_user_detail(self, admin, user_id):
        """Read an allowlisted account summary; never return authentication records."""
        user_id = text(user_id, "user id", 100, True)
        with self.auth.connect() as db:
            # Recheck the principal in the same connection as the sensitive read.
            allowed = db.execute("SELECT 1 FROM users WHERE id=? AND role='PLATFORM_ADMIN' "
                                 "AND status='ACTIVE' AND deleted_at IS NULL", (admin["id"],)).fetchone()
            if not allowed:
                raise BuyerError(403, "Platform admin required.")
            row = db.execute("""SELECT id,email,display_name,company_name,role,status,email_verified_at,
                created_at,last_login_at,deleted_at,preferred_language FROM users WHERE id=?""", (user_id,)).fetchone()
            if not row:
                raise BuyerError(404, "Account not found.")
            profile = db.execute("SELECT country,city,contact_person,updated_at FROM buyer_profiles WHERE user_id=?",
                                 (user_id,)).fetchone()
            owner = db.execute("""SELECT a.supplier_id,u.company_name,a.status AS verification_status,
                'OWNER' AS role,u.status AS account_status FROM supplier_applications a
                JOIN users u ON u.id=a.supplier_id WHERE a.supplier_id=?""", (user_id,)).fetchone()
            workspaces = [dict(owner)] if owner else []
            workspaces += [dict(item) for item in db.execute("""SELECT m.supplier_id,u.company_name,m.role,
                a.status AS verification_status,m.status AS membership_status,u.status AS account_status
                FROM supplier_team_members m JOIN users u ON u.id=m.supplier_id
                JOIN supplier_applications a ON a.supplier_id=m.supplier_id
                WHERE m.user_id=? ORDER BY m.joined_at DESC LIMIT 50""", (user_id,))]
            counts = {}
            for label, table, key in (("buyerInquiries", "buyer_inquiries", "buyer_id"),
                                     ("buyerQuotes", "trade_quotes", "buyer_id"),
                                     ("supplierInquiries", "buyer_inquiries", "supplier_id"),
                                     ("supplierQuotes", "trade_quotes", "supplier_id")):
                # Table and column names are fixed constants, never request input.
                # A buyer has only received quotations that have actually been sent.
                sent_only = " AND sent_at IS NOT NULL" if label == "buyerQuotes" else ""
                counts[label] = db.execute(f"SELECT count(*) FROM {table} WHERE {key}=?"+sent_only, (user_id,)).fetchone()[0]
            activity = [dict(item) for item in db.execute("""SELECT action,entity_type,entity_id,created_at
                FROM trade_audit WHERE actor_user_id=? OR (entity_type='user' AND entity_id=?)
                ORDER BY created_at DESC,id DESC LIMIT 30""", (user_id,user_id))]
            return {"account":dict(row), "profile":dict(profile) if profile else None,
                    "membership":BuyerService.membership(db,user_id), "supplierWorkspaces":workspaces,
                    "counts":counts, "activity":activity}

    def user_status(self, admin, user_id, body):
        status = body.get("status")
        reason = text(body.get("reason"), "reason", 1000, True)
        if status not in ("ACTIVE", "SUSPENDED"):
            raise BuyerError(400, "Invalid account status.")
        with self.auth.connect() as db:
            row = db.execute("SELECT role,status FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or row["role"] == "PLATFORM_ADMIN" or row["status"] == "DELETED":
                raise BuyerError(403, "This account cannot be changed here.")
            db.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            self.audit(db, admin["id"], "USER_"+status, "user", user_id, metadata=reason)
        return {"id": user_id, "status": status}

    def audit_rows(self, page=None):
        with self.auth.connect() as db:
            return query_list(db, "SELECT * FROM trade_audit", order='created_at DESC,id DESC', page=page, legacy_limit=200)
