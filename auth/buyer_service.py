"""Buyer-only persistence for AUTOLINK's B2B sourcing workspace.

Catalogue models are references. Supplier offers, membership payments and
supplier replies are never synthesized from catalogue or demonstration data.
"""

import json
import re
import sqlite3
import time
import uuid
from datetime import date
from pathlib import Path


CATALOG = {item["id"]: item for item in json.loads((Path(__file__).parent / "catalog.json").read_text())}
INQUIRY_STATES = {"WAITING", "QUOTED", "DISCUSSION", "CLOSED", "CANCELLED"}
REQUEST_STATES = {"DRAFT", "PUBLISHED", "RESPONSES_RECEIVED", "CLOSED"}


class BuyerError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def text(value, label, max_length=320, required=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise BuyerError(400, f"{label} must be text.")
    value = value.strip()
    if len(value) > max_length or (required and not value):
        raise BuyerError(400, f"Invalid {label}.")
    return value


def positive_int(value, label, default=1):
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100000:
        raise BuyerError(400, f"Invalid {label}.")
    return value


class BuyerService:
    def __init__(self, auth):
        self.auth = auth
        from catalog_service import CatalogService
        self.catalog = CatalogService(auth)
        with self.auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS buyer_profiles (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    contact_person TEXT NOT NULL DEFAULT '', job_title TEXT NOT NULL DEFAULT '',
                    phone TEXT NOT NULL DEFAULT '', whatsapp TEXT NOT NULL DEFAULT '',
                    country TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
                    website TEXT NOT NULL DEFAULT '', company_type TEXT NOT NULL DEFAULT '',
                    target_market TEXT NOT NULL DEFAULT '', preferred_brands TEXT NOT NULL DEFAULT '',
                    annual_volume TEXT NOT NULL DEFAULT '', introduction TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED', updated_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS buyer_saved_vehicles (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    vehicle_id TEXT NOT NULL, created_at INTEGER NOT NULL,
                    PRIMARY KEY(user_id,vehicle_id)
                );
                CREATE TABLE IF NOT EXISTS buyer_compared_vehicles (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    vehicle_id TEXT NOT NULL, created_at INTEGER NOT NULL,
                    PRIMARY KEY(user_id,vehicle_id)
                );
                CREATE TABLE IF NOT EXISTS supplier_profiles (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    published INTEGER NOT NULL DEFAULT 0,
                    country TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                    updated_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS buyer_saved_suppliers (
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    created_at INTEGER NOT NULL,
                    PRIMARY KEY(user_id,supplier_id)
                );
                CREATE TABLE IF NOT EXISTS buyer_inquiries (
                    id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    vehicle_id TEXT NOT NULL, supplier_id TEXT REFERENCES supplier_profiles(user_id),
                    quantity INTEGER NOT NULL, destination_country TEXT NOT NULL DEFAULT '',
                    destination_port TEXT NOT NULL DEFAULT '', trade_term TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'WAITING',
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS buyer_inquiries_owner ON buyer_inquiries(buyer_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS buyer_inquiry_replies (
                    id TEXT PRIMARY KEY, inquiry_id TEXT NOT NULL REFERENCES buyer_inquiries(id) ON DELETE CASCADE,
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    message TEXT NOT NULL, amount_minor INTEGER, currency TEXT,
                    created_at INTEGER NOT NULL, read_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS buyer_requests (
                    id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL, vehicle_id TEXT, brand TEXT NOT NULL DEFAULT '',
                    vehicle_type TEXT NOT NULL DEFAULT '', energy TEXT NOT NULL DEFAULT '',
                    year INTEGER, quantity INTEGER NOT NULL, budget_minor INTEGER, currency TEXT,
                    destination_country TEXT NOT NULL DEFAULT '', destination_port TEXT NOT NULL DEFAULT '',
                    trade_term TEXT NOT NULL DEFAULT '', delivery_date TEXT NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'DRAFT',
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS buyer_requests_owner ON buyer_requests(buyer_id,created_at DESC);
                CREATE TABLE IF NOT EXISTS buyer_memberships (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    plan TEXT NOT NULL, status TEXT NOT NULL, start_at INTEGER NOT NULL,
                    end_at INTEGER NOT NULL, auto_renew INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS buyer_membership_payments (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    membership_id TEXT NOT NULL REFERENCES buyer_memberships(id),
                    amount_minor INTEGER NOT NULL, currency TEXT NOT NULL, paid_at INTEGER,
                    status TEXT NOT NULL, transaction_id TEXT NOT NULL UNIQUE
                );
            """)
            request_columns={row["name"] for row in db.execute("PRAGMA table_info(buyer_requests)")}
            for name,declaration in (("distribution_consent","INTEGER NOT NULL DEFAULT 0"),("published_at","INTEGER")):
                if name not in request_columns:
                    db.execute(f"ALTER TABLE buyer_requests ADD COLUMN {name} {declaration}")

    def require(self, token, role="BUYER"):
        user = self.auth.user_for_token(token)
        allowed = ('BUYER', 'MERCHANT', 'SUPPLIER') if role == 'BUYER' else (role,)
        if user["role"] not in allowed:
            raise BuyerError(403, "This account does not have access to this workspace.")
        return user

    def model(self, vehicle_id):
        item = self.catalog.get(vehicle_id)
        if not item or not self.catalog.enabled(vehicle_id):
            raise BuyerError(404, "Vehicle model was not found in the catalogue.")
        return item

    @staticmethod
    def membership(db, user_id):
        row = db.execute("SELECT * FROM buyer_memberships WHERE user_id=? ORDER BY end_at DESC LIMIT 1", (user_id,)).fetchone()
        if not row:
            return {"status": "FREE", "plan": None, "startAt": None, "endAt": None, "autoRenew": False}
        status = "ACTIVE" if row["status"] == "ACTIVE" and row["end_at"] > int(time.time()) else "EXPIRED"
        return {"status": status, "plan": row["plan"], "startAt": row["start_at"],
                "endAt": row["end_at"], "autoRenew": bool(row["auto_renew"])}

    def profile(self, user):
        with self.auth.connect() as db:
            row = db.execute("SELECT * FROM buyer_profiles WHERE user_id=?", (user["id"],)).fetchone()
        fields = {field: row[field] if row else "" for field in (
            "contact_person", "job_title", "phone", "whatsapp", "country", "city", "website",
            "company_type", "target_market", "preferred_brands", "annual_volume", "introduction")}
        return {"companyName": user["company_name"], "email": user["email"],
                "verificationStatus": row["verification_status"] if row else "UNVERIFIED", **fields}

    def update_profile(self, user, body):
        company = text(body.get("companyName"), "company name", 160, True)
        names = ("contact_person", "job_title", "phone", "whatsapp", "country", "city", "website",
                 "company_type", "target_market", "preferred_brands", "annual_volume", "introduction")
        values = [text(body.get(key), key, 2000 if key == "introduction" else 320) for key in names]
        if values[6] and not re.match(r"^https?://[^\s]+$", values[6]):
            raise BuyerError(400, "Website must start with http:// or https://.")
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute("""SELECT company_name FROM users WHERE id=? AND status='ACTIVE'
                AND deleted_at IS NULL AND role IN ('BUYER','MERCHANT','SUPPLIER')""", (user['id'],)).fetchone()
            if not current:
                raise BuyerError(403, 'An active business account is required.')
            has_review = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_applications'").fetchone()
            locked = has_review and db.execute("""SELECT 1 FROM supplier_applications WHERE supplier_id=?
                AND status IN ('PENDING','APPROVED','SUSPENDED')""", (user['id'],)).fetchone()
            if locked and company != current['company_name']:
                raise BuyerError(409, 'Company name is locked during supplier review or while the company is active. Contact support.')
            db.execute("UPDATE users SET company_name=? WHERE id=?", (company, user["id"]))
            db.execute("INSERT INTO buyer_profiles(user_id," + ",".join(names) + ",updated_at) VALUES (" + ",".join("?" for _ in range(len(names) + 2)) + ") ON CONFLICT(user_id) DO UPDATE SET " + ",".join(key + "=excluded." + key for key in names) + ",updated_at=excluded.updated_at", (user["id"], *values, int(time.time())))
        return self.profile({**user, "company_name": company})

    def vehicle_list(self, user, kind):
        table = "buyer_saved_vehicles" if kind == "favorites" else "buyer_compared_vehicles"
        with self.auth.connect() as db:
            rows = db.execute(f"SELECT vehicle_id,created_at FROM {table} WHERE user_id=? ORDER BY created_at DESC", (user["id"],)).fetchall()
        return [{**self.catalog[row["vehicle_id"]], "savedAt": row["created_at"]} for row in rows if row["vehicle_id"] in self.catalog]

    def add_vehicle(self, user, kind, vehicle_id):
        self.model(vehicle_id)
        table = "buyer_saved_vehicles" if kind == "favorites" else "buyer_compared_vehicles"
        with self.auth.connect() as db:
            if kind == "compare":
                count = db.execute("SELECT count(*) FROM buyer_compared_vehicles WHERE user_id=?", (user["id"],)).fetchone()[0]
                exists = db.execute("SELECT 1 FROM buyer_compared_vehicles WHERE user_id=? AND vehicle_id=?", (user["id"], vehicle_id)).fetchone()
                if count >= 4 and not exists:
                    raise BuyerError(409, "You can compare up to four vehicles.")
            db.execute(f"INSERT OR IGNORE INTO {table}(user_id,vehicle_id,created_at) VALUES (?,?,?)", (user["id"], vehicle_id, int(time.time())))
        return self.vehicle_list(user, kind)

    def remove_vehicle(self, user, kind, vehicle_id):
        table = "buyer_saved_vehicles" if kind == "favorites" else "buyer_compared_vehicles"
        with self.auth.connect() as db:
            db.execute(f"DELETE FROM {table} WHERE user_id=? AND vehicle_id=?", (user["id"], vehicle_id))
        return self.vehicle_list(user, kind)

    def suppliers(self, user, saved=False):
        with self.auth.connect() as db:
            has_review = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_applications'").fetchone()
            review_join = " JOIN supplier_applications a ON a.supplier_id=p.user_id" if has_review else ""
            review_filter = " AND a.status='APPROVED'" if has_review else ""
            saved_join = " JOIN buyer_saved_suppliers s ON s.supplier_id=p.user_id" if saved else ""
            selected = "s.created_at" if saved else "NULL"
            args = (user["id"],) if saved else ()
            saved_filter = " AND s.user_id=?" if saved else ""
            rows = db.execute("SELECT p.user_id,p.country,p.description,u.company_name,"+selected+" AS created_at FROM supplier_profiles p JOIN users u ON u.id=p.user_id"+review_join+saved_join+" WHERE p.published=1 AND u.status='ACTIVE' AND u.is_test_workspace=0 AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL AND u.role IN ('BUYER','MERCHANT','SUPPLIER')"+review_filter+saved_filter+" ORDER BY p.updated_at DESC",args).fetchall()
        return [{"id":r["user_id"],"companyName":r["company_name"],"country":r["country"],
                 "description":r["description"],"verificationStatus":"BUSINESS_ACCOUNT_ACTIVE" if has_review else "UNVERIFIED","savedAt":r["created_at"]} for r in rows]

    def save_supplier(self, user, supplier_id, add=True):
        supplier_id = text(supplier_id, "supplier", 100, True)
        with self.auth.connect() as db:
            if add:
                has_review = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='supplier_applications'").fetchone()
                join = " JOIN supplier_applications a ON a.supplier_id=p.user_id" if has_review else ""
                review = " AND a.status='APPROVED'" if has_review else ""
                supplier = db.execute("SELECT 1 FROM supplier_profiles p JOIN users u ON u.id=p.user_id"+join+
                    " WHERE p.user_id=? AND p.published=1 AND u.status='ACTIVE' AND u.is_test_workspace=0 AND u.deleted_at IS NULL"
                    " AND u.email_verified_at IS NOT NULL AND u.role IN ('BUYER','MERCHANT','SUPPLIER')"+review, (supplier_id,)).fetchone()
                if not supplier:
                    raise BuyerError(404, "Published supplier profile was not found.")
                db.execute("INSERT OR IGNORE INTO buyer_saved_suppliers(user_id,supplier_id,created_at) VALUES (?,?,?)", (user["id"], supplier_id, int(time.time())))
            else:
                db.execute("DELETE FROM buyer_saved_suppliers WHERE user_id=? AND supplier_id=?", (user["id"], supplier_id))
        return self.suppliers(user, saved=True)

    def inquiry_rows(self, user, inquiry_id=None, page=None, status=None, keyword='', limit=None):
        from pagination import query_list, list_items
        status = text(status, 'inquiry status', 30)
        keyword = text(keyword, 'search filter', 160)
        if status and status != 'ALL' and status not in INQUIRY_STATES | {'SUBMITTED','VIEWED','CONTACTED','NEGOTIATING'}:
            raise BuyerError(400, 'Invalid inquiry status.')
        with self.auth.connect() as db:
            sql = """SELECT i.*,u.company_name AS supplier_name,
                (SELECT count(*) FROM buyer_inquiry_replies r WHERE r.inquiry_id=i.id AND r.read_at IS NULL) AS unread_replies
                FROM buyer_inquiries i LEFT JOIN users u ON u.id=i.supplier_id
                LEFT JOIN catalog_models m ON m.id=i.vehicle_id LEFT JOIN catalog_brands b ON b.id=m.brand_id
                WHERE i.buyer_id=?"""
            args = [user["id"]]
            if inquiry_id:
                sql += " AND i.id=?"
                args.append(inquiry_id)
            if status and status != 'ALL':
                sql += ' AND i.status=?'; args.append(status)
            if keyword:
                # Literal Unicode substring search: %, _ and quotes never become SQL wildcards/code.
                db.create_function('autolink_casefold', 1, lambda v: str(v or '').casefold(), deterministic=True)
                sql += " AND instr(autolink_casefold(i.id||' '||COALESCE(b.name,'')||' '||COALESCE(m.name,'')||' '||COALESCE(u.company_name,'')),?)>0"
                args.append(keyword.casefold())
            rows = query_list(db, sql, args, order='i.updated_at DESC,i.id DESC',
                              page=None if inquiry_id else page, legacy_limit=limit)
            result = []
            for row in list_items(rows):
                item = dict(row)
                item["vehicle"] = self.catalog.get(item["vehicle_id"])
                item["replies"] = [dict(r) for r in db.execute("SELECT id,message,amount_minor,currency,created_at,read_at FROM buyer_inquiry_replies WHERE inquiry_id=? ORDER BY created_at", (item["id"],))] if inquiry_id else []
                result.append(item)
        return {**rows, 'items': result} if isinstance(rows, dict) else result

    def create_inquiry(self, user, body):
        vehicle_id = text(body.get("vehicleId"), "vehicle model", 100, True)
        self.model(vehicle_id)
        supplier_id = text(body.get("supplierId"), "supplier", 100) or None
        if supplier_id:
            with self.auth.connect() as db:
                if not db.execute("SELECT 1 FROM supplier_profiles WHERE user_id=? AND published=1", (supplier_id,)).fetchone():
                    raise BuyerError(404, "Published supplier profile was not found.")
        now = int(time.time())
        inquiry_id = "INQ-" + uuid.uuid4().hex[:12].upper()
        with self.auth.connect() as db:
            db.execute("INSERT INTO buyer_inquiries(id,buyer_id,vehicle_id,supplier_id,quantity,destination_country,destination_port,trade_term,note,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (inquiry_id, user["id"], vehicle_id, supplier_id, positive_int(body.get("quantity"), "quantity"),
                        text(body.get("destinationCountry"), "destination country", 120), text(body.get("destinationPort"), "destination port", 120),
                        text(body.get("tradeTerm"), "trade term", 30), text(body.get("note"), "note", 2000), now, now))
        return self.inquiry_rows(user, inquiry_id)[0]

    def requests(self, user, request_id=None, page=None):
        from pagination import query_list
        with self.auth.connect() as db:
            responses_exist=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='buyer_request_responses'").fetchone()
            count="(SELECT count(*) FROM buyer_request_responses b WHERE b.request_id=r.id)" if responses_exist else "0"
            sql=f"SELECT r.*,{count} AS response_count FROM buyer_requests r WHERE r.buyer_id=?"
            args=[user['id']]
            if request_id: sql+=' AND r.id=?'; args.append(request_id)
            return query_list(db,sql,args,order='r.updated_at DESC,r.id DESC',page=None if request_id else page)

    def check_request_publish(self, db, user, body, request_id=None):
        if not user.get("email_verified_at"):
            raise BuyerError(403,"Verify your email before publishing a buying request.")
        if body.get("publishConsent") is not True:
            raise BuyerError(400,"Agree to share this request with verified suppliers before publishing.")
        now=int(time.time())
        args=[user["id"],now-86400]
        exclusion=" AND id!=?" if request_id else ""
        if request_id:args.append(request_id)
        rows=db.execute("SELECT published_at FROM buyer_requests WHERE buyer_id=? AND published_at>?"+exclusion,args).fetchall()
        if len(rows)>=10 or sum(row["published_at"]>now-3600 for row in rows)>=3:
            raise BuyerError(429,"Buying request publication limit reached. Try again later.")

    def update_request_status(self,user,request_id,body):
        status=body.get("status")
        if status not in ("PUBLISHED","CLOSED"):
            raise BuyerError(400,"Invalid request status.")
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT * FROM buyer_requests WHERE id=? AND buyer_id=?",(request_id,user["id"])).fetchone()
            if not row:
                raise BuyerError(404,"Buying request not found.")
            if row["status"]=="CLOSED":
                raise BuyerError(409,"This buying request is closed. Create a new request if needed.")
            if status=="PUBLISHED":
                if row["distribution_consent"]:
                    raise BuyerError(409,"This request is already shared with verified suppliers.")
                if not row["destination_country"]:
                    raise BuyerError(400,"Destination country is required for publication.")
                self.check_request_publish(db,user,body,request_id)
                db.execute("UPDATE buyer_requests SET status='PUBLISHED',distribution_consent=1,published_at=?,updated_at=? WHERE id=? AND buyer_id=?",(int(time.time()),int(time.time()),request_id,user["id"]))
            else:
                db.execute("UPDATE buyer_requests SET status='CLOSED',distribution_consent=0,updated_at=? WHERE id=? AND buyer_id=?",(int(time.time()),request_id,user["id"]))
        return self.requests(user, request_id)[0]

    def create_request(self, user, body):
        title = text(body.get("title"), "request title", 160, True)
        vehicle_id = text(body.get("vehicleId"), "vehicle model", 100) or None
        if vehicle_id:
            self.model(vehicle_id)
        status = body.get("status", "DRAFT")
        if status not in ("DRAFT", "PUBLISHED"):
            raise BuyerError(400, "Invalid request status.")
        if user["role"] not in ('BUYER', 'MERCHANT', 'SUPPLIER'):
            raise BuyerError(403,"Buyer account required.")
        now = int(time.time())
        values = [title, vehicle_id, text(body.get("brand"), "brand", 120), text(body.get("vehicleType"), "vehicle type", 100),
                  text(body.get("energy"), "energy", 100), body.get("year"), positive_int(body.get("quantity"), "quantity"),
                  body.get("budgetMinor"), text(body.get("currency"), "currency", 3),
                  text(body.get("destinationCountry"), "destination country", 120), text(body.get("destinationPort"), "destination port", 120),
                  text(body.get("tradeTerm"), "trade term", 30), text(body.get("deliveryDate"), "delivery date", 30),
                  text(body.get("note"), "note", 2000), status]
        if values[5] is not None and (isinstance(values[5],bool) or not isinstance(values[5], int) or not 1900 <= values[5] <= 2100):
            raise BuyerError(400, "Invalid model year.")
        if values[7] is not None and (isinstance(values[7],bool) or not isinstance(values[7], int) or not 0 <= values[7] <= 10**12):
            raise BuyerError(400, "Invalid budget.")
        if values[8] and not re.fullmatch(r"[A-Z]{3}",values[8]):
            raise BuyerError(400,"Invalid currency.")
        if values[11] and values[11] not in ("FOB","CIF","CFR","EXW"):
            raise BuyerError(400,"Invalid Incoterm.")
        if values[12]:
            try:date.fromisoformat(values[12])
            except ValueError as exc:raise BuyerError(400,"Invalid delivery date.") from exc
        if status=="PUBLISHED" and not values[9]:
            raise BuyerError(400,"Destination country is required for publication.")
        request_id = "REQ-" + uuid.uuid4().hex[:12].upper()
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if status=="PUBLISHED":self.check_request_publish(db,user,body)
            duplicate=db.execute("SELECT 1 FROM buyer_requests WHERE buyer_id=? AND title=? AND quantity=? AND destination_country=? AND created_at>?",(user["id"],title,values[6],values[9],now-300)).fetchone()
            if duplicate:raise BuyerError(409,"This buying request was already saved recently.")
            if db.execute("SELECT count(*) FROM buyer_requests WHERE buyer_id=? AND created_at>?",(user["id"],now-86400)).fetchone()[0]>=20:
                raise BuyerError(429,"Buying request limit reached. Try again later.")
            db.execute("INSERT INTO buyer_requests(id,buyer_id,title,vehicle_id,brand,vehicle_type,energy,year,quantity,budget_minor,currency,destination_country,destination_port,trade_term,delivery_date,note,status,created_at,updated_at,distribution_consent,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (request_id, user["id"], *values, now, now,1 if status=="PUBLISHED" else 0,now if status=="PUBLISHED" else None))
        return self.requests(user, request_id)[0]

    def messages(self, user):
        with self.auth.connect() as db:
            return [dict(r) for r in db.execute("SELECT r.id,r.inquiry_id,r.message,r.amount_minor,r.currency,r.created_at,r.read_at,u.company_name AS supplier_name FROM buyer_inquiry_replies r JOIN buyer_inquiries i ON i.id=r.inquiry_id JOIN users u ON u.id=r.supplier_id WHERE i.buyer_id=? ORDER BY r.created_at DESC", (user["id"],))]

    def mark_read(self, user, reply_id):
        with self.auth.connect() as db:
            cursor = db.execute("UPDATE buyer_inquiry_replies SET read_at=COALESCE(read_at,?) WHERE id=? AND inquiry_id IN (SELECT id FROM buyer_inquiries WHERE buyer_id=?)", (int(time.time()), reply_id, user["id"]))
            if cursor.rowcount != 1:
                raise BuyerError(404, "Message was not found.")
        return {"read": True}

    def overview(self, user):
        with self.auth.connect() as db:
            counts = {
                "savedVehicles": db.execute("SELECT count(*) FROM buyer_saved_vehicles WHERE user_id=?", (user["id"],)).fetchone()[0],
                "activeInquiries": db.execute("SELECT count(*) FROM buyer_inquiries WHERE buyer_id=? AND status IN ('WAITING','SUBMITTED','VIEWED','CONTACTED','QUOTED','NEGOTIATING','DISCUSSION')", (user["id"],)).fetchone()[0],
                "supplierReplies": db.execute("SELECT count(*) FROM buyer_inquiry_replies WHERE read_at IS NULL AND inquiry_id IN (SELECT id FROM buyer_inquiries WHERE buyer_id=?)", (user["id"],)).fetchone()[0],
                "savedSuppliers": db.execute("SELECT count(*) FROM buyer_saved_suppliers WHERE user_id=?", (user["id"],)).fetchone()[0],
                "quotes": db.execute("SELECT count(*) FROM trade_quotes WHERE buyer_id=? AND status!='DRAFT' AND sent_at IS NOT NULL AND archived_at IS NULL", (user["id"],)).fetchone()[0]
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trade_quotes'").fetchone() else 0,
            }
            member = self.membership(db, user["id"])
        return {"counts": counts, "membership": member, "recentInquiries": self.inquiry_rows(user, limit=5),
                "savedVehicles": self.vehicle_list(user, "favorites")[:4], "profileComplete": bool(user["company_name"] and self.profile(user)["country"]),
                "displayName": user["display_name"], "companyName": user["company_name"], "country": self.profile(user)["country"],
                "emailVerified": bool(user["email_verified_at"])}

    def membership_page(self, user):
        with self.auth.connect() as db:
            member = self.membership(db, user["id"])
            bills = [dict(r) for r in db.execute("SELECT p.id,p.amount_minor,p.currency,p.paid_at,p.status,p.transaction_id,m.plan,m.start_at,m.end_at FROM buyer_membership_payments p JOIN buyer_memberships m ON m.id=p.membership_id WHERE p.user_id=? ORDER BY p.paid_at DESC", (user["id"],))]
        return {"membership": member, "billing": bills, "checkoutAvailable": False}
