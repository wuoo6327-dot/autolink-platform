"""Durable transactional notifications; never blocks or rolls back trade submission."""
import html
import json
import os
import threading
import time
import uuid
from urllib.parse import urlsplit

from mail_service import configured, send_message


from mail_templates import RESOURCES, copy_for

TEMPLATES = RESOURCES['en']['events']


def safe_path(path):
    return (isinstance(path, str) and len(path) <= 500 and any(path == root or path.startswith(root+'/') for root in ('/buyer','/supplier','/admin'))
            and not path.startswith('//') and '\\' not in path and not any(ord(c) < 32 for c in path)
            and not urlsplit(path).netloc and '..' not in urlsplit(path).path.split('/'))


def render(event, path, language='en'):
    language, labels = copy_for(language)
    title, text = labels['events'][event]
    button = labels['button']
    direction = 'rtl' if language == 'ar' else 'ltr'
    lang = 'zh-CN' if language == 'zh' else language
    base = os.environ.get('APP_URL', 'https://autolinkglobal.com').rstrip('/')
    parsed = urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not safe_path(path):
        raise ValueError('Invalid notification destination.')
    url = base + path
    footer = labels['footer']
    plain = 'AUTOLINK\n\n' + title + '\n\n' + text + '\n\n' + button + ': ' + url + '\n\n' + footer
    content = f'''<!doctype html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f7f9f7;font-family:Arial,sans-serif;color:#233b2d"><main style="max-width:520px;margin:30px auto;padding:32px;background:white;border:1px solid #e0e9e1"><strong style="font-size:22px;letter-spacing:.08em">AUTOLINK</strong><h1 style="font-size:21px;margin-top:32px">{html.escape(title)}</h1><p style="line-height:1.7">{html.escape(text)}</p><p><a href="{html.escape(url, quote=True)}" style="display:inline-block;padding:12px 20px;background:#224734;color:white;text-decoration:none">{html.escape(button)}</a></p><hr style="border:0;border-top:1px solid #e3ebe4;margin:28px 0"><small style="color:#667a6b">{html.escape(footer)}</small></main></body></html>'''
    return 'AUTOLINK · ' + title, plain, content


