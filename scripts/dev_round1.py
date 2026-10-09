#!/usr/bin/env python3
"""Disposable loopback QA preview. No .env, production data, mail or Google.

Run from this isolated checkout: python3 scripts/dev_round1.py
Ctrl-C / SIGTERM stops Caddy and the API and removes every temporary file.
The only seeded identities are clearly labelled SYNTHETIC QA accounts.
"""
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


HOST = '127.0.0.1'
SITE_PORT = 18780
API_PORT = 18781
BASE = 'http://127.0.0.1:18780'
BUYER_EMAIL = 'synthetic-qa-buyer@example.com'
OWNER_EMAIL = 'synthetic-qa-owner@example.com'


def ensure_free_ports():
    for port in (SITE_PORT, API_PORT):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try:
                probe.bind((HOST, port))
            except OSError:
                raise RuntimeError('QA port '+str(port)+' is already occupied; no existing process was changed.')


def disable_google(*args, **kwargs):
    raise ValueError('Google provider is disabled in the disposable QA preview.')


def mock_mail(*args, **kwargs):
    # Deliberately no provider access, message output, or verification-code log.
    return {'id': 'SYNTHETIC_QA_NO_DELIVERY'}


def local_environment(temp, root):
    # Never inherit provider credentials or production storage locations. These
    # system values only locate installed binaries and the native temp folder.
    allowed = {key: os.environ[key] for key in ('PATH', 'TMPDIR', 'LANG', 'LC_ALL') if key in os.environ}
    allowed.update({
        'GOOGLE_CLIENT_ID': 'synthetic-local-qa-disabled.apps.googleusercontent.com',
        'AUTH_DB_PATH': str(temp/'synthetic-qa.sqlite3'),
        'AUTH_CODE_SECRET': secrets.token_urlsafe(48),
        'PORT': str(API_PORT),
        'COOKIE_SECURE': 'false',
        'DEV_ALLOWED_ORIGINS': BASE+','+'http://127.0.0.1:'+str(API_PORT),
        'PLATFORM_ADMIN_EMAIL': OWNER_EMAIL,
        'VEHICLE_IMAGE_ROOT': str(temp/'private'/'vehicle-images'),
        'SUPPLIER_DOCUMENT_ROOT': str(temp/'private'/'supplier-documents'),
        'SEO_SITE_ROOT': str(root/'site'),
        'SITE_ADDRESS': BASE,
        'XDG_CONFIG_HOME': str(temp/'caddy-config'),
        'XDG_DATA_HOME': str(temp/'caddy-data'),
        'MEMBERSHIP_RESTRICTIONS': 'false',
        'MAIL_PROVIDER': 'disabled',
    })
    return allowed


def seed_accounts(auth, password_hash):
    now = int(time.time())
    passwords = {}
    with auth.connect() as db:
        for ident, email, name, role in (
            ('SYNTHETIC-QA-BUYER', BUYER_EMAIL, 'SYNTHETIC QA buyer', 'BUYER'),
            ('SYNTHETIC-QA-OWNER', OWNER_EMAIL, 'SYNTHETIC QA platform owner', 'PLATFORM_ADMIN'),
        ):
            password = secrets.token_urlsafe(18)+'-QA!'
            passwords[email] = password
            db.execute('''INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at,preferred_language)
                VALUES (?,?,?,?,?,?,?,?)''', (ident,email,name,'SYNTHETIC QA COMPANY',role,now,now,'zh'))
            db.execute('INSERT INTO email_identities(email,user_id) VALUES (?,?)', (email,ident))
            db.execute('INSERT INTO email_passwords(user_id,password_hash,updated_at) VALUES (?,?,?)',
                       (ident,password_hash(password),now))
        # Reference catalogues are real maintained public model data. Business
        # records, inventory, prices, payments and signatures are not synthesized.
        tables = ('supplier_profiles','supplier_applications','supplier_vehicles','buyer_inquiries',
                  'trade_quotes','buyer_memberships','supplier_agreement_confirmations',
                  'supplier_agreement_confirmation_revisions')
        existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {table:db.execute('SELECT count(*) FROM '+table).fetchone()[0]
                  for table in tables if table in existing}
        if any(counts.values()):
            raise RuntimeError('Fresh QA database unexpectedly contains business records.')
    return passwords, counts


def await_ready(process):
    deadline = time.monotonic()+12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Local Caddy exited; inspect its temporary QA log before cleanup.')
        try:
            with urllib.request.urlopen(BASE+'/autolink/public/models',timeout=1) as response:
                payload=json.load(response)
                if response.status==200 and len(payload.get('data') or [])==234:
                    return
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(.15)
    raise RuntimeError('Local QA preview did not become ready.')


