"""Validated, re-encoded listing images; original uploads are never served."""
import base64
import binascii
import io
import os
import time
import uuid
import warnings
import re
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from buyer_service import BuyerError, text

ROOT=Path(os.environ.get('VEHICLE_IMAGE_ROOT','/data/private/vehicle-images'))
Image.MAX_IMAGE_PIXELS=24_000_000


class ListingImages:
    def __init__(self, auth):
        self.auth=auth
        with auth.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS vehicle_images (
                id TEXT PRIMARY KEY,listing_id TEXT NOT NULL REFERENCES supplier_vehicles(id),
                supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                filename TEXT NOT NULL,stored_name TEXT NOT NULL UNIQUE,
                bytes INTEGER NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,
                created_at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS vehicle_images_listing ON vehicle_images(listing_id,created_at);
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(vehicle_images)')}
            for name, declaration in (('stock_photo', 'INTEGER NOT NULL DEFAULT 0'), ('attested_by', 'TEXT REFERENCES users(id)'), ('attested_at', 'INTEGER')):
                if name not in columns:
                    db.execute(f'ALTER TABLE vehicle_images ADD COLUMN {name} {declaration}')

    def list(self, listing_id):
        with self.auth.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,listing_id,filename,bytes,width,height,created_at,stock_photo,attested_at FROM vehicle_images WHERE listing_id=? ORDER BY created_at,id',(listing_id,))]

    @staticmethod
    def validate_stored(row):
        if not re.fullmatch(r'[0-9a-f]{32}\.jpg', row['stored_name']):
            raise BuyerError(409, 'A listing photo is unavailable. Upload a fresh photo.')
        try:
            path = ROOT / row['stored_name']
            if path.is_symlink() or not path.is_file() or path.stat().st_size != row['bytes']:
                raise OSError('Missing photo')
            with Image.open(path) as image:
                if image.format != 'JPEG' or image.size != (row['width'], row['height']) or min(image.size) < 200:
                    raise OSError('Invalid photo')
                image.verify()
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            raise BuyerError(409, 'A listing photo is unavailable. Upload a fresh photo.') from exc

    def require_stock_photos(self, db, listing_id, supplier_id):
        rows = db.execute('SELECT * FROM vehicle_images WHERE listing_id=? AND supplier_id=? AND stock_photo=1 AND attested_by IS NOT NULL AND attested_at IS NOT NULL', (listing_id, supplier_id)).fetchall()
        if not rows:
            raise BuyerError(409, 'Upload and confirm at least one real stock photo before review.')
        for row in rows:
            self.validate_stored(row)

    def attest(self, supplier, listing_id, image_id, body):
        if body.get('stockPhoto') is not True:
            raise BuyerError(400, 'Confirm that this is a real photo of this listing inventory.')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT i.* FROM vehicle_images i JOIN supplier_vehicles v ON v.id=i.listing_id WHERE i.id=? AND i.listing_id=? AND i.supplier_id=? AND v.supplier_id=? AND v.status IN (\'DRAFT\',\'REJECTED\') AND v.archived_at IS NULL', (image_id, listing_id, supplier['id'], supplier['id'])).fetchone()
            if not row:
                raise BuyerError(404, 'Editable listing photo not found.')
            self.validate_stored(row)
            db.execute('UPDATE vehicle_images SET stock_photo=1,attested_by=?,attested_at=? WHERE id=?', (supplier.get('actor_user_id', supplier['id']), int(time.time()), image_id))
            db.execute('INSERT INTO trade_audit VALUES (?,?,?,?,?,?,?,?)', ('AUD-'+uuid.uuid4().hex.upper(), supplier.get('actor_user_id',supplier['id']), supplier['id'], 'VEHICLE_STOCK_PHOTO_CONFIRMED', 'vehicle', listing_id, int(time.time()), image_id))
        return self.list(listing_id)

    def copy_into(self, db, supplier_id, source_id, destination_id):
        """Copy already sanitized JPEGs into an independent private draft.

        Caller owns the database transaction. Returned files must be removed if
        that transaction fails; partial filesystem work is cleaned up here.
        """
        paths = []
        try:
            rows = db.execute('SELECT * FROM vehicle_images WHERE listing_id=? AND supplier_id=? ORDER BY created_at,id LIMIT 8',
                              (source_id, supplier_id)).fetchall()
            for row in rows:
                if not re.fullmatch(r'[0-9a-f]{32}\.jpg', row['stored_name']):
                    raise BuyerError(409, 'A listing photo is unavailable. Upload a fresh photo.')
                try:
                    data = (ROOT / row['stored_name']).read_bytes()
                except OSError as exc:
                    raise BuyerError(409, 'A listing photo is unavailable. Upload a fresh photo.') from exc
                if len(data) != row['bytes'] or len(data) > 5_000_000:
                    raise BuyerError(409, 'A listing photo is unavailable. Upload a fresh photo.')
                stored = uuid.uuid4().hex + '.jpg'
                path = ROOT / stored
                with path.open('xb') as file:
                    paths.append(path)
                    os.chmod(path, 0o600)
                    file.write(data)
                db.execute('INSERT INTO vehicle_images(id,listing_id,supplier_id,filename,stored_name,bytes,width,height,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                           ('IMG-' + uuid.uuid4().hex.upper(), destination_id, supplier_id,
                            row['filename'], stored, len(data), row['width'], row['height'], int(time.time())))
        except Exception:
            for path in paths:
                path.unlink(missing_ok=True)
            raise
        return paths

    def add(self, supplier, listing_id, body):
        if body.get('stockPhoto') is not True:
            raise BuyerError(400, 'Confirm that this is a real photo of this listing inventory.')
        filename=text(body.get('filename'),'filename',160,True)
        mime=body.get('contentType')
        if mime not in ('image/jpeg','image/png') or Path(filename).suffix.lower() not in ('.jpg','.jpeg','.png') or '/' in filename or '\\' in filename:
            raise BuyerError(400,'PNG or JPEG image required.')
        encoded=body.get('base64')
        if not isinstance(encoded,str) or len(encoded)>8_000_000:
            raise BuyerError(413,'Image must be 5 MB or smaller.')
        try:raw=base64.b64decode(encoded,validate=True)
        except (ValueError,binascii.Error) as exc:raise BuyerError(400,'Invalid image encoding.') from exc
        if not 20<=len(raw)<=5_000_000:
            raise BuyerError(413,'Image must be 5 MB or smaller.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as original:
                    if original.format not in ('PNG','JPEG') or (mime=='image/png')!=(original.format=='PNG') or original.width<200 or original.height<200:
                        raise BuyerError(400,'A matching PNG/JPEG of at least 200 × 200 pixels is required.')
                    original.verify()
                with Image.open(io.BytesIO(raw)) as original:
                    image=ImageOps.exif_transpose(original).convert('RGB')
                    image.thumbnail((2400,2400))
                    output=io.BytesIO();image.save(output,'JPEG',quality=88,optimize=True)
                    data=output.getvalue();width,height=image.size
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombWarning,Image.DecompressionBombError) as exc:
            raise BuyerError(400,'Image cannot be decoded safely.') from exc
        image_id='IMG-'+uuid.uuid4().hex.upper();stored=uuid.uuid4().hex+'.jpg'
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700);path=ROOT/stored
        try:
            with self.auth.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                listing=db.execute('SELECT status FROM supplier_vehicles WHERE id=? AND supplier_id=? AND archived_at IS NULL',(listing_id,supplier['id'])).fetchone()
                if not listing:raise BuyerError(404,'Vehicle listing not found.')
                if listing['status'] not in ('DRAFT','REJECTED'):raise BuyerError(409,'Images can be added only to draft or rejected listings.')
                if db.execute('SELECT count(*) FROM vehicle_images WHERE listing_id=?',(listing_id,)).fetchone()[0]>=8:raise BuyerError(409,'Maximum eight images per listing.')
                with path.open('xb') as file:
                    os.chmod(path,0o600);file.write(data)
                now = int(time.time())
                db.execute('INSERT INTO vehicle_images(id,listing_id,supplier_id,filename,stored_name,bytes,width,height,created_at,stock_photo,attested_by,attested_at) VALUES (?,?,?,?,?,?,?,?,?,1,?,?)',(image_id,listing_id,supplier['id'],filename,stored,len(data),width,height,now,supplier.get('actor_user_id',supplier['id']),now))
        except Exception:
            path.unlink(missing_ok=True);raise
        return next(row for row in self.list(listing_id) if row['id']==image_id)

    def bytes(self, image_id, user=None):
        with self.auth.connect() as db:
            row=db.execute('''SELECT i.stored_name,i.supplier_id,v.status,v.archived_at,a.status AS company_status,u.status AS account_status,
                p.published,cm.active AS model_active,cb.active AS brand_active,
                u.deleted_at,u.email_verified_at,u.role AS account_role,u.is_test_workspace
                FROM vehicle_images i JOIN supplier_vehicles v ON v.id=i.listing_id
                JOIN supplier_applications a ON a.supplier_id=i.supplier_id JOIN users u ON u.id=i.supplier_id
                JOIN supplier_profiles p ON p.user_id=i.supplier_id
                LEFT JOIN catalog_models cm ON cm.id=v.model_id LEFT JOIN catalog_brands cb ON cb.id=cm.brand_id
                WHERE i.id=?''',(image_id,)).fetchone()
        public=row and row['status']=='ONLINE' and row['company_status']=='APPROVED' and row['account_status']=='ACTIVE' and row['archived_at'] is None and row['published'] and row['model_active'] and row['brand_active'] and row['deleted_at'] is None and row['email_verified_at'] is not None and row['account_role'] in ('BUYER','MERCHANT','SUPPLIER')
        public = public and not row['is_test_workspace']
        privileged=row and user and (user['id']==row['supplier_id'] or user['role']=='PLATFORM_ADMIN')
        if not public and not privileged:raise BuyerError(404,'Image not found.')
        return (ROOT/row['stored_name']).read_bytes()
