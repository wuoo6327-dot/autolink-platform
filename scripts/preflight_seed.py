"""Synthetic fixtures for an EMPTY isolated round3 volume; never production."""
import json
import os
import time
from pathlib import Path

from app import AuthService
from buyer_service import BuyerService
from email_auth import EmailAuthService, password_hash
from trade_service import TradeService
from PIL import Image
import image_service

assert os.environ.get('AUTOLINK_PREFLIGHT_STAGE') == 'round3'
assert os.environ.get('AUTH_DB_PATH') == '/data/round3.sqlite3'
assert not os.environ.get('MAIL_PROVIDER') and not os.environ.get('RESEND_API_KEY')
auth = AuthService(Path('/data/round3.sqlite3'), 'offline-qa-client', verifier=lambda *_: {})
email = EmailAuthService(auth, sender=lambda *_: None)
BuyerService(auth)
trade = TradeService(auth)
now = int(time.time())
password = 'Synthetic-QA-Only-2026!'
hashed = password_hash(password)
with auth.connect() as db:
    assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 0
    for name, role in [('owner', 'PLATFORM_ADMIN'), ('other-admin', 'PLATFORM_ADMIN'),
                       ('buyer', 'BUYER'), ('merchant', 'MERCHANT'), ('outsider', 'BUYER'), ('suspended', 'BUYER')]:
        db.execute('INSERT INTO users(id,email,display_name,company_name,role,created_at,email_verified_at) VALUES (?,?,?,?,?,?,?)',
                   (name, 'qa-'+name+'@example.invalid', 'SYNTHETIC QA '+name, 'SYNTHETIC QA', role, now, now))
        db.execute('INSERT INTO email_identities VALUES (?,?)', ('qa-'+name+'@example.invalid', name))
        db.execute('INSERT INTO email_passwords VALUES (?,?,?)', (name, hashed, now))
    db.execute("UPDATE users SET status='SUSPENDED' WHERE id='suspended'")
tokens = {name: auth.session_for_user(name)['access_token'] for name in ['owner', 'other-admin', 'buyer', 'merchant', 'outsider']}
user = auth.user_for_token(tokens['merchant'])
trade.save_application(user, {'companyName':'SYNTHETIC QA ONLY','registrationNo':'QA-NOT-REAL',
    'country':'China','address':'SYNTHETIC','contactName':'QA','contactPhone':'+860000'})
with auth.connect() as db:
    db.execute("UPDATE supplier_applications SET status='APPROVED' WHERE supplier_id='merchant'")
    db.execute("UPDATE supplier_profiles SET published=1 WHERE user_id='merchant'")
listing = trade.save_vehicle(user, {'modelId':'zeekr-9x-2026','modelYear':2026,'priceMinor':100000,
    'stock':2,'moq':1,'originPort':'SYNTHETIC QA','validUntil':'2099-01-01'})
image_service.ROOT.mkdir(parents=True, exist_ok=True)
Image.new('RGB', (64, 64), 'blue').save(image_service.ROOT/'qa-private.jpg', 'JPEG')
with auth.connect() as db:
    db.execute('INSERT INTO vehicle_images(id,listing_id,supplier_id,filename,stored_name,bytes,width,height,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
        ('qa-private',listing['id'],'merchant','qa-private.jpg','qa-private.jpg',(image_service.ROOT/'qa-private.jpg').stat().st_size,64,64,now))
    before = {t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['supplier_applications','supplier_vehicles','vehicle_images']}
Path('/data/qa-fixtures.json').write_text(json.dumps({'syntheticOnly':True,'tokens':tokens,'password':password,'before':before}))
print('Synthetic fixtures seeded into /data/round3.sqlite3; no emails sent.')