def main():
    root = Path(__file__).resolve().parent.parent
    if root.name != 'autolink-round1-isolated-20261010-015717':
        raise RuntimeError('This QA launcher is restricted to the authorized isolated checkout.')
    caddy = shutil.which('caddy')
    if not caddy:
        raise RuntimeError('Official local Caddy is required; this script does not install tools.')
    ensure_free_ports()
    stop = threading.Event()
    for name in ('SIGINT','SIGTERM'):
        signal.signal(getattr(signal,name),lambda *_: stop.set())
    with tempfile.TemporaryDirectory(prefix='autolink-round1-SYNTHETIC-QA-') as directory:
        temp = Path(directory)
        environment = local_environment(temp,root)
        os.environ.clear()
        os.environ.update(environment)
        # Import only this isolated auth package, after replacing inherited env.
        sys.path.insert(0,str(root/'auth'))
        from app import AuthService, Handler
        from business_mail import BusinessMailer
        from buyer_service import BuyerService
        from email_auth import EmailAuthService, password_hash
        from seo_service import PublicSEOService
        from trade_service import TradeService
        from http.server import ThreadingHTTPServer

        auth = AuthService(temp/'synthetic-qa.sqlite3',os.environ['GOOGLE_CLIENT_ID'],verifier=disable_google)
        auth.mailer = BusinessMailer(auth,sender=mock_mail)
        email = EmailAuthService(auth,sender=mock_mail)
        buyer = BuyerService(auth)
        trade = TradeService(auth)
        passwords, counts = seed_accounts(auth,password_hash)

        class LocalQAHandler(Handler):
            def log_message(self,*args):
                pass  # No URLs, payloads, cookies or credentials in the QA log.
            def handle_request(self,method):
                path = urlsplit(self.path).path
                if path=='/autolink/auth/google/config' and method=='GET':
                    self.send_json(200,{'enabled':False,'qaProviderDisabled':True})
                    return
                if path.startswith('/autolink/auth/google/') and method=='POST':
                    self.send_json(503,None,'SYNTHETIC QA: Google provider is disabled.')
                    return
                return super().handle_request(method)

        LocalQAHandler.service=auth
        LocalQAHandler.email_auth=email
        LocalQAHandler.buyer=buyer
        LocalQAHandler.trade=trade
        LocalQAHandler.platform=trade.platform
        LocalQAHandler.seo=PublicSEOService(trade,root/'site')
        server=ThreadingHTTPServer((HOST,API_PORT),LocalQAHandler)
        thread=threading.Thread(target=server.serve_forever,name='autolink-local-QA-api',daemon=True)
        thread.start()
        process=None
        try:
            config=(root/'Caddyfile').read_text()
            if config.count('root * /srv')!=1 or 'auth:8080' not in config:
                raise RuntimeError('Candidate Caddy layout changed; review the local replacements.')
            if config.count('{$SITE_ADDRESS} {')!=1:
                raise RuntimeError('Candidate Caddy site layout changed; review the local bind.')
            config=config.replace('{$SITE_ADDRESS} {','{$SITE_ADDRESS} {\n\tbind '+HOST,1)
            config='{\n  admin off\n  auto_https off\n}\n'+config.replace('root * /srv','root * '+json.dumps(str(root/'site'))).replace('auth:8080',HOST+':'+str(API_PORT))
            config_path=temp/'Caddyfile';config_path.write_text(config)
            log_path=temp/'caddy-QA.log'
            with log_path.open('w') as log:
                result=subprocess.run([caddy,'validate','--config',str(config_path),'--adapter','caddyfile'],
                    stdout=log,stderr=log,env=dict(os.environ),cwd=root,timeout=20,check=False)
                if result.returncode:
                    raise RuntimeError('Local candidate Caddy configuration failed validation.')
                process=subprocess.Popen([caddy,'run','--config',str(config_path),'--adapter','caddyfile'],
                    stdout=log,stderr=log,env=dict(os.environ),cwd=root)
                await_ready(process)
                info={'warning':'SYNTHETIC QA ONLY — temporary SQLite, no business fixtures, no provider delivery',
                      'url':BASE,'api_url':'http://127.0.0.1:'+str(API_PORT),'pid':os.getpid(),'caddy_pid':process.pid,
                      'temporary_directory':str(temp),'business_record_counts':counts,'accounts':passwords,
                      'cleanup':'Ctrl-C, or kill -TERM '+str(os.getpid())+'; both listeners stop and all temporary data is deleted.'}
                info_path=temp/'qa-info.json';info_path.write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n');os.chmod(info_path,0o600)
                print(json.dumps(info,ensure_ascii=False,indent=2),flush=True)
                while not stop.wait(.4):
                    if process.poll() is not None:
                        raise RuntimeError('Local Caddy stopped unexpectedly.')
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait(timeout=5)
            server.shutdown();server.server_close();thread.join(timeout=2)
            auth.mailer.stop_event.set()
    print('SYNTHETIC QA stopped; temporary database, files and Caddy state deleted.',flush=True)


if __name__=='__main__':
    main()
