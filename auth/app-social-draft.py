"""Small social-identity account API for the AUTOLINK static frontend."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import social


CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
DB_PATH = Path(os.environ.get("AUTH_DB_PATH", "/data/autolink-auth.sqlite3"))
PORT = int(os.environ.get("PORT", "8080"))
SESSION_SECONDS = 1800
CHALLENGE_SECONDS = 300
OAUTH_SECONDS = 300
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
                    google_sub TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'MERCHANT',
                    created_at INTEGER NOT NULL
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
                CREATE TABLE IF NOT EXISTS identities (
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    user_id TEXT NOT NULL REFERENCES users(id),
                    PRIMARY KEY(provider, subject)
                );
                CREATE INDEX IF NOT EXISTS identities_user ON identities(user_id);
                CREATE TABLE IF NOT EXISTS oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_tickets (
                    ticket_hash TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    email TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS oauth_states_expiry ON oauth_states(expires_at);
                CREATE INDEX IF NOT EXISTS oauth_tickets_expiry ON oauth_tickets(expires_at);
                """
            )
            db.execute("INSERT OR IGNORE INTO identities(provider,subject,user_id) "
                       "SELECT 'google',google_sub,id FROM users WHERE google_sub NOT LIKE 'unlinked:%'")

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
        claims = self.verify_credential(body.get("credential"), body.get("nonce"))
        sub = str(claims["sub"])
        with self.connect() as db:
            user = db.execute("SELECT * FROM users WHERE google_sub=?", (sub,)).fetchone()
            if user is None:
                company = body.get("companyName")
                if not isinstance(company, str) or not body.get("consent"):
                    return {"registrationRequired": True}
                company = company.strip()
                if not 1 <= len(company) <= 160:
                    raise ApiError(400, "Enter a company name of 1 to 160 characters.")
                email = claims.get("email")
                if not isinstance(email, str) or len(email) > 320:
                    raise ApiError(401, "Google account email is unavailable.")
                user_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO users(id,google_sub,email,display_name,company_name,created_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (user_id, sub, email, str(claims.get("name") or "")[:160], company, int(time.time())),
                )
                db.execute("INSERT INTO identities(provider,subject,user_id) VALUES ('google',?,?)",
                           (sub, user_id))
                user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            token = secrets.token_urlsafe(48)
            now = int(time.time())
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
            db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,?)",
                       (digest(token), user["id"], now + SESSION_SECONDS))
        return {"access_token": token, "expire_in": SESSION_SECONDS}

    def oauth_start(self, provider: str):
        if not social.enabled(provider):
            raise ApiError(503, "This sign-in provider is not available yet.")
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = int(time.time())
        with self.connect() as db:
            db.execute("DELETE FROM oauth_states WHERE expires_at<=?", (now,))
            db.execute("INSERT INTO oauth_states(state_hash,provider,nonce,expires_at) VALUES (?,?,?,?)",
                       (digest(state), provider, nonce, now + OAUTH_SECONDS))
        return social.authorization_url(provider, state, nonce)

    def oauth_callback(self, provider: str, state: str, code: str):
        if not 20 <= len(state) <= 200 or not 1 <= len(code) <= 4096:
            raise ApiError(400, "Invalid sign-in response.")
        now = int(time.time())
        with self.connect() as db:
            row = db.execute("SELECT nonce FROM oauth_states WHERE state_hash=? AND provider=? AND expires_at>?",
                             (digest(state), provider, now)).fetchone()
            if row is None:
                raise ApiError(401, "Sign-in challenge expired or was already used.")
            db.execute("DELETE FROM oauth_states WHERE state_hash=?", (digest(state),))
        try:
            identity = social.exchange(provider, code, row["nonce"])
        except social.ProviderError as exc:
            raise ApiError(401, str(exc)) from exc
        ticket = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("DELETE FROM oauth_tickets WHERE expires_at<=?", (now,))
            db.execute("INSERT INTO oauth_tickets(ticket_hash,provider,subject,email,display_name,expires_at) "
                       "VALUES (?,?,?,?,?,?)",
                       (digest(ticket), provider, identity["subject"], identity["email"],
                        identity["name"], now + OAUTH_SECONDS))
        return ticket

    def oauth_finish(self, body: dict):
        ticket = body.get("ticket")
        if not isinstance(ticket, str) or not 20 <= len(ticket) <= 200:
            raise ApiError(400, "Invalid sign-in ticket.")
        now = int(time.time())
        with self.connect() as db:
            row = db.execute("SELECT * FROM oauth_tickets WHERE ticket_hash=? AND expires_at>?",
                             (digest(ticket), now)).fetchone()
            if row is None:
                raise ApiError(401, "Sign-in ticket expired or was already used.")
            user = db.execute("SELECT users.* FROM identities JOIN users ON users.id=identities.user_id "
                              "WHERE identities.provider=? AND identities.subject=?",
                              (row["provider"], row["subject"])).fetchone()
            if user is None:
                company = body.get("companyName")
                if not isinstance(company, str) or not body.get("consent"):
                    return {"registrationRequired": True}
                company = company.strip()
                if not 1 <= len(company) <= 160:
                    raise ApiError(400, "Enter a company name of 1 to 160 characters.")
                user_id = str(uuid.uuid4())
                db.execute("INSERT INTO users(id,google_sub,email,display_name,company_name,created_at) "
                           "VALUES (?,?,?,?,?,?)",
                           (user_id, "unlinked:" + user_id, row["email"], row["display_name"],
                            company, now))
                db.execute("INSERT INTO identities(provider,subject,user_id) VALUES (?,?,?)",
                           (row["provider"], row["subject"], user_id))
                user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            db.execute("DELETE FROM oauth_tickets WHERE ticket_hash=?", (digest(ticket),))
            token = secrets.token_urlsafe(48)
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (?,?,?)",
                       (digest(token), user["id"], now + SESSION_SECONDS))
        return {"access_token": token, "expire_in": SESSION_SECONDS}

    def user_for_token(self, token: str):
        if not token or len(token) > 200:
            raise ApiError(401, "Please sign in with Google.")
        with self.connect() as db:
            user = db.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id "
                "WHERE sessions.token_hash=? AND sessions.expires_at>?",
                (digest(token), int(time.time())),
            ).fetchone()
        if user is None:
            raise ApiError(401, "Login has expired. Please sign in again.")
        return dict(user)

    def logout(self, token: str):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))
        return {}

    def delete_account(self, token: str):
        user = self.user_for_token(token)
        with self.connect() as db:
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("DELETE FROM identities WHERE user_id=?", (user["id"],))
            db.execute("DELETE FROM users WHERE id=?", (user["id"],))
        return {"deleted": True}

    def link(self, body: dict, token: str):
        user = self.user_for_token(token)
        claims = self.verify_credential(body.get("credential"), body.get("nonce"))
        if not hmac.compare_digest(str(claims["sub"]), user["google_sub"]):
            raise ApiError(409, "This business account is already linked to a different Google account.")
        return {"linked": True}


