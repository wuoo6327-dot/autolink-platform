"""Shared notifications, support submissions and membership applications."""
import hashlib
import os
import time
import uuid

from buyer_service import BuyerError, text
from email_auth import normalized_email
from business_mail import BusinessMailer
from pagination import query_list


class PlatformService:
    @staticmethod
    def membership_policy_enabled():
        # Explicit deployment switch permits compatible rollout of the new policy.
        return os.environ.get('MEMBERSHIP_RESTRICTIONS', 'false').lower() == 'true'

    @staticmethod
    def member_in_db(db, user):
        if not user:
            return False
        now = int(time.time())
        return bool(db.execute("""SELECT 1 FROM users u WHERE u.id=? AND u.status='ACTIVE'
            AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL
            AND (u.role='PLATFORM_ADMIN' OR (u.role IN ('BUYER','MERCHANT','SUPPLIER') AND EXISTS
            (SELECT 1 FROM buyer_memberships m WHERE m.user_id=u.id AND m.status='ACTIVE'
             AND m.plan IN ('monthly','quarterly','annual') AND m.start_at<=? AND m.end_at>?)))""",
            (user['id'], now, now)).fetchone())

    def can_view_member_data(self, user):
        if not self.membership_policy_enabled():
            return True
        with self.auth.connect() as db:
            return self.member_in_db(db, user)

    def member_projection(self, value, user, public_supplier=False):
        """Remove restricted values before serialization, including nested history."""
        if self.can_view_member_data(user):
            return value
        def project(v):
            if isinstance(v, list):
                return [project(item) for item in v]
            if not isinstance(v, dict):
                return v
            result={key:project(item) for key,item in v.items()}
            for key in ('price_minor','unit_price_minor','total_price_minor','shipping_cost_minor'):
                if key in result:
                    result[key]=None
                    result['priceLocked']=True
            for key in ('supplierContact','contact'):
                if key in result:
                    result[key]=None
                    result['contactLocked']=True
            if 'message' in result and 'amount_minor' in result:
                result['amount_minor']=None
                result['priceLocked']=True
            if public_supplier and 'company_name' in result:
                result.pop('website',None)
            return result
        return project(value)

    def __init__(self, auth):
        self.auth = auth
        with auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account_notifications (
                    id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
                    event TEXT NOT NULL,entity_id TEXT NOT NULL,url TEXT NOT NULL,
                    created_at INTEGER NOT NULL,read_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS notifications_owner ON account_notifications(user_id,read_at,created_at DESC);
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),email TEXT NOT NULL,
                    type TEXT NOT NULL,subject TEXT NOT NULL,message TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN',ip_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS support_status ON support_tickets(status,created_at DESC);
                CREATE INDEX IF NOT EXISTS support_ip ON support_tickets(ip_hash,created_at);
                CREATE TABLE IF NOT EXISTS membership_applications (
                    id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),plan TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',terms_version TEXT NOT NULL,
                    privacy_version TEXT NOT NULL,membership_version TEXT NOT NULL,
                    refund_version TEXT NOT NULL,language TEXT NOT NULL,accepted_at INTEGER NOT NULL,
                    ticket_id TEXT NOT NULL REFERENCES support_tickets(id)
                );
                CREATE INDEX IF NOT EXISTS membership_application_owner ON membership_applications(user_id,accepted_at DESC);
                CREATE TABLE IF NOT EXISTS listing_reports (
                    id TEXT PRIMARY KEY,reporter_id TEXT NOT NULL REFERENCES users(id),
                    entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,reason TEXT NOT NULL,
                    message TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'OPEN',
                    created_at INTEGER NOT NULL,reviewed_by TEXT REFERENCES users(id),
                    reviewed_at INTEGER,resolution TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS listing_reports_status ON listing_reports(status,created_at DESC);
            """)

    @staticmethod
    def notify(db, user_id, event, entity_id, url):
        notification_id = uuid.uuid4().hex
        db.execute("INSERT INTO account_notifications(id,user_id,event,entity_id,url,created_at) VALUES (?,?,?,?,?,?)",
                   (notification_id,user_id,event,entity_id,url,int(time.time())))
        BusinessMailer.enqueue(db,user_id,event,entity_id,url,'notice:'+notification_id)

    def notifications(self, user, page=None):
        with self.auth.connect() as db:
            return query_list(db, "SELECT id,event,entity_id,url,created_at,read_at FROM account_notifications WHERE user_id=?",
                              (user["id"],), order='created_at DESC,id DESC', page=page, legacy_limit=100)

    def unread_notification_count(self, user):
        with self.auth.connect() as db:
            return db.execute("SELECT count(*) FROM account_notifications WHERE user_id=? AND read_at IS NULL",
                              (user["id"],)).fetchone()[0]

    def mark_notification(self, user, notification_id):
        with self.auth.connect() as db:
            cursor=db.execute("UPDATE account_notifications SET read_at=COALESCE(read_at,?) WHERE id=? AND user_id=?",(int(time.time()),notification_id,user["id"]))
            if cursor.rowcount!=1:
                raise BuyerError(404,"Notification not found.")
        return {"read":True}

    def contact(self, user, body, ip):
        kind=body.get("type")
        if kind not in ("General Support","Membership","Supplier Application","Report Fraud","Business Cooperation"):
            raise BuyerError(400,"Invalid support type.")
        email=normalized_email(user["email"] if user else body.get("email"))
        subject=text(body.get("subject"),"subject",160,True)
        message=text(body.get("message"),"message",4000,True)
        plan=body.get("plan")
        if plan and (not user or user["role"] not in ('BUYER', 'MERCHANT', 'SUPPLIER')):
            raise BuyerError(401,"Sign in with your buyer account to apply for membership.")
        if plan and (plan not in ("monthly","quarterly","annual") or body.get("consent") is not True):
            raise BuyerError(400,"Select a plan and accept the terms before applying.")
        now=int(time.time());ticket_id="SUP-"+uuid.uuid4().hex[:16].upper()
        ip_hash=hashlib.sha256(ip.encode()).hexdigest()
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM support_tickets WHERE ip_hash=? AND created_at>?",(ip_hash,now-3600)).fetchone()[0]>=3:
                raise BuyerError(429,"Support request limit reached. Please try again later.")
            db.execute("INSERT INTO support_tickets(id,user_id,email,type,subject,message,ip_hash,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                       (ticket_id,user["id"] if user else None,email,kind,subject,message,ip_hash,now,now))
            if plan:
                language=body.get("language","en")
                if language not in ("en","zh","ar","ru","kk","uz","ko","fr","sw"):
                    language="en"
                db.execute("INSERT INTO membership_applications(id,user_id,plan,terms_version,privacy_version,membership_version,refund_version,language,accepted_at,ticket_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                           (uuid.uuid4().hex,user["id"],plan,"1.0","1.0","draft-20261006","not-open",language,now,ticket_id))
            for admin in db.execute("SELECT id FROM users WHERE role='PLATFORM_ADMIN' AND status='ACTIVE'"):
                self.notify(db,admin["id"],"SUPPORT_REQUEST",ticket_id,"/admin/support")
        return {"id":ticket_id,"status":"OPEN","paymentAvailable":False}

    def tickets(self, page=None):
        with self.auth.connect() as db:
            return query_list(db, "SELECT id,user_id,email,type,subject,message,status,created_at,updated_at FROM support_tickets",
                              order='created_at DESC,id DESC', page=page, legacy_limit=200)

    def ticket_status(self, admin, ticket_id, body):
        if admin["role"] != "PLATFORM_ADMIN":
            raise BuyerError(403,"Platform admin required.")
        status=body.get("status")
        if status not in ("OPEN","IN_PROGRESS","RESOLVED","CLOSED"):
            raise BuyerError(400,"Invalid support status.")
        with self.auth.connect() as db:
            if db.execute("UPDATE support_tickets SET status=?,updated_at=? WHERE id=?",(status,int(time.time()),ticket_id)).rowcount!=1:
                raise BuyerError(404,"Support request not found.")
            self.audit(db,admin,"SUPPORT_STATUS_CHANGED","support",ticket_id,status)
        return {"id":ticket_id,"status":status}

    def entitlements(self, user):
        with self.auth.connect() as db:
            membership=db.execute("SELECT plan,end_at FROM buyer_memberships WHERE user_id=? AND status='ACTIVE' AND plan IN ('monthly','quarterly','annual') AND start_at<=? AND end_at>? ORDER BY end_at DESC LIMIT 1",(user["id"],int(time.time()),int(time.time()))).fetchone()
        # Membership expiry preserves account history. No payment or automatic grants.
        member = self.can_view_member_data(user)
        return {"membershipActive":bool(membership),"plan":membership["plan"] if membership else None,
                "expiresAt":membership["end_at"] if membership else None,
                "browseVehicles":True,"saveVehicles":True,"saveSuppliers":True,
                "sendInquiries":bool(user["email_verified_at"]),"viewOwnQuotes":True,"checkout":False,
                "viewVehiclePrices":member,"viewSupplierContacts":member,
                "inquiriesPerDay":30 if member else None,"freeInquiryLifetimeLimit":None if member else 1,
                "inquiryLimitPeriod":"rolling24h" if member else "accountLifetime"}

    def report(self, user, body):
        kind=body.get("entityType");entity_id=text(body.get("entityId"),"entity ID",100,True)
        reason=body.get("reason")
        if kind not in ("supplier","vehicle") or reason not in ("Fake Vehicle","Incorrect Price","Fraud","Copyright","Spam","Other"):
            raise BuyerError(400,"Invalid report.")
        message=text(body.get("message"),"message",2000,True);now=int(time.time())
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if not user["email_verified_at"]:
                raise BuyerError(403,"Verify your email before submitting a report.")
            if db.execute("SELECT count(*) FROM listing_reports WHERE reporter_id=? AND created_at>?",(user["id"],now-3600)).fetchone()[0]>=5:
                raise BuyerError(429,"Report limit reached.")
            table,column=("supplier_applications","supplier_id") if kind=="supplier" else ("supplier_vehicles","id")
            if not db.execute(f"SELECT 1 FROM {table} WHERE {column}=?",(entity_id,)).fetchone():
                raise BuyerError(404,"Reported item not found.")
            report_id="REP-"+uuid.uuid4().hex[:16].upper()
            db.execute("INSERT INTO listing_reports(id,reporter_id,entity_type,entity_id,reason,message,created_at) VALUES (?,?,?,?,?,?,?)",(report_id,user["id"],kind,entity_id,reason,message,now))
        return {"id":report_id,"status":"OPEN"}

    def reports(self, page=None):
        with self.auth.connect() as db:
            return query_list(db, "SELECT * FROM listing_reports", order='created_at DESC,id DESC', page=page, legacy_limit=200)

    def review_report(self, admin, report_id, body):
        if admin["role"] != "PLATFORM_ADMIN":
            raise BuyerError(403,"Platform admin required.")
        status=body.get("status");reason=text(body.get("resolution"),"resolution",1000,True)
        if status not in ("OPEN","INVESTIGATING","RESOLVED","REJECTED"):
            raise BuyerError(400,"Invalid report status.")
        with self.auth.connect() as db:
            if db.execute("UPDATE listing_reports SET status=?,reviewed_by=?,reviewed_at=?,resolution=? WHERE id=?",(status,admin["id"],int(time.time()),reason,report_id)).rowcount!=1:
                raise BuyerError(404,"Report not found.")
            self.audit(db,admin,"REPORT_REVIEWED","report",report_id,status+": "+reason)
        return {"id":report_id,"status":status}

    @staticmethod
    def audit(db,admin,action,kind,entity_id,metadata):
        db.execute("INSERT INTO trade_audit(id,actor_user_id,action,entity_type,entity_id,created_at,metadata) VALUES (?,?,?,?,?,?,?)",
                   ("AUD-"+uuid.uuid4().hex.upper(),admin["id"],action,kind,entity_id,int(time.time()),metadata[:1000]))
