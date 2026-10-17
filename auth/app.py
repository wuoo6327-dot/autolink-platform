"""AUTOLINK account API for Google and email authenticated users."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from buyer_service import BuyerError, BuyerService
from pagination import requested_page
from email_auth import EmailAuthService, EmailError, normalized_email, account_entry_error
from trade_service import TradeService, LISTING_STATES
from seo_service import PublicSEOService
from platform_service import PlatformService
from business_mail import BusinessMailer
from mail_templates import language_code
from membership_payments import MembershipPaymentService
from supplier_listing_payments import SupplierListingPayments


CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
DB_PATH = Path(os.environ.get("AUTH_DB_PATH", "/data/autolink-auth.sqlite3"))
PORT = int(os.environ.get("PORT", "8080"))
SESSION_SECONDS = 1800
REMEMBER_SECONDS = 7 * 86400
CHALLENGE_SECONDS = 300
MAX_BODY_BYTES = 16 * 1024


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def default_verifier(credential: str, client_id: str) -> dict:
    from google.auth.transport.requests import Request
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(credential, Request(), client_id)


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class AuthService:
    def __init__(self, db_path: Path, client_id: str, verifier=default_verifier):
        if not client_id:
            raise RuntimeError("GOOGLE_CLIENT_ID must be configured")
        self.db_path = db_path
        self.client_id = client_id
        self.verifier = verifier
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    google_sub TEXT UNIQUE,
                    email TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'MERCHANT',
                    created_at INTEGER NOT NULL,
                    email_verified_at INTEGER
                );
                CREATE TABLE IF NOT EXISTS challenges (
                    nonce_hash TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
                CREATE INDEX IF NOT EXISTS challenges_expiry ON challenges(expires_at);
                CREATE TABLE IF NOT EXISTS consents (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    terms_version TEXT NOT NULL,
                    privacy_version TEXT NOT NULL,
                    accepted_at INTEGER NOT NULL
                );
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
            if "status" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE'")
            if "deleted_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN deleted_at INTEGER")
            if "last_login_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN last_login_at INTEGER")
            if "email_verified_at" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN email_verified_at INTEGER")
            if "preferred_language" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN preferred_language TEXT NOT NULL DEFAULT 'en'")
            if "is_test_workspace" not in columns:
                db.execute("ALTER TABLE users ADD COLUMN is_test_workspace INTEGER NOT NULL DEFAULT 0 CHECK (is_test_workspace IN (0,1))")
        self.mailer = BusinessMailer(self)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def challenge(self):
        nonce = secrets.token_urlsafe(32)
        now = int(time.time())
        with self.connect() as db:
            db.execute("DELETE FROM challenges WHERE expires_at <= ?", (now,))
            db.execute("INSERT INTO challenges(nonce_hash, expires_at) VALUES (?, ?)",
                       (digest(nonce), now + CHALLENGE_SECONDS))
        return {"clientId": self.client_id, "nonce": nonce}

    def verify_credential(self, credential: str, nonce: str):
        if not isinstance(credential, str) or not 100 <= len(credential) <= 10000:
            raise ApiError(400, "Invalid Google credential.")
        if not isinstance(nonce, str) or not 20 <= len(nonce) <= 100:
            raise ApiError(400, "Invalid login challenge.")
        try:
            claims = self.verifier(credential, self.client_id)
        except Exception as exc:
            raise ApiError(401, "Google sign-in could not be verified.") from exc
        if not isinstance(claims, dict):
            raise ApiError(401, "Google sign-in could not be verified.")
        token_nonce = claims.get("nonce")
        if not isinstance(token_nonce, str) or not hmac.compare_digest(token_nonce, nonce):
            raise ApiError(401, "Google sign-in challenge did not match.")
        if not claims.get("sub") or claims.get("email_verified") not in (True, "true"):
            raise ApiError(401, "A verified Google account is required.")
        now = int(time.time())
        with self.connect() as db:
            cursor = db.execute(
                "DELETE FROM challenges WHERE nonce_hash=? AND expires_at>?",
                (digest(nonce), now),
            )
            if cursor.rowcount != 1:
                raise ApiError(401, "Login challenge expired or was already used.")
        return claims

    def google_login(self, body: dict):
        try:
            language = language_code(body.get('language', 'en'))
        except ValueError as exc:
            raise ApiError(400, 'Unsupported language.') from exc
        claims = self.verify_credential(body.get("credential"), body.get("nonce"))
        sub = str(claims["sub"])
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE google_sub=?", (sub,)).fetchone()
            if user is None:
                email = claims.get("email")
                if not isinstance(email, str) or len(email) > 320:
                    raise ApiError(401, "Google account email is unavailable.")
                email = normalized_email(email)
                if db.execute("SELECT 1 FROM email_identities WHERE email=?", (email,)).fetchone():
                    raise ApiError(409, "This email already has an account. Sign in with email code, then link Google from account settings.")
                role = body.get("role", "MERCHANT")
                if role not in ("MERCHANT", "BUYER"):
                    raise ApiError(400, "Invalid account role.")
                company = body.get("companyName")
                if not isinstance(company, str) or body.get("consent") is not True:
                    return {"registrationRequired": True}
                company = company.strip()
                if not (0 if role == "BUYER" else 1) <= len(company) <= 160:
                    raise ApiError(400, "Enter a company name of 1 to 160 characters.")
                user_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO users(id,google_sub,email,display_name,company_name,role,created_at,last_login_at,email_verified_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (user_id, sub, email, str(claims.get("name") or "")[:160], company, role, int(time.time()), int(time.time()), int(time.time())),
                )
                db.execute("UPDATE users SET preferred_language=? WHERE id=?", (language, user_id))
                db.execute(
                    "INSERT INTO consents(user_id,terms_version,privacy_version,accepted_at) VALUES (?,?,?,?)",
                    (user_id, "1.0", "1.0", int(time.time())),
                )
                db.execute("INSERT INTO email_identities(email,user_id) VALUES (?,?)", (email,user_id))
                BusinessMailer.enqueue(db,user_id,'WELCOME',user_id,'/buyer' if role=='BUYER' else '/supplier','welcome:'+user_id)
                user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            else:
                requested_role = body.get('role', 'MERCHANT')
                if requested_role not in ('BUYER', 'MERCHANT'):
                    raise ApiError(400, 'Invalid account role.')
                mismatch = account_entry_error(user['role'], requested_role)
                if mismatch:
                    raise ApiError(403, mismatch)
                db.execute("UPDATE users SET last_login_at=?,email_verified_at=COALESCE(email_verified_at,?) WHERE id=?", (int(time.time()),int(time.time()), user["id"]))
        return {**self.session_for_user(user["id"], bool(body.get("remember"))), "role": user["role"]}

    def session_for_user(self, user_id: str, remember: bool = False):
        token = secrets.token_urlsafe(48)
        now = int(time.time())
        seconds = REMEMBER_SECONDS if remember else SESSION_SECONDS
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            user = db.execute("SELECT status,deleted_at FROM users WHERE id=?", (user_id,)).fetchone()
            if not user or user["status"] != "ACTIVE" or user["deleted_at"] is not None:
                raise ApiError(401, "Account is unavailable. Contact support.")
            db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,?)",
                       (digest(token), user_id, now + seconds))
        return {"access_token": token, "expire_in": seconds}

    def user_for_token(self, token: str):
        if not token or len(token) > 200:
            raise ApiError(401, "Please sign in.")
        with self.connect() as db:
            user = db.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id "
                "WHERE sessions.token_hash=? AND sessions.expires_at>?",
                (digest(token), int(time.time())),
            ).fetchone()
        if user is None or user["status"] != "ACTIVE" or user["deleted_at"] is not None:
            raise ApiError(401, "Login has expired. Please sign in again.")
        return dict(user)

    def save_language(self, token: str, body: dict):
        if set(body) != {'language'}:
            raise ApiError(400, 'Only the language preference can be changed.')
        try:
            language = language_code(body.get('language'))
        except ValueError as exc:
            raise ApiError(400, 'Unsupported language.') from exc
        # Resolve ownership again under the write lock; no target user ID is accepted.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute('''SELECT u.id FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>? AND u.status='ACTIVE' AND u.deleted_at IS NULL''',
                (digest(token), int(time.time()))).fetchone()
            if not user:
                raise ApiError(401, 'Please sign in.')
            db.execute('UPDATE users SET preferred_language=? WHERE id=?', (language, user['id']))
        return {'language': language}

    def logout(self, token: str):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
        return {}

    @staticmethod
    def platform_admin_in_db(db, user):
        """Recheck the configured platform owner against the current account."""
        if not user:
            return False
        row = db.execute("SELECT role,email FROM users WHERE id=? AND status='ACTIVE' AND deleted_at IS NULL",
                         (user['id'],)).fetchone()
        owner_email = os.environ.get('PLATFORM_ADMIN_EMAIL', '').strip().casefold()
        return bool(row and row['role'] == 'PLATFORM_ADMIN' and
                    (not owner_email or row['email'].strip().casefold() == owner_email))

    @staticmethod
    def account_deletion_denial(db, user):
        owner_email = os.environ.get('PLATFORM_ADMIN_EMAIL', '').strip().casefold()
        if owner_email and user['email'].strip().casefold() == owner_email:
            return 'The platform owner cannot delete their account here.'
        if user['role'] == 'PLATFORM_ADMIN' and db.execute(
                "SELECT count(*) FROM users WHERE role='PLATFORM_ADMIN' AND status='ACTIVE' AND deleted_at IS NULL"
                ).fetchone()[0] <= 1:
            return 'The last active platform administrator cannot delete their account.'
        return None

    def account_deletion_allowed(self, user):
        with self.connect() as db:
            current = db.execute("SELECT role,email FROM users WHERE id=? AND status='ACTIVE' AND deleted_at IS NULL",
                                 (user['id'],)).fetchone()
            return bool(current and not self.account_deletion_denial(db, current))

    def delete_account(self, token: str):
        with self.connect() as db:
            # Resolve the session and administrator count under one write lock.
            db.execute('BEGIN IMMEDIATE')
            user = db.execute("""SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>? AND u.status='ACTIVE' AND u.deleted_at IS NULL""",
                (digest(token), int(time.time()))).fetchone()
            if not user:
                raise ApiError(401, 'Please sign in.')
            denial = self.account_deletion_denial(db, user)
            if denial:
                raise ApiError(403, denial)
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("UPDATE users SET status='DELETED',deleted_at=? WHERE id=?", (int(time.time()), user["id"]))
        return {"deleted": True}

    def link(self, body: dict, token: str):
        user = self.user_for_token(token)
        claims = self.verify_credential(body.get("credential"), body.get("nonce"))
        if normalized_email(claims.get("email")) != normalized_email(user["email"]):
            raise ApiError(409, "Google account email does not match this account.")
        if user["google_sub"] and not hmac.compare_digest(str(claims["sub"]), user["google_sub"]):
            raise ApiError(409, "This business account is already linked to a different Google account.")
        with self.connect() as db:
            existing = db.execute("SELECT id FROM users WHERE google_sub=?", (str(claims["sub"]),)).fetchone()
            if existing and existing["id"] != user["id"]:
                raise ApiError(409, "Google account is already linked to another account.")
            db.execute("UPDATE users SET google_sub=? WHERE id=?", (str(claims["sub"]),user["id"]))
        return {"linked": True}


class Handler(BaseHTTPRequestHandler):
    def list_page(self, key='page'):
        return requested_page(parse_qs(urlsplit(self.path).query, keep_blank_values=True), key)

    def list_filter(self, key):
        values = parse_qs(urlsplit(self.path).query, keep_blank_values=True).get(key, [''])
        if len(values) != 1:
            raise BuyerError(400, 'Invalid search filter.')
        return values[0]

    service: AuthService
    buyer: BuyerService
    email_auth: EmailAuthService
    trade: TradeService
    platform: PlatformService
    seo: PublicSEOService
    payments: MembershipPaymentService
    supplier_payments: SupplierListingPayments
    server_version = "AUTOLINKAuth/1.0"

    def payment_service(self):
        instance = getattr(self, "payments", None)
        return instance if instance is not None else MembershipPaymentService(self.service)

    def supplier_payment_service(self):
        instance = getattr(self, "supplier_payments", None)
        return instance if instance is not None else SupplierListingPayments(self.trade)

    def log_message(self, format, *args):
        # Never log bearer tokens or Google credentials.
        print("%s %s" % (self.address_string(), format % args), flush=True)

    def send_json(self, status: int, data=None, message: str = "OK", cookie: str = "", remember: bool = False, clear_cookie: bool = False):
        path=urlsplit(self.path).path
        if status==200 and data is not None and getattr(self,'platform',None) and self.platform.membership_policy_enabled():
            public=path.startswith('/autolink/public/vehicles') or path.startswith('/autolink/public/suppliers')
            buyer=path.startswith('/autolink/buyer/')
            if public or buyer:
                principal=None
                if self.token():
                    try:principal=self.service.user_for_token(self.token())
                    except ApiError:pass
                data=self.platform.member_projection(data,principal,public_supplier=path.startswith('/autolink/public/suppliers'))
        payload = json.dumps({"code": 200 if status == 200 else status,
                              "msg": message, "data": data}, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Robots-Tag", "noindex, nofollow")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            secure = "; Secure" if os.environ.get("COOKIE_SECURE", "true").lower() != "false" else ""
            age = f"; Max-Age={REMEMBER_SECONDS}" if remember else ""
            self.send_header("Set-Cookie", f"autolink_session={cookie}; Path=/; HttpOnly; SameSite=Lax{secure}{age}")
        if clear_cookie:
            self.send_header("Set-Cookie", "autolink_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(payload)

    def send_html(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(data)

    def send_image(self, data):
        self.send_response(200)
        self.send_header("Content-Type","image/jpeg")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Cache-Control","no-store")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(data)

    def send_xml(self, data):
        self.send_response(200)
        self.send_header('Content-Type','application/xml; charset=utf-8')
        # Recheck public eligibility on every request, including after suspension.
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        if self.command != "HEAD": self.wfile.write(data)

    def send_document(self, result):
        filename = "autolink-private-document" + {"application/pdf":".pdf","image/png":".png","image/jpeg":".jpg"}[result["contentType"]]
        self.send_response(200)
        self.send_header("Content-Type", result["contentType"])
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(result["data"])))
        self.end_headers()
        self.wfile.write(result["data"])

    def token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        for part in self.headers.get("Cookie", "").split(";"):
            if part.strip().startswith("autolink_session="):
                return part.strip().split("=", 1)[1]
        return ""

    def check_origin(self):
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ApiError(403, "Cross-site requests are not allowed.")
        origin = self.headers.get("Origin")
        allowed = {"https://autolinkglobal.com"}
        if os.environ.get("COOKIE_SECURE", "true").lower() == "false":
            allowed.update(os.environ.get("DEV_ALLOWED_ORIGINS", "http://127.0.0.1:8776").split(","))
        if origin and origin not in allowed:
            raise ApiError(403, "Request origin is not allowed.")

    def read_body(self, max_bytes=MAX_BODY_BYTES):
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ApiError(415, "JSON request body required.")
        self.check_origin()
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid request length.") from exc
        if size < 0 or size > max_bytes:
            raise ApiError(413, "Request is too large.")
        try:
            body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "Invalid JSON.") from exc
        if not isinstance(body, dict):
            raise ApiError(400, "JSON object required.")
        return body

    def read_payment_webhook(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid webhook length.") from exc
        if size < 1 or size > 65536:
            raise ApiError(413, "Invalid webhook length.")
        return self.rfile.read(size)

    def check_test_workspace(self, method, path):
        # Provisioned test accounts can edit their own drafts; they cannot contact
        # real buyers, join another team, sign an agreement or publish listings.
        if not self.token():
            return
        try:
            user = self.service.user_for_token(self.token())
        except ApiError:
            return  # The endpoint retains its existing authentication behavior.
        if not user.get("is_test_workspace"):
            return
        if path.startswith(("/autolink/supplier/buying-requests", "/autolink/supplier/invitations")):
            raise ApiError(403, "Test workspace: real buyer requests and team invitations are unavailable.")
        if method not in ("POST", "PUT", "DELETE"):
            return
        if path in ("/auth/logout", "/autolink/auth/password/login", "/autolink/auth/google/challenge",
                    "/autolink/auth/google/login", "/autolink/auth/email/login",
                    "/autolink/auth/password/change", "/autolink/auth/preferences",
                    "/autolink/auth/logout-all", "/autolink/buyer/profile"):
            return
        if method in ("POST", "PUT") and re.fullmatch(
                r"/autolink/supplier/vehicles(?:/[^/]+(?:/(?:copy|archive|restore|images(?:/[^/]+/attest)?))?)?", path):
            return
        if method == "POST" and path.startswith("/autolink/notifications/"):
            return
        if method == "PUT" and path == "/autolink/supplier/profile":
            return  # This profile is excluded from every public supplier query.
        raise ApiError(403, "Test workspace: this action is unavailable. You may manage private vehicle drafts.")

    def handle_request(self, method: str):
        path = urlsplit(self.path).path
        if method == "POST" and path == "/autolink/payments/webhooks/stripe":
            self.send_json(200, self.payment_service().webhook(
                "stripe", self.read_payment_webhook(), self.headers))
            return
        if method == "POST" and path == "/autolink/supplier/payments/webhooks/stripe":
            self.send_json(200, self.supplier_payment_service().webhook(
                self.read_payment_webhook(), self.headers))
            return
        self.check_test_workspace(method, path)
        if method in ("POST", "PUT", "DELETE"):
            self.check_origin()
        if path == "/autolink/support" and method == "POST":
            body = self.read_body()
            user = self.service.user_for_token(self.token()) if self.token() else None
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",",1)[0].strip()
            self.send_json(200,self.platform.contact(user,body,ip))
            return
        if path == "/autolink/reports" and method == "POST":
            user = self.service.user_for_token(self.token())
            self.send_json(200,self.platform.report(user,self.read_body()))
            return
        if path == "/autolink/notifications" and method == "GET":
            self.send_json(200,self.platform.notifications(self.service.user_for_token(self.token()), page=self.list_page()))
            return
        if path == "/autolink/notifications/summary" and method == "GET":
            self.send_json(200,self.platform.notification_summary(self.service.user_for_token(self.token())))
            return
        if path.startswith("/autolink/notifications/") and method == "POST":
            user = self.service.user_for_token(self.token())
            self.read_body()
            self.send_json(200,self.platform.mark_notification(user,path.rsplit("/",1)[1]))
            return
        if path.startswith("/autolink/public/"):
            self.handle_public(method, path)
            return
        if path.startswith("/autolink/supplier/"):
            self.handle_supplier(method, path)
            return
        if path.startswith("/autolink/admin/"):
            self.handle_admin(method, path)
            return
        if path.startswith("/autolink/buyer/"):
            self.handle_buyer(method, path)
            return
        if method == "GET" and path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if method == "GET" and path == "/autolink/merchants":
            # Old clients get only the existing reviewed public directory.
            self.send_json(200, [{"id": item["id"], "name": item["company_name"],
                "city": item.get("city"), "country": item.get("country"),
                "introduction": item.get("description"),
                "brands": [part.strip() for part in (item.get("main_brands") or "").split(",") if part.strip()],
                "markets": [part.strip() for part in (item.get("main_markets") or "").split(",") if part.strip()]}
                for item in self.trade.supplier_list(public=True)])
            return
        if method == "GET" and path == "/autolink/auth/social/config":
            # Only Google GSI exists. No OAuth /start route is advertised.
            self.send_json(200, {"google": bool(self.service.client_id)})
            return
        if method == "GET" and path == "/autolink/auth/google/config":
            self.send_json(200, {"enabled": bool(self.service.client_id)})
            return
        if method == "POST" and path == "/autolink/auth/google/challenge":
            self.read_body()
            self.send_json(200, self.service.challenge())
            return
        if method == "POST" and path == "/autolink/auth/google/login":
            body = self.read_body()
            data = self.service.google_login(body)
            self.send_json(200, data, cookie=data.get("access_token", ""), remember=bool(body.get("remember")))
            return
        if method == "POST" and path == "/autolink/auth/google/link":
            self.send_json(200, self.service.link(self.read_body(), self.token()))
            return
        if method == "POST" and path == "/auth/logout":
            self.send_json(200, self.service.logout(self.token()), clear_cookie=True)
            return
        if method == "POST" and path == "/autolink/auth/email/send-code":
            body = self.read_body()
            if body.get("purpose", "login") == "login" and body.get("consent") is not True:
                raise ApiError(400, "Accept the platform terms before requesting a login code.")
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",", 1)[0].strip()
            self.send_json(200, self.email_auth.send_code(body.get("email"), body.get("purpose", "login"), ip, body.get("language", "en")))
            return
        if method == "POST" and path == "/autolink/auth/email/login":
            body = self.read_body()
            data = self.email_auth.login_code(body)
            self.send_json(200, data, cookie=data["access_token"], remember=bool(body.get("remember")))
            return
        if method == "POST" and path == "/autolink/auth/email/register":
            body = self.read_body()
            data = self.email_auth.register(body)
            self.send_json(200, data, cookie=data["access_token"], remember=bool(body.get("remember")))
            return
        if method == "POST" and path == "/autolink/auth/password/login":
            body = self.read_body()
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",", 1)[0].strip()
            data = self.email_auth.login_password(body, ip)
            self.send_json(200, data, cookie=data["access_token"], remember=bool(body.get("remember")))
            return
        if method == "POST" and path == "/autolink/auth/password/set":
            self.send_json(200, self.email_auth.set_password(self.token(), self.read_body()))
            return
        if method == "POST" and path == "/autolink/auth/password/change":
            body = self.read_body()
            ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",", 1)[0].strip()
            self.send_json(200, self.email_auth.change_password(self.token(), body, ip), clear_cookie=True)
            return
        if path == "/autolink/auth/preferences" and method in ("GET", "POST"):
            if method == "GET":
                user = self.service.user_for_token(self.token())
                self.send_json(200, {"language": user["preferred_language"]})
            else:
                self.send_json(200, self.service.save_language(self.token(), self.read_body()))
            return
        if method == "GET" and path == "/autolink/auth/security":
            user = self.service.user_for_token(self.token())
            self.send_json(200, {"email":user["email"], "emailVerified":bool(user.get("email_verified_at")),
                "passwordSet":self.email_auth.has_password(user["id"]), "googleLinked":bool(user["google_sub"]), "lastLoginAt":user.get("last_login_at"), "language":user["preferred_language"]})
            return
        if method == "POST" and path == "/autolink/auth/logout-all":
            self.read_body()
            user = self.service.user_for_token(self.token())
            with self.service.connect() as db:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            self.send_json(200, {"signedOut":True}, clear_cookie=True)
            return
        if method == "POST" and path == "/autolink/auth/password/reset":
            self.send_json(200, self.email_auth.reset_password(self.read_body()))
            return
        if method == "GET" and path == "/auth/code":
            self.send_json(200, {"captchaEnabled": False, "uuid": ""})
            return
        if method == "POST" and path in ("/auth/login", "/autolink/merchant/register"):
            self.read_body()
            raise ApiError(501, "Password accounts are not connected. Please use Google sign-in.")
        if method == "GET" and path in ("/autolink/catalog", "/autolink/countries", "/autolink/stock"):
            self.send_json(200, [])
            return
        if method == "GET" and path == "/autolink/me":
            user = self.service.user_for_token(self.token())
            self.send_json(200, {"id": user["id"], "role": user["role"], "username": user["email"],
                                 "email": user["email"], "nickName": user["display_name"],
                                 "companyName": user["company_name"], "accountDeletionAllowed": self.service.account_deletion_allowed(user), "isTestWorkspace":bool(user.get("is_test_workspace")), "language":user["preferred_language"], "passwordSet": self.email_auth.has_password(user["id"])})
            return
        if method == "DELETE" and path == "/autolink/me":
            self.send_json(200, self.service.delete_account(self.token()), clear_cookie=True)
            return
        if method == "GET" and path in ("/autolink/merchant/stock", "/autolink/requests"):
            if self.service.user_for_token(self.token())["role"] != "MERCHANT":
                raise ApiError(403, "Merchant account required.")
            self.send_json(200, [])
            return
        if method == "GET" and path == "/autolink/merchant/interest":
            if self.service.user_for_token(self.token())["role"] != "MERCHANT":
                raise ApiError(403, "Merchant account required.")
            self.send_json(200, {"notifications": [], "models": []})
            return
        if method == "GET" and path == "/autolink/merchant/overview":
            if self.service.user_for_token(self.token())["role"] != "MERCHANT":
                raise ApiError(403, "Merchant account required.")
            self.send_json(200, {"publishedStocks": 0, "pendingStocks": 0, "draftStocks": 0,
                                 "rejectedStocks": 0, "expiredStocks": 0, "offlineStocks": 0,
                                 "unansweredRequests": 0, "quotedRequests": 0, "totalRequests": 0,
                                 "contacts": 0, "unreadInterest": 0})
            return
        if method == "GET" and path == "/autolink/merchant/application":
            user = self.service.user_for_token(self.token())
            if user["role"] != "MERCHANT":
                raise ApiError(403, "Merchant account required.")
            self.send_json(200, {"id": user["id"], "version": 1, "status": "DRAFT",
                                 "company_name": user["company_name"], "registration_no": "",
                                 "address": "", "contact_name": user["display_name"],
                                 "contact_email": user["email"], "contact_phone": "",
                                 "introduction": "", "documents": [], "history": []})
            return
        if path.startswith("/autolink/") or path.startswith("/auth/"):
            raise ApiError(501, "This business feature is not connected yet.")
        raise ApiError(404, "Not found.")

    def handle_buyer(self, method: str, path: str):
        user = self.buyer.require(self.token())
        base = "/autolink/buyer/"
        tail = path[len(base):]
        if method == "GET" and tail == "overview":
            data = self.buyer.overview(user)
            data["savedListings"] = self.trade.saved_listings(user)[:4]
            data["recentQuotes"] = self.trade.quote_rows(user)[:5]
            data["unreadNotifications"] = self.platform.unread_notification_count(user)
        elif method == "GET" and tail == "profile":
            data = self.buyer.profile(user)
        elif method == "PUT" and tail == "profile":
            data = self.buyer.update_profile(user, self.read_body())
        elif method == "GET" and tail in ("favorites", "compare"):
            data = self.buyer.vehicle_list(user, tail)
        elif method == "POST" and tail in ("favorites", "compare"):
            data = self.buyer.add_vehicle(user, tail, self.read_body().get("vehicleId"))
        elif method == "DELETE" and (tail.startswith("favorites/") or tail.startswith("compare/")):
            kind, vehicle_id = tail.split("/", 1)
            data = self.buyer.remove_vehicle(user, kind, vehicle_id)
        elif method == "GET" and tail == "suppliers":
            data = self.buyer.suppliers(user)
        elif method == "GET" and tail == "saved-suppliers":
            data = self.buyer.suppliers(user, saved=True)
        elif method == "POST" and tail == "saved-suppliers":
            data = self.buyer.save_supplier(user, self.read_body().get("supplierId"))
        elif method == "DELETE" and tail.startswith("saved-suppliers/"):
            data = self.buyer.save_supplier(user, tail.split("/", 1)[1], add=False)
        elif method == "GET" and tail == "inquiries":
            data = self.buyer.inquiry_rows(user, page=self.list_page(),
                                          status=self.list_filter('status'), keyword=self.list_filter('keyword'))
        elif method == "POST" and tail == "inquiries":
            body = self.read_body()
            data = self.trade.create_inquiry(user, body)
        elif method == "GET" and tail.startswith("inquiries/"):
            rows = self.buyer.inquiry_rows(user, tail.split("/", 1)[1])
            if not rows:
                raise BuyerError(404, "Inquiry was not found.")
            data = rows[0]
            data["supplierContact"] = self.trade.buyer_supplier_contact(user, data["id"])
        elif method == "GET" and tail == "requests":
            data = self.buyer.requests(user, page=self.list_page())
        elif method == "POST" and tail == "requests":
            data = self.buyer.create_request(user, self.read_body())
        elif method == "PUT" and tail.startswith("requests/"):
            data = self.buyer.update_request_status(user,tail.split("/",1)[1],self.read_body())
        elif method == "GET" and tail == "messages":
            data = self.buyer.messages(user)
        elif method == "GET" and tail == "quotes":
            data = self.trade.quote_rows(user, page=self.list_page())
        elif method == "GET" and tail == "saved-listings":
            data = self.trade.saved_listings(user)
        elif method == "POST" and tail == "saved-listings":
            data = self.trade.save_listing(user, self.read_body().get("listingId"))
        elif method == "DELETE" and tail.startswith("saved-listings/"):
            data = self.trade.save_listing(user, tail.split("/",1)[1], add=False)
        elif method == "GET" and tail.startswith("quotes/"):
            data = self.trade.buyer_quote(user, tail.split("/",1)[1])
        elif method == "POST" and tail.startswith("quotes/") and tail.endswith("/response"):
            quote_id = tail.split("/")[1]
            data = self.trade.buyer_quote(user, quote_id, self.read_body().get("decision"))
        elif method == "GET" and tail == "history":
            data = self.trade.recent_views(user)
        elif method == "POST" and tail == "history":
            data = self.trade.record_view(user, self.read_body().get("listingId"))
        elif method == "POST" and tail.startswith("messages/") and tail.endswith("/read"):
            self.read_body()
            data = self.buyer.mark_read(user, tail.split("/")[1])
        elif method == "GET" and tail == "membership":
            data = self.buyer.membership_page(user)
            data["pricing"] = self.payment_service().pricing(user)
            data["orders"] = self.payment_service().orders(user)
            data["checkoutAvailable"] = data["pricing"]["methods"]["stripe_card"]["available"]
        elif method == "POST" and tail == "membership/checkout":
            data = self.payment_service().create_checkout(user, self.read_body())
        elif method == "GET" and tail == "entitlements":
            data = self.platform.entitlements(user)
        elif method == "GET" and tail == "security":
            data = {"email": user["email"], "googleLinked": bool(user["google_sub"]), "passwordSet": self.email_auth.has_password(user["id"]),
                    "emailVerified": bool(user.get("email_verified_at")), "lastLoginAt": user.get("last_login_at"), "recentDevices": [], "language": user["preferred_language"]}
        elif method == "POST" and tail == "logout-all":
            self.read_body()
            with self.service.connect() as db:
                db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            data = {"signedOut": True}
        else:
            raise BuyerError(404, "Buyer feature was not found.")
        self.send_json(200, data)

    def handle_public(self, method: str, path: str):
        tail = path[len("/autolink/public/"):]
        if method != "GET":
            raise ApiError(405, "Method not allowed.")
        if tail == 'seo/trade' or tail.startswith('seo/trade/'):
            renderer = getattr(self, 'seo', None) or PublicSEOService(self.trade)
            status, body = renderer.render(self.path[len('/autolink/public/seo'):])
            self.send_html(status, body)
            return
        if tail=='sitemap.xml' or tail.startswith('sitemaps/'):
            self.send_xml(self.trade.sitemap_xml('sitemap.xml' if tail=='sitemap.xml' else tail[len('sitemaps/'):]))
            return
        if tail.startswith("vehicle-images/"):
            user = None
            if self.token():
                try: user = self.service.user_for_token(self.token())
                except ApiError: pass
            self.send_image(self.trade.images.bytes(tail.split("/",1)[1],user))
            return
        if tail == "models":
            data = self.trade.catalog.models(brand=parse_qs(urlsplit(self.path).query).get("brandId", [None])[0])
            renderer = getattr(self, 'seo', None) or PublicSEOService(self.trade)
            data = [{**model,'seo':renderer.index_policy('model',model)} for model in data]
        elif tail.startswith("models/"):
            ident = tail.split("/", 1)[1]
            if not self.trade.catalog.enabled(ident):
                raise ApiError(404, "Model not found.")
            data = self.trade.catalog.get(ident)
            renderer = getattr(self, 'seo', None) or PublicSEOService(self.trade)
            data = {**data,'seo':renderer.index_policy('model',data)}
        elif tail == "brands":
            data = self.trade.catalog.brands()
            renderer = getattr(self, 'seo', None) or PublicSEOService(self.trade)
            data = [{**brand,'seo':renderer.index_policy('brand',{**brand,'models':self.trade.catalog.models(brand=brand['id'])})} for brand in data]
        elif tail.startswith("brands/"):
            data = self.trade.catalog.brand(tail.split("/", 1)[1])
            renderer = getattr(self, 'seo', None) or PublicSEOService(self.trade)
            data = {**data,'seo':renderer.index_policy('brand',data)}
        elif tail == "vehicles":
            query = parse_qs(urlsplit(self.path).query)
            principal=None
            if self.token():
                try:principal=self.service.user_for_token(self.token())
                except ApiError:pass
            if not self.platform.can_view_member_data(principal) and (
                    'minPriceMinor' in query or 'maxPriceMinor' in query or
                    query.get('sort',[None])[0] in ('price_asc','price_desc')):
                raise ApiError(403, 'Membership is required to view prices and contacts.')
            try:
                limit = min(50, max(1, int(query.get("limit", [25])[0])))
                offset = max(0, int(query.get("offset", [0])[0]))
            except (TypeError, ValueError) as exc:
                raise ApiError(400, "Invalid pagination.") from exc
            if offset > 100000:
                raise ApiError(400, "Invalid search filter.")
            filters = {key: query.get(key, [None])[0] for key in
                       ("keyword","brand","model","vehicleType","energyType","condition","steering","incoterm","sort",
                        "year","minStock","minPriceMinor","maxPriceMinor")}
            supplier_id = query.get("supplierId", [None])[0]
            if supplier_id and len(supplier_id) > 100:
                raise ApiError(400, "Invalid supplier filter.")
            data = self.trade.vehicle_rows(public=True, supplier_id=supplier_id, limit=limit, offset=offset, filters=filters)
        elif tail.startswith("vehicles/"):
            data = self.trade.vehicle(tail.split("/", 1)[1], public=True)
        elif tail == "suppliers":
            data = self.trade.supplier_list()
        elif tail.startswith("suppliers/"):
            data = self.trade.public_supplier(tail.split("/", 1)[1])
            if not data:
                raise ApiError(404, "Supplier not found.")
        else:
            raise ApiError(404, "Not found.")
        self.send_json(200, data)

    def handle_supplier(self, method: str, path: str):
        tail = path[len("/autolink/supplier/"):]
        if tail == "contexts" and method == "GET":
            self.send_json(200,self.trade.team.contexts(self.service.user_for_token(self.token())))
            return
        if tail == "invitations" and method == "GET":
            self.send_json(200,self.trade.team.invitations(self.service.user_for_token(self.token())))
            return
        if tail.startswith("invitations/") and tail.endswith("/accept") and method == "POST":
            self.read_body()
            self.send_json(200,self.trade.team.accept(self.service.user_for_token(self.token()),tail.split("/")[1]))
            return
        user = self.trade.require_supplier(self.token(),
            approved=not (tail in ("application", "agreement", "documents") or tail.startswith("documents/")),
            supplier_id=self.headers.get("X-Autolink-Supplier"))
        if user["supplier_role"] == "SALES":
            allowed = (method=="GET" and tail in ("overview","vehicles","members","inquiries","quotes","buyers") or
                method=="GET" and tail.startswith(("inquiries/","buyers/","quotes/")) or
                method in ("PUT","POST") and tail.startswith(("inquiries/","quotes/","buyers/")))
            if not allowed or tail.endswith("/assignment"):
                raise ApiError(403,"This operation is restricted to the company owner.")
        if method == "GET" and tail == "overview":
            data = self.trade.supplier_overview(user)
        elif method == "GET" and tail == "application":
            data = self.trade.application(user)
        elif method == "PUT" and tail == "application":
            data = self.trade.save_application(user, self.read_body())
        elif method == "GET" and tail == "agreement":
            data = self.trade.agreement.current(user)
        elif method == "POST" and tail == "agreement":
            data = self.trade.agreement.confirm(user, self.read_body())
        elif method == "GET" and tail == "profile":
            data = self.trade.supplier_profile(user)
        elif method == "PUT" and tail == "profile":
            data = self.trade.save_supplier_profile(user, self.read_body())
        elif method == "GET" and tail == "brand-authorizations":
            data = self.trade.brand_authorizations.rows(user["id"])
        elif method == "POST" and tail == "brand-authorizations":
            data = self.trade.brand_authorizations.submit(user, self.read_body())
        elif method == "GET" and tail == "documents":
            data = self.trade.documents(user["id"])
        elif method == "POST" and tail == "documents":
            data = self.trade.add_document(user, self.read_body(7_200_000))
        elif method == "GET" and tail.startswith("documents/"):
            self.send_document(self.trade.document_bytes(tail.split("/",1)[1],user))
            return
        elif method == "GET" and tail == "vehicles":
            status=parse_qs(urlsplit(self.path).query).get("status", [None])[0]
            if status is not None and status not in LISTING_STATES:
                raise ApiError(400, "Invalid vehicle status.")
            data = self.trade.vehicle_rows(supplier_id=user["id"],public=user["supplier_role"]=="SALES",status=status,limit=200,page=self.list_page())
        elif method == "POST" and tail == "vehicles":
            data = self.trade.save_vehicle(user, self.read_body())
        elif method == "GET" and tail == "listing-payments":
            with self.service.connect() as db:
                rows = db.execute(
                    "SELECT id,listing_id,model_id,model_year,quarter_number,amount_minor,currency,"
                    "status,created_at,paid_at,service_until,refund_status,dispute_status "
                    "FROM supplier_listing_orders WHERE supplier_id=? ORDER BY created_at DESC LIMIT 50",
                    (user["id"],)
                ).fetchall()
            data = [dict(row) for row in rows]
        elif tail.startswith("vehicles/"):
            parts = tail.split("/")
            listing_id = parts[1]
            if method == "GET" and len(parts) == 2:
                data = self.trade.vehicle(listing_id, supplier_id=user["id"], include_archived=True)
            elif method == "PUT" and len(parts) == 2:
                data = self.trade.save_vehicle(user, self.read_body(), listing_id)
            elif len(parts) == 3 and parts[2] == "images" and method == "GET":
                self.trade.vehicle(listing_id,supplier_id=user["id"])
                data = self.trade.images.list(listing_id)
            elif len(parts) == 3 and parts[2] == "images" and method == "POST":
                data = self.trade.images.add(user,listing_id,self.read_body(8_000_000))
                with self.service.connect() as db:
                    self.trade.audit(db,user["id"],"VEHICLE_IMAGE_ADDED","vehicle",listing_id,user["id"])
            elif method == "POST" and len(parts) == 5 and parts[2] == "images" and parts[4] == "attest":
                data = self.trade.images.attest(user, listing_id, parts[3], self.read_body())
            elif method == "POST" and len(parts) == 3 and parts[2] == "copy":
                self.read_body()
                data = self.trade.copy_vehicle(user, listing_id)
            elif method == "GET" and len(parts) == 3 and parts[2] == "listing-quote":
                data = self.supplier_payment_service().quote(user, listing_id)
            elif method == "POST" and len(parts) == 3 and parts[2] == "listing-checkout":
                data = self.supplier_payment_service().create_checkout(user, listing_id, self.read_body())
            elif method == "POST" and len(parts) == 3:
                self.read_body()
                data = self.trade.transition_vehicle(user, listing_id, parts[2])
            else:
                raise ApiError(404, "Not found.")
        elif method == "GET" and tail == "inquiries":
            data = self.trade.supplier_inquiries(user, page=self.list_page())
        elif method == "GET" and tail == "buying-requests":
            data = self.trade.buying_requests(user, page=self.list_page())
        elif tail.startswith("buying-requests/"):
            parts=tail.split("/")
            if method=="GET" and len(parts)==2:
                rows=self.trade.buying_requests(user,parts[1])
                if not rows:raise ApiError(404,"Buying request not found.")
                data=rows[0]
            elif method=="POST" and len(parts)==3 and parts[2]=="respond":
                data=self.trade.respond_to_request(user,parts[1],self.read_body())
            else:raise ApiError(404,"Buying request endpoint not found.")
        elif tail.startswith("inquiries/"):
            parts = tail.split("/")
            inquiry_id = parts[1]
            if method == "GET" and len(parts) == 2:
                rows = self.trade.supplier_inquiries(user, inquiry_id)
                if not rows:
                    raise ApiError(404, "Inquiry not found.")
                data = rows[0]
            elif method == "PUT" and len(parts) == 2:
                data = self.trade.update_inquiry(user, inquiry_id, self.read_body())
            elif method == "POST" and len(parts) == 3 and parts[2] == "quotes":
                data = self.trade.create_quote(user, inquiry_id, self.read_body())
            else:
                raise ApiError(404, "Not found.")
        elif method == "GET" and tail == "quotes":
            data = self.trade.quote_rows(user, supplier=True, page=self.list_page())
        elif method == "GET" and tail.startswith("quotes/") and len(tail.split("/"))==2:
            data = self.trade.supplier_quote(user, tail.split("/")[1])
        elif method == "POST" and tail.startswith("quotes/") and tail.endswith("/send"):
            self.read_body()
            data = self.trade.send_quote(user, tail.split("/")[1])
        elif method == "GET" and tail == "buyers":
            data = self.trade.crm(user, page=self.list_page())
        elif method == "GET" and tail == "members":
            data = self.trade.team.members(user)
        elif method == "GET" and tail == "team":
            data = self.trade.team.team(user)
        elif method == "POST" and tail == "team/invitations":
            data = self.trade.team.invite(user,self.read_body())
        elif method == "POST" and tail.startswith("team/invitations/") and tail.endswith("/cancel"):
            self.read_body()
            data = self.trade.team.cancel(user,tail.split("/")[2])
        elif method == "DELETE" and tail.startswith("team/members/"):
            self.read_body()
            data = self.trade.team.remove(user,tail.split("/")[2])
        elif method == "PUT" and tail.startswith("buyers/") and tail.endswith("/assignment"):
            data = self.trade.team.assign(user,tail.split("/")[1],self.read_body())
        elif method == "POST" and tail.startswith("quotes/") and tail.endswith("/cancel"):
            self.read_body()
            data = self.trade.cancel_quote(user, tail.split("/")[1])
        elif method == "GET" and tail.startswith("buyers/"):
            data = self.trade.crm_detail(user, tail.split("/")[1], pages={
                key:self.list_page(key) for key in ('notesPage','inquiriesPage','quotesPage')})
        elif method == "PUT" and tail.startswith("buyers/"):
            data = self.trade.update_crm(user, tail.split("/")[1], self.read_body())
        else:
            raise ApiError(404, "Supplier feature not found.")
        self.send_json(200, data)

    def handle_admin(self, method: str, path: str):
        user = self.trade.require_admin(self.token())
        tail = path[len("/autolink/admin/"):]
        if method == "GET" and tail == "overview":
            data = self.trade.admin_overview()
        elif method == "GET" and tail == "sourcing":
            kind=parse_qs(urlsplit(self.path).query).get('kind',['requests'])[0]
            data=self.trade.admin_sourcing(user,kind,page=self.list_page())
        elif method == "POST" and re.fullmatch(r"sourcing/(requests|inquiries)/[^/]+/followup",tail):
            _,kind,entity_id,_=tail.split('/')
            data=self.trade.admin_sourcing_followup(user,kind,entity_id,self.read_body())
        elif method == "GET" and tail == "seo/status":
            data = (getattr(self, 'seo', None) or PublicSEOService(self.trade)).admin_status()
        elif method == "GET" and tail == "email":
            data = self.service.mailer.status()
        elif method == "GET" and tail == "brands":
            data = self.trade.catalog.brands(public=False)
        elif method == "GET" and tail == "models":
            data = self.trade.catalog.models(public=False)
        elif method == "POST" and tail == "brands":
            data = self.trade.catalog.save_brand(user, self.read_body())
        elif method == "PUT" and tail.startswith("brands/"):
            data = self.trade.catalog.save_brand(user, self.read_body(), tail.split("/", 1)[1])
        elif method == "POST" and tail == "models":
            data = self.trade.catalog.save_model(user, self.read_body())
        elif method == "PUT" and tail.startswith("models/"):
            data = self.trade.catalog.save_model(user, self.read_body(), tail.split("/", 1)[1])
        elif method == "GET" and tail == "users":
            data = self.trade.admin_users(parse_qs(urlsplit(self.path).query).get("keyword", [""])[0], page=self.list_page())
        elif method == "GET" and re.fullmatch(r"users/[^/]+", tail):
            data = self.trade.admin_user_detail(user, tail.split("/", 1)[1])
        elif method == "POST" and tail.startswith("users/") and tail.endswith("/status"):
            data = self.trade.user_status(user, tail.split("/")[1], self.read_body())
        elif method == "POST" and re.fullmatch(r"users/[^/]+/clear-supplier-access", tail):
            data = self.trade.clear_supplier_access(user, tail.split('/')[1], self.read_body())
        elif method == "POST" and re.fullmatch(r"users/[^/]+/erase-personal-data", tail):
            data = self.trade.erase_user_personal_data(user, tail.split('/')[1], self.read_body())
        elif method == "GET" and tail == "support":
            data = self.platform.tickets(page=self.list_page())
        elif method == "POST" and tail.startswith("support/"):
            data = self.platform.ticket_status(user,tail.split("/")[1],self.read_body())
        elif method == "GET" and tail == "reports":
            data = self.platform.reports(page=self.list_page())
        elif method == "POST" and tail.startswith("reports/"):
            data = self.platform.review_report(user,tail.split("/")[1],self.read_body())
        elif method == "GET" and tail == "audit":
            data = self.trade.audit_rows(page=self.list_page())
        elif method == "GET" and tail == "suppliers":
            status = parse_qs(urlsplit(self.path).query).get("status", [None])[0]
            data = self.trade.supplier_list(public=False, status=status, page=self.list_page())
        elif method == "GET" and tail.startswith("suppliers/") and len(tail.split('/'))==2:
            rows = self.trade.supplier_list(public=False, supplier_id=tail.split('/')[1])
            if not rows:
                raise ApiError(404, 'Supplier application not found.')
            data = rows[0]
            with self.service.connect() as db:
                data['agreementConfirmation'] = self.trade.agreement.matching(db,data['supplier_id'],data['company_name'],data['registration_no'],data['address'])
        elif method == "GET" and tail.startswith("suppliers/") and tail.endswith("/documents"):
            data = self.trade.documents(tail.split("/")[1])
        elif method == "GET" and re.fullmatch(r"suppliers/[^/]+/brand-authorizations", tail):
            data = self.trade.brand_authorizations.rows(tail.split('/')[1])
        elif method == "POST" and re.fullmatch(r"brand-authorizations/[^/]+/review", tail):
            data = self.trade.brand_authorizations.review(user, tail.split('/')[1], self.read_body())
        elif method == "GET" and tail.startswith("documents/"):
            self.send_document(self.trade.document_bytes(tail.split("/",1)[1],user))
            return
        elif method == "POST" and tail.startswith("suppliers/") and tail.endswith("/review"):
            data = self.trade.review_supplier(user, tail.split("/")[1], self.read_body())
        elif method == "GET" and tail == "vehicles":
            status = parse_qs(urlsplit(self.path).query).get("status", [None])[0]
            data = self.trade.vehicle_rows(status=status, limit=200, page=self.list_page())
        elif method == "GET" and tail.startswith("vehicles/") and len(tail.split('/'))==2:
            data = self.trade.vehicle(tail.split('/')[1], include_archived=True)
            data['stockPhotos'] = self.trade.images.list(tail.split('/')[1])
        elif re.fullmatch(r"vehicles/[^/]+/price-reviews", tail) and method in ("GET", "POST"):
            listing_id = tail.split("/")[1]
            data = self.trade.price_reviews.history(user, listing_id) if method == "GET" else self.trade.price_reviews.record(user, listing_id, self.read_body())
        elif method == "POST" and tail.startswith("vehicles/") and tail.endswith("/review"):
            data = self.trade.review_vehicle(user, tail.split("/")[1], self.read_body())
        else:
            raise ApiError(404, "Admin feature not found.")
        self.send_json(200, data)

    def do_GET(self):
        self.dispatch("GET")

    def do_HEAD(self):
        # Do not dispatch private business GET handlers: some legacy reads write.
        path = urlsplit(self.path).path
        if path == '/healthz' or path.startswith('/autolink/public/'):
            self.dispatch('GET')
        else:
            self.send_json(405, None, 'HEAD is only available for public resources.')

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def dispatch(self, method):
        try:
            self.handle_request(method)
        except ApiError as exc:
            self.send_json(exc.status, None, exc.message)
        except BuyerError as exc:
            self.send_json(exc.status, None, exc.message)
        except EmailError as exc:
            self.send_json(exc.status, None, exc.message)
        except Exception:
            self.send_json(500, None, "Server error.")


def main():
    Handler.service = AuthService(DB_PATH, CLIENT_ID)
    Handler.email_auth = EmailAuthService(Handler.service)
    Handler.buyer = BuyerService(Handler.service)
    Handler.trade = TradeService(Handler.service)
    Handler.platform = Handler.trade.platform
    Handler.seo = PublicSEOService(Handler.trade)
    Handler.payments = MembershipPaymentService(Handler.service)
    Handler.supplier_payments = SupplierListingPayments(Handler.trade)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    Handler.service.mailer.start()
    try:server.serve_forever()
    finally:Handler.service.mailer.stop_event.set()


if __name__ == "__main__":
    main()