class Handler(BaseHTTPRequestHandler):
    service: AuthService
    server_version = "AUTOLINKAuth/1.0"

    def log_message(self, format, *args):
        # Callback URLs contain one-use authorization codes; never log query strings.
        print("%s %s %s" % (self.address_string(), self.command,
                            urlsplit(self.path).path), flush=True)

    def redirect(self, destination: str):
        self.send_response(302)
        self.send_header("Location", destination)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def popup(self, provider: str, ticket: str = "", error: str = ""):
        label = {"linkedin": "LinkedIn", "facebook": "Facebook", "instagram": "Instagram"}[provider]
        script_nonce = secrets.token_urlsafe(20)
        ticket_json = json.dumps(ticket)
        error_json = json.dumps(error)
        provider_json = json.dumps(label)
        page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{label} · AUTOLINK</title>
<style>body{{font:16px system-ui,sans-serif;background:#f5f7f6;color:#23392f;margin:0;display:grid;place-items:center;min-height:100vh}}
main{{background:white;border:1px solid #dbe4dd;border-radius:16px;padding:32px;max-width:390px;width:calc(100% - 64px);box-shadow:0 12px 35px #12271b14}}
h1{{font-size:23px;margin:0 0 14px}}p{{line-height:1.5;color:#52645b}}label{{display:block;margin:20px 0}}input[type=text]{{display:block;width:100%;box-sizing:border-box;padding:12px;margin-top:8px;border:1px solid #b9c9bf;border-radius:8px;font:inherit}}
.check{{display:flex;gap:9px;align-items:flex-start;font-size:13px}}button{{background:#214637;color:white;border:0;border-radius:8px;padding:13px 18px;font:inherit;width:100%;cursor:pointer}}a{{color:#214637}}.error{{color:#a32727}}</style>
<main><h1>Continue with {label}</h1><p id="status">Completing secure sign-in…</p>
<form id="signup" hidden><p>Create your AUTOLINK business account.</p><label>Company name
<input id="company" type="text" maxlength="160" autocomplete="organization" required></label>
<label class="check"><input id="consent" type="checkbox" required><span>I agree to the
<a href="/terms" target="_blank" rel="noopener">Terms of Service</a> and
<a href="/privacy" target="_blank" rel="noopener">Privacy Policy</a>.</span></label>
<button type="submit">Create account</button></form></main>
<script nonce="{script_nonce}">(()=>{{
const ticket={ticket_json}, initialError={error_json}, provider={provider_json};
const status=document.getElementById('status'), form=document.getElementById('signup');
async function finish(company){{
  const body={{ticket}};
  if(company){{body.companyName=company;body.consent=document.getElementById('consent').checked;}}
  const response=await fetch('/autolink/auth/oauth/finish',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body),cache:'no-store'}});
  const result=await response.json();
  if(!response.ok||result.code!==200)throw new Error(result.msg||'Sign-in failed.');
  if(result.data.registrationRequired){{form.hidden=false;status.textContent=provider+' account verified. Add your company to continue.';return;}}
  localStorage.setItem('autolink-business-session',JSON.stringify({{token:result.data.access_token,
    expiresAt:Date.now()+result.data.expire_in*1000}}));
  window.location.replace('/merchant/login');
}}
if(initialError){{status.className='error';status.textContent=initialError;}}
else finish().catch(error=>{{status.className='error';status.textContent=error.message;}});
form.addEventListener('submit',event=>{{event.preventDefault();status.className='';status.textContent='Creating account…';
  finish(document.getElementById('company').value.trim()).catch(error=>{{status.className='error';status.textContent=error.message;}});}});
}})();</script></html>'''
        payload = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", f"default-src 'none'; script-src 'nonce-{script_nonce}'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status: int, data=None, message: str = "OK"):
        payload = json.dumps({"code": 200 if status == 200 else status,
                              "msg": message, "data": data}, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def token(self):
        auth = self.headers.get("Authorization", "")
        return auth[7:] if auth.startswith("Bearer ") else ""

    def read_body(self):
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            raise ApiError(415, "JSON request body required.")
        origin = self.headers.get("Origin")
        if origin and origin != "https://autolinkglobal.com" and origin != "http://127.0.0.1:8766":
            raise ApiError(403, "Request origin is not allowed.")
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ApiError(400, "Invalid request length.") from exc
        if size < 0 or size > MAX_BODY_BYTES:
            raise ApiError(413, "Request is too large.")
        try:
            body = json.loads(self.rfile.read(size))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError(400, "Invalid JSON.") from exc
        if not isinstance(body, dict):
            raise ApiError(400, "JSON object required.")
        return body

    def handle_request(self, method: str):
        path = urlsplit(self.path).path
        if method == "GET" and path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        if method == "GET" and path == "/autolink/auth/google/config":
            self.send_json(200, {"enabled": True})
            return
        if method == "GET" and path == "/autolink/auth/social/config":
            self.send_json(200, {provider: social.enabled(provider) for provider in social.PROVIDERS})
            return
        for provider in social.PROVIDERS:
            if method == "GET" and path == f"/autolink/auth/{provider}/start":
                self.redirect(self.service.oauth_start(provider))
                return
            if method == "GET" and path == f"/autolink/auth/{provider}/callback":
                query = parse_qs(urlsplit(self.path).query)
                if query.get("error"):
                    self.popup(provider, error="Authorization was cancelled or rejected.")
                    return
                try:
                    ticket = self.service.oauth_callback(provider, query.get("state", [""])[0],
                                                         query.get("code", [""])[0])
                except ApiError as exc:
                    self.popup(provider, error=exc.message)
                    return
                self.popup(provider, ticket=ticket)
                return
        if method == "POST" and path == "/autolink/auth/oauth/finish":
            self.send_json(200, self.service.oauth_finish(self.read_body()))
            return
        if method == "POST" and path == "/autolink/auth/google/challenge":
            self.read_body()
            self.send_json(200, self.service.challenge())
            return
        if method == "POST" and path == "/autolink/auth/google/login":
            self.send_json(200, self.service.google_login(self.read_body()))
            return
        if method == "POST" and path == "/autolink/auth/google/link":
            self.send_json(200, self.service.link(self.read_body(), self.token()))
            return
        if method == "POST" and path == "/auth/logout":
            self.send_json(200, self.service.logout(self.token()))
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
            self.send_json(200, {"id": user["id"], "role": "MERCHANT", "username": user["email"],
                                 "email": user["email"], "nickName": user["display_name"],
                                 "companyName": user["company_name"]})
            return
        if method == "DELETE" and path == "/autolink/me":
            self.send_json(200, self.service.delete_account(self.token()))
            return
        if method == "GET" and path in ("/autolink/merchant/stock", "/autolink/requests"):
            self.service.user_for_token(self.token())
            self.send_json(200, [])
            return
        if method == "GET" and path == "/autolink/merchant/interest":
            self.service.user_for_token(self.token())
            self.send_json(200, {"notifications": [], "models": []})
            return
        if method == "GET" and path == "/autolink/merchant/overview":
            self.service.user_for_token(self.token())
            self.send_json(200, {"publishedStocks": 0, "pendingStocks": 0, "draftStocks": 0,
                                 "rejectedStocks": 0, "expiredStocks": 0, "offlineStocks": 0,
                                 "unansweredRequests": 0, "quotedRequests": 0, "totalRequests": 0,
                                 "contacts": 0, "unreadInterest": 0})
            return
        if method == "GET" and path == "/autolink/merchant/application":
            user = self.service.user_for_token(self.token())
            self.send_json(200, {"id": user["id"], "version": 1, "status": "DRAFT",
                                 "company_name": user["company_name"], "registration_no": "",
                                 "address": "", "contact_name": user["display_name"],
                                 "contact_email": user["email"], "contact_phone": "",
                                 "introduction": "", "documents": [], "history": []})
            return
        if path.startswith("/autolink/") or path.startswith("/auth/"):
            raise ApiError(501, "This business feature is not connected yet.")
        raise ApiError(404, "Not found.")

    def do_GET(self):
        self.dispatch("GET")

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
        except Exception:
            self.send_json(500, None, "Server error.")


def main():
    Handler.service = AuthService(DB_PATH, CLIENT_ID)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
