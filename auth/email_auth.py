"""Email-code and PBKDF2-password identities attached to the existing users table."""

import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid

from mail_templates import language_code
from mail_service import MailUnavailable, send_verification
from business_mail import BusinessMailer


CODE_TTL = 600
CODE_COOLDOWN = 60
PASSWORD_ITERATIONS = 600000
EMAIL_RE = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,63}$", re.UNICODE)


def account_entry_error(account_role, requested_role):
    """An existing identity has one role; a sign-in form cannot change it."""
    if requested_role == 'BUYER' and account_role != 'BUYER':
        return 'This email belongs to a different account role. Use the appropriate sign-in page.'
    if requested_role == 'MERCHANT' and account_role == 'BUYER':
        return 'This email belongs to a buyer account. Use a different email for a supplier account.'
    if requested_role == 'MERCHANT' and account_role not in ('MERCHANT', 'SUPPLIER', 'PLATFORM_ADMIN'):
        return 'This email belongs to a different account role. Use the appropriate sign-in page.'
    return None


class EmailError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def normalized_email(value):
    if not isinstance(value, str):
        raise EmailError(400, "Enter a valid email address.")
    email = value.strip().casefold()
    if len(email) > 320 or not EMAIL_RE.fullmatch(email) or email.startswith('.') or '..' in email:
        raise EmailError(400, "Enter a valid email address.")
    return email


def password_hash(password, salt=None):
    if not isinstance(password, str) or not 8 <= len(password) <= 128:
        raise EmailError(400, "Password must be 8 to 128 characters.")
    salt = salt or secrets.token_bytes(16)
    value = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${value.hex()}"


def verify_password(password, stored):
    try:
        kind, iterations, salt, expected = stored.split('$')
        if kind != 'pbkdf2_sha256' or int(iterations) != PASSWORD_ITERATIONS:
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PASSWORD_ITERATIONS)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError, AttributeError):
        return False