class BusinessMailer:
    def __init__(self, auth, sender=None):
        self.auth = auth
        self.sender = sender or send_message
        self.testing_sender = sender is not None
        self.stop_event = threading.Event()
        self.thread = None
        with auth.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS business_mail_jobs (
                    id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
                    event TEXT NOT NULL,entity_id TEXT NOT NULL,url TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE,status TEXT NOT NULL DEFAULT 'PENDING',
                    attempt_count INTEGER NOT NULL DEFAULT 0,next_attempt_at INTEGER NOT NULL,
                    first_attempt_at INTEGER,lease_until INTEGER,lease_token TEXT,
                    payload TEXT,provider_id TEXT,last_error TEXT,
                    created_at INTEGER NOT NULL,sent_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS business_mail_due ON business_mail_jobs(status,next_attempt_at);
            ''')

    @staticmethod
    def enqueue(db, user_id, event, entity_id, path, dedupe_key):
        if event not in TEMPLATES or not safe_path(path):
            return None
        now = int(time.time());ident = 'MAIL-' + uuid.uuid4().hex
        db.execute('''INSERT OR IGNORE INTO business_mail_jobs(id,user_id,event,entity_id,url,dedupe_key,next_attempt_at,created_at)
            SELECT ?,id,?,?,?,?,?,? FROM users WHERE id=? AND status='ACTIVE' AND deleted_at IS NULL AND email_verified_at IS NOT NULL''',
            (ident,event,entity_id,path,dedupe_key,now,now,user_id))
        return ident

    @staticmethod
    def enqueue_invitation(db, supplier_id, invitation_id):
        # The existing user_id FK identifies the authorizing company owner for
        # this event. Delivery address is resolved from the invitation at claim
        # time; no placeholder user or separate mail queue is created.
        return BusinessMailer.enqueue(db, supplier_id, 'TEAM_INVITATION', invitation_id,
                                      '/supplier/team', 'team-invitation:'+invitation_id)

    @staticmethod
    def eligible(db, job):
        uid, entity, event = job['user_id'], job['entity_id'], job['event']
        if event == 'TEAM_INVITATION':
            return bool(db.execute('''SELECT 1 FROM supplier_team_invites i
                JOIN supplier_applications a ON a.supplier_id=i.supplier_id
                JOIN users owner ON owner.id=i.supplier_id
                WHERE i.id=? AND i.supplier_id=? AND i.invited_by=?
                AND i.status='PENDING' AND i.expires_at>?
                AND a.status='APPROVED' AND owner.role IN ('MERCHANT','SUPPLIER')
                AND owner.status='ACTIVE' AND owner.deleted_at IS NULL
                AND owner.email_verified_at IS NOT NULL''',
                (entity,uid,uid,int(time.time()))).fetchone())
        if event == 'WELCOME':return uid == entity
        if event == 'NEW_QUOTE':
            return bool(db.execute("SELECT 1 FROM trade_quotes WHERE id=? AND buyer_id=? AND status IN ('SENT','VIEWED') AND valid_until>=date('now')", (entity, uid)).fetchone())
        if event == 'QUOTE_CANCELLED':
            return bool(db.execute("SELECT 1 FROM trade_quotes WHERE id=? AND buyer_id=? AND status='CANCELLED' AND sent_at IS NOT NULL", (entity, uid)).fetchone())
        if event == 'NEW_INQUIRY':
            return bool(db.execute('''SELECT 1 FROM buyer_inquiries i JOIN supplier_applications a ON a.supplier_id=i.supplier_id
                WHERE i.id=? AND i.status!='CLOSED' AND a.status='APPROVED' AND
                (i.supplier_id=? OR (i.assigned_to=? AND EXISTS (SELECT 1 FROM supplier_team_members m
                    WHERE m.supplier_id=i.supplier_id AND m.user_id=? AND m.status='ACTIVE')))''', (entity, uid, uid, uid)).fetchone())
        if event.startswith('SUPPLIER_'):
            return uid == entity and bool(db.execute('SELECT 1 FROM supplier_applications WHERE supplier_id=? AND status=?', (uid,event[9:])).fetchone())
        if event.startswith('VEHICLE_'):
            states = ('APPROVED','ONLINE','OFFLINE','SOLD_OUT') if event == 'VEHICLE_APPROVED' else ('REJECTED',)
            return bool(db.execute('SELECT 1 FROM supplier_vehicles WHERE id=? AND supplier_id=? AND archived_at IS NULL AND status IN ('+','.join('?' for _ in states)+')', (entity,uid,*states)).fetchone())
        if event.startswith('QUOTE_'):
            return bool(db.execute('SELECT 1 FROM trade_quotes WHERE id=? AND supplier_id=? AND status=?', (entity,uid,event[6:])).fetchone())
        if event == 'MEMBERSHIP_EXPIRY':
            return bool(db.execute("SELECT 1 FROM buyer_memberships WHERE id=? AND user_id=? AND end_at<=? AND status IN ('ACTIVE','EXPIRED')", (entity, uid, int(time.time()))).fetchone())
        if event == 'TEAM_INVITED':
            return bool(db.execute('''SELECT 1 FROM supplier_team_invites i JOIN users u ON u.email=i.email
                JOIN supplier_applications a ON a.supplier_id=i.supplier_id JOIN users owner ON owner.id=i.supplier_id
                WHERE i.id=? AND u.id=? AND i.status='PENDING' AND i.expires_at>?
                AND a.status='APPROVED' AND owner.status='ACTIVE' AND owner.deleted_at IS NULL
                AND owner.email_verified_at IS NOT NULL AND owner.role IN ('MERCHANT','SUPPLIER') ''', (entity,uid,int(time.time()))).fetchone())
        if event == 'TEAM_JOINED':
            return bool(db.execute("SELECT 1 FROM supplier_team_members WHERE supplier_id=? AND user_id=? AND status='ACTIVE'", (uid, entity)).fetchone())
        if event == 'BUYER_ASSIGNED':
            return bool(db.execute('''SELECT 1 FROM supplier_crm c JOIN supplier_team_members m ON m.supplier_id=c.supplier_id
                AND m.user_id=c.assigned_to WHERE c.buyer_id=? AND c.assigned_to=? AND m.status='ACTIVE' ''', (entity, uid)).fetchone())
        return False

    def queue_membership_expiry(self):
        now = int(time.time())
        with self.auth.connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='buyer_memberships'").fetchone():return
            for row in db.execute("SELECT id,user_id,end_at FROM buyer_memberships WHERE status IN ('ACTIVE','EXPIRED') AND end_at<=? AND end_at>?", (now, now-86400)):
                self.enqueue(db, row['user_id'], 'MEMBERSHIP_EXPIRY', row['id'], '/buyer/membership', 'membership-expiry:'+row['id']+':'+str(row['end_at']))

    def claim(self):
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE business_mail_jobs SET status='FAILED',last_error='RETRY_WINDOW_EXPIRED',payload=NULL WHERE status IN ('PENDING','SENDING') AND first_attempt_at IS NOT NULL AND first_attempt_at<?", (now-23*3600,))
            db.execute("UPDATE business_mail_jobs SET status='FAILED',last_error='ATTEMPT_LIMIT',payload=NULL WHERE status='SENDING' AND lease_until<=? AND attempt_count>=5", (now,))
            job = db.execute('''SELECT j.*,u.email,u.status AS user_status,u.email_verified_at,u.deleted_at,u.preferred_language
                FROM business_mail_jobs j JOIN users u ON u.id=j.user_id WHERE
                (j.status='PENDING' AND j.next_attempt_at<=?) OR (j.status='SENDING' AND j.lease_until<=?)
                ORDER BY j.created_at,j.id LIMIT 1''', (now, now)).fetchone()
            if not job:return None
            if job['first_attempt_at'] is None and db.execute('SELECT count(*) FROM business_mail_jobs WHERE user_id=? AND first_attempt_at>?', (job['user_id'],now-3600)).fetchone()[0]>=20:
                db.execute('UPDATE business_mail_jobs SET next_attempt_at=? WHERE id=?', (now+3600,job['id']))
                return {'cancelled':True}
            if job['user_status'] != 'ACTIVE' or job['deleted_at'] is not None or not job['email_verified_at'] or not self.eligible(db, job):
                db.execute("UPDATE business_mail_jobs SET status='CANCELLED',last_error='RECIPIENT_OR_EVENT_UNAVAILABLE',payload=NULL WHERE id=?", (job['id'],))
                return {'cancelled':True}
            email, language = job['email'], job['preferred_language']
            if job['event'] == 'TEAM_INVITATION':
                invitation = db.execute('SELECT email FROM supplier_team_invites WHERE id=?',
                                        (job['entity_id'],)).fetchone()
                email = invitation['email']
                recipient = db.execute('SELECT status,deleted_at,role,email_verified_at,preferred_language FROM users WHERE email=?',
                                       (email,)).fetchone()
                if recipient:
                    if recipient['status'] != 'ACTIVE' or recipient['deleted_at'] is not None or recipient['role'] not in ('BUYER','MERCHANT','SUPPLIER'):
                        db.execute("UPDATE business_mail_jobs SET status='CANCELLED',last_error='RECIPIENT_OR_EVENT_UNAVAILABLE',payload=NULL WHERE id=?", (job['id'],))
                        return {'cancelled':True}
                    if recipient['email_verified_at']:
                        language = recipient['preferred_language']
            payload = json.loads(job['payload']) if job['payload'] else None
            if payload and payload['email'] != email:
                db.execute("UPDATE business_mail_jobs SET status='CANCELLED',last_error='RECIPIENT_CHANGED',payload=NULL WHERE id=?", (job['id'],))
                return {'cancelled':True}
            if not payload:
                try:subject,plain,content = render(job['event'],job['url'],language)
                except (KeyError,ValueError):
                    db.execute("UPDATE business_mail_jobs SET status='FAILED',last_error='TEMPLATE_OR_DESTINATION_UNAVAILABLE',payload=NULL WHERE id=?", (job['id'],))
                    return {'cancelled':True}
                payload = {'email':email,'subject':subject,'plain':plain,'content':content}
            lease = uuid.uuid4().hex
            db.execute("UPDATE business_mail_jobs SET status='SENDING',attempt_count=attempt_count+1,first_attempt_at=COALESCE(first_attempt_at,?),lease_until=?,lease_token=?,payload=? WHERE id=?", (now,now+120,lease,json.dumps(payload),job['id']))
            return {**dict(job),'attempt_count':job['attempt_count']+1,'lease_token':lease,'payload':payload}

    def process_once(self, limit=5):
        if not self.testing_sender and not configured():return 0
        processed = 0
        for _ in range(min(20,max(1,limit))):
            job = self.claim()
            if job is None:break
            if job.get('cancelled'):continue
            try:
                payload = job['payload']
                provider_id = self.sender(payload['email'],payload['subject'],payload['plain'],payload['content'],idempotency_key='business/'+job['id'])
                if not provider_id:raise ValueError('Provider acceptance missing.')
                with self.auth.connect() as db:
                    db.execute("UPDATE business_mail_jobs SET status='SENT',sent_at=?,provider_id=?,last_error=NULL,payload=NULL,lease_until=NULL,lease_token=NULL WHERE id=? AND lease_token=?", (int(time.time()),str(provider_id)[:200],job['id'],job['lease_token']))
                processed += 1
            except Exception:
                # Persist a fixed code only. Provider errors may include credentials or message content.
                failed = job['attempt_count'] >= 5
                delay = (30,120,480,1800,7200)[min(4,job['attempt_count']-1)]
                with self.auth.connect() as db:
                    db.execute("UPDATE business_mail_jobs SET status=?,next_attempt_at=?,last_error='DELIVERY_UNAVAILABLE',payload=CASE WHEN ? THEN NULL ELSE payload END,lease_until=NULL,lease_token=NULL WHERE id=? AND lease_token=?", ('FAILED' if failed else 'PENDING',int(time.time())+delay,int(failed),job['id'],job['lease_token']))
        return processed

    def status(self):
        with self.auth.connect() as db:
            counts = {row['status']:row['count'] for row in db.execute('SELECT status,count(*) AS count FROM business_mail_jobs GROUP BY status')}
        return {'configured':bool(configured()),'counts':{key:counts.get(key,0) for key in ('PENDING','SENDING','SENT','FAILED','CANCELLED')},'sentMeans':'Accepted by the mail provider; inbox delivery is not confirmed.'}

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.queue_membership_expiry()
                self.process_once()
            except Exception:
                # No secret-bearing exception output. A later iteration retries the durable jobs.
                pass
            self.stop_event.wait(30)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.thread = threading.Thread(target=self.run,name='autolink-business-mail',daemon=True)
        self.thread.start()