class EmailAuthService:
    def __init__(self, auth, sender=send_verification):
        self.auth = auth
        self.sender = sender
        self.secret = os.environ.get('AUTH_CODE_SECRET', '').encode() or secrets.token_bytes(32)
        auth.code_secret = self.secret
        self.migrate_nullable_google_subject()
        with auth.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS email_identities (
                    email TEXT PRIMARY KEY, user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS email_passwords (
                    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    password_hash TEXT NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS email_verification_codes (
                    id TEXT PRIMARY KEY, email TEXT NOT NULL, code_hash TEXT NOT NULL,
                    purpose TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER,
                    attempt_count INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL,
                    ip_hash TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS email_codes_email_time ON email_verification_codes(email,created_at);
                CREATE INDEX IF NOT EXISTS email_codes_ip_time ON email_verification_codes(ip_hash,created_at);
                CREATE TABLE IF NOT EXISTS email_password_attempts (
                    id TEXT PRIMARY KEY, email_hash TEXT NOT NULL, ip_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS email_password_attempts_email_time ON email_password_attempts(email_hash,created_at);
                CREATE INDEX IF NOT EXISTS email_password_attempts_ip_time ON email_password_attempts(ip_hash,created_at);
            """)
            duplicates = db.execute("SELECT lower(trim(email)),count(*) FROM users GROUP BY lower(trim(email)) HAVING count(*)>1").fetchall()
            if duplicates:
                raise RuntimeError("Duplicate normalized account emails need manual review before email login is enabled.")
            for row in db.execute("SELECT id,email FROM users WHERE email IS NOT NULL ORDER BY created_at"):
                email = row['email'].strip().casefold()
                if EMAIL_RE.fullmatch(email):
                    db.execute("INSERT OR IGNORE INTO email_identities(email,user_id) VALUES (?,?)", (email,row['id']))

    def migrate_nullable_google_subject(self):
        """Current production schema is nullable; never rebuild users at startup."""
        with self.auth.connect() as db:
            cols = {row[1]: row for row in db.execute("PRAGMA table_info(users)")}
            if cols['google_sub'][3]:
                raise RuntimeError("Legacy non-null Google identity schema needs an explicit backed-up migration before email login. No user data was changed.")

    def code_digest(self, code_id, code):
        return hmac.new(self.secret, f'{code_id}:{code}'.encode(), hashlib.sha256).hexdigest()

    def ip_digest(self, ip):
        return hmac.new(self.secret, ip.encode(), hashlib.sha256).hexdigest()

    def send_code(self, email_value, purpose, ip, language='en'):
        try:
            language = language_code(language)
        except ValueError as exc:
            raise EmailError(400, 'Unsupported language.') from exc
        email = normalized_email(email_value)
        if purpose not in ('login','reset_password'):
            raise EmailError(400, "Unsupported code purpose.")
        now = int(time.time())
        ip_hash = self.ip_digest(ip)
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT count(*) FROM email_verification_codes WHERE ip_hash=? AND created_at>?", (ip_hash,now-3600)).fetchone()[0] >= 20:
                raise EmailError(429, "Too many requests. Try again later.")
            rows = db.execute("SELECT created_at FROM email_verification_codes WHERE email=? AND created_at>? ORDER BY created_at DESC", (email,now-3600)).fetchall()
            if rows and rows[0]['created_at'] > now-CODE_COOLDOWN:
                raise EmailError(429, "Please wait before requesting another code.")
            if len(rows) >= 5:
                raise EmailError(429, "Too many requests. Try again later.")
            identity = db.execute("SELECT user_id FROM email_identities WHERE email=?", (email,)).fetchone()
            if purpose == 'reset_password' and not identity:
                return {'retryAfter': CODE_COOLDOWN}
            code_id = uuid.uuid4().hex
            code = f'{secrets.randbelow(1000000):06d}'
            db.execute("UPDATE email_verification_codes SET used_at=? WHERE email=? AND purpose=? AND used_at IS NULL", (now,email,purpose))
            db.execute("INSERT INTO email_verification_codes(id,email,code_hash,purpose,expires_at,created_at,ip_hash) VALUES (?,?,?,?,?,?,?)",
                       (code_id,email,self.code_digest(code_id,code),purpose,now+CODE_TTL,now,ip_hash))
        try:
            if self.sender is send_verification:
                self.sender(email, code, purpose, language)
            else:
                # Preserve the existing three-argument injected transport contract.
                self.sender(email, code, purpose)
        except MailUnavailable as exc:
            with self.auth.connect() as db:
                db.execute("DELETE FROM email_verification_codes WHERE id=?", (code_id,))
            raise EmailError(503, "Email delivery is unavailable. Try again later.") from exc
        return {'retryAfter': CODE_COOLDOWN}

    def consume_code(self, db, email, code, purpose):
        db.execute("BEGIN IMMEDIATE")
        if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):
            raise EmailError(401, "Invalid or expired verification code.")
        now = int(time.time())
        row = db.execute("SELECT * FROM email_verification_codes WHERE email=? AND purpose=? AND used_at IS NULL ORDER BY created_at DESC LIMIT 1", (email,purpose)).fetchone()
        if not row or row['expires_at'] <= now or row['attempt_count'] >= 5:
            raise EmailError(401, "Invalid or expired verification code.")
        db.execute("UPDATE email_verification_codes SET attempt_count=attempt_count+1 WHERE id=?", (row['id'],))
        if not hmac.compare_digest(row['code_hash'],self.code_digest(row['id'],code)):
            # Keep the failed attempt even though an exception is raised.
            db.commit()
            raise EmailError(401, "Invalid or expired verification code.")
        db.execute("UPDATE email_verification_codes SET used_at=? WHERE id=?", (now,row['id']))
        return now

    def register(self, body):
        """Create a verified buyer using the existing one-time email challenge."""
        allowed={'email','code','password','country','consent','language','remember'}
        if set(body)-allowed:
            raise EmailError(400, 'Unsupported registration fields.')
        if body.get('consent') is not True:
            raise EmailError(400, 'Accept the platform terms to create an account.')
        country=body.get('country')
        if not isinstance(country,str) or not 2 <= len(country.strip()) <= 120 or re.search(r'[\x00-\x1f\x7f]',country):
            raise EmailError(400, 'Enter your country or region.')
        password=body.get('password')
        if not isinstance(password,str) or not 8 <= len(password) <= 128:
            raise EmailError(400, 'Password must be 8 to 128 characters.')
        return self.login_code(body,registration={'country':country.strip(),'password':password})

    def login_code(self, body, registration=None):
        try:
            language = language_code(body.get('language', 'en'))
        except ValueError as exc:
            raise EmailError(400, 'Unsupported language.') from exc
        email = normalized_email(body.get('email'))
        requested_role = body.get('role', 'BUYER')
        if requested_role not in ('BUYER', 'MERCHANT'):
            raise EmailError(400, 'Invalid account role.')
        with self.auth.connect() as db:
            now = self.consume_code(db,email,body.get('code'),'login')
            identity = db.execute("SELECT user_id FROM email_identities WHERE email=?", (email,)).fetchone()
            if identity:
                if registration is not None:
                    # An explicit signup must never replace an existing credential
                    # or convert a supplier/admin into a buyer.
                    raise EmailError(409, 'This email already has an account. Sign in or reset your password.')
                user_id = identity['user_id']
                role = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()['role']
                mismatch = account_entry_error(role, requested_role)
                if mismatch:
                    raise EmailError(403, mismatch)
            else:
                if body.get('consent') is not True:
                    raise EmailError(400, "Accept the platform terms to create an account.")
                user_id = uuid.uuid4().hex
                company_name = body.get('companyName', '')
                if not isinstance(company_name, str) or len(company_name.strip()) > 160:
                    raise EmailError(400, 'Invalid company name.')
                company_name = company_name.strip()
                if requested_role == 'MERCHANT' and not company_name:
                    raise EmailError(400, 'Enter your company name to create a supplier account.')
                db.execute("INSERT INTO users(id,google_sub,email,display_name,company_name,role,created_at,last_login_at,email_verified_at) VALUES (?,?,?,?,?,?,?,?,?)",
                           (user_id,None,email,'',company_name,requested_role,now,now,now))
                db.execute("UPDATE users SET preferred_language=? WHERE id=?", (language, user_id))
                db.execute("INSERT INTO email_identities(email,user_id) VALUES (?,?)", (email,user_id))
                db.execute("INSERT INTO consents(user_id,terms_version,privacy_version,accepted_at) VALUES (?,?,?,?)", (user_id,'1.0','1.0',now))
                if registration is not None:
                    # Hash only after a valid code, inside the same transaction as
                    # account creation, consent, country and challenge consumption.
                    db.execute('INSERT INTO email_passwords(user_id,password_hash,updated_at) VALUES (?,?,?)',
                               (user_id,password_hash(registration['password']),now))
                    db.execute('INSERT INTO buyer_profiles(user_id,country,updated_at) VALUES (?,?,?)',
                               (user_id,registration['country'],now))
                BusinessMailer.enqueue(db,user_id,'WELCOME',user_id,'/buyer' if requested_role == 'BUYER' else '/supplier','welcome:'+user_id)
            db.execute("UPDATE users SET last_login_at=?,email_verified_at=COALESCE(email_verified_at,?) WHERE id=?", (now,now,user_id))
            role = db.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()['role']
        return {**self.auth.session_for_user(user_id, bool(body.get('remember'))), 'role':role}

    def login_password(self, body, ip=''):
        email = normalized_email(body.get('email'))
        requested_role = body.get('role', 'BUYER')
        if requested_role not in ('BUYER', 'MERCHANT'):
            raise EmailError(400, 'Invalid account role.')
        password = body.get('password')
        if not isinstance(password,str):
            raise EmailError(401, "Invalid email or password.")
        now = int(time.time())
        email_hash = self.ip_digest('email:'+email)
        ip_hash = self.ip_digest('ip:'+ip)
        with self.auth.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM email_password_attempts WHERE created_at<=?", (now-3600,))
            if db.execute("SELECT count(*) FROM email_password_attempts WHERE email_hash=? AND created_at>?", (email_hash,now-900)).fetchone()[0] >= 10 or db.execute("SELECT count(*) FROM email_password_attempts WHERE ip_hash=? AND created_at>?", (ip_hash,now-900)).fetchone()[0] >= 30:
                raise EmailError(429, "Too many requests. Try again later.")
            db.execute("INSERT INTO email_password_attempts(id,email_hash,ip_hash,created_at) VALUES (?,?,?,?)", (uuid.uuid4().hex,email_hash,ip_hash,now))
            row = db.execute("SELECT i.user_id,p.password_hash,u.role FROM email_identities i JOIN email_passwords p ON p.user_id=i.user_id JOIN users u ON u.id=i.user_id WHERE i.email=?", (email,)).fetchone()
        # The same expensive hash path is used for absent accounts.
        fallback = 'pbkdf2_sha256$600000$00000000000000000000000000000000$' + '00'*32
        valid = verify_password(password,row['password_hash'] if row else fallback)
        if not row or not valid:
            raise EmailError(401, "Invalid email or password.")
        with self.auth.connect() as db:
            db.execute("DELETE FROM email_password_attempts WHERE email_hash=?", (email_hash,))
            mismatch = account_entry_error(row['role'], requested_role)
            if mismatch:
                raise EmailError(403, mismatch)
            db.execute("UPDATE users SET last_login_at=? WHERE id=?", (int(time.time()),row['user_id']))
        return {**self.auth.session_for_user(row['user_id'], bool(body.get('remember'))), 'role':row['role']}

    def set_password(self, token, body):
        user = self.auth.user_for_token(token)
        if not user.get('email_verified_at'):
            raise EmailError(403, 'Verify your email before changing your password.')
        password = password_hash(body.get('password'))
        with self.auth.connect() as db:
            if db.execute("SELECT 1 FROM email_passwords WHERE user_id=?", (user['id'],)).fetchone():
                raise EmailError(409, "Password is already set. Use password reset to change it.")
            db.execute("INSERT INTO email_passwords(user_id,password_hash,updated_at) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET password_hash=excluded.password_hash,updated_at=excluded.updated_at", (user['id'],password,int(time.time())))
        return {'passwordSet':True}

    def change_password(self, token, body, ip=''):
        user = self.auth.user_for_token(token)
        if not user.get('email_verified_at'):
            raise EmailError(403, 'Verify your email before changing your password.')
        current = body.get('currentPassword')
        if not isinstance(current, str) or not 1 <= len(current) <= 128:
            raise EmailError(401, 'Current password is incorrect.')
        now = int(time.time())
        account_hash = self.ip_digest('password-change:'+user['id'])
        ip_hash = self.ip_digest('password-change-ip:'+ip)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM email_password_attempts WHERE created_at<=?', (now-3600,))
            if db.execute('SELECT count(*) FROM email_password_attempts WHERE email_hash=? AND created_at>?', (account_hash,now-900)).fetchone()[0] >= 10 or db.execute('SELECT count(*) FROM email_password_attempts WHERE ip_hash=? AND created_at>?', (ip_hash,now-900)).fetchone()[0] >= 30:
                raise EmailError(429, 'Too many requests. Try again later.')
            db.execute('INSERT INTO email_password_attempts VALUES (?,?,?,?)', (uuid.uuid4().hex,account_hash,ip_hash,now))
            stored = db.execute('SELECT password_hash FROM email_passwords WHERE user_id=?', (user['id'],)).fetchone()
        fallback = 'pbkdf2_sha256$600000$00000000000000000000000000000000$' + '00'*32
        if not verify_password(current, stored['password_hash'] if stored else fallback) or not stored:
            raise EmailError(401, 'Current password is incorrect.')
        replacement = password_hash(body.get('password'))
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Recheck session, account and hash under the write lock: a concurrent
            # logout/reset/suspension must not authorize a later password change.
            live = db.execute('''SELECT 1 FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.user_id=? AND s.expires_at>?
                AND u.status='ACTIVE' AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL''',
                (hashlib.sha256(token.encode('utf-8')).hexdigest(),user['id'],int(time.time()))).fetchone()
            if not live:
                raise EmailError(401, 'Login has expired. Please sign in again.')
            changed = db.execute('UPDATE email_passwords SET password_hash=?,updated_at=? WHERE user_id=? AND password_hash=?',
                                 (replacement,int(time.time()),user['id'],stored['password_hash']))
            if changed.rowcount != 1:
                raise EmailError(409, 'Password was updated. Please sign in again.')
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            db.execute('UPDATE email_verification_codes SET used_at=? WHERE email=? AND used_at IS NULL', (int(time.time()),user['email']))
            db.execute('DELETE FROM email_password_attempts WHERE email_hash=?', (account_hash,))
        return {'passwordChanged':True,'signedOut':True}

    def reset_password(self, body):
        email = normalized_email(body.get('email'))
        value = body.get('password')
        if not isinstance(value,str) or not 8 <= len(value) <= 128:
            raise EmailError(400, 'Password must be 8 to 128 characters.')
        with self.auth.connect() as db:
            self.consume_code(db,email,body.get('code'),'reset_password')
            identity = db.execute("SELECT user_id FROM email_identities WHERE email=?", (email,)).fetchone()
            if not identity:
                raise EmailError(401, "Invalid or expired verification code.")
            password = password_hash(value)
            db.execute("INSERT INTO email_passwords(user_id,password_hash,updated_at) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET password_hash=excluded.password_hash,updated_at=excluded.updated_at", (identity['user_id'],password,int(time.time())))
            db.execute("DELETE FROM sessions WHERE user_id=?", (identity['user_id'],))
            db.execute('UPDATE email_verification_codes SET used_at=? WHERE email=? AND used_at IS NULL',
                       (int(time.time()),email))
        return {'reset':True}

    def has_password(self, user_id):
        with self.auth.connect() as db:
            return bool(db.execute("SELECT 1 FROM email_passwords WHERE user_id=?", (user_id,)).fetchone())
