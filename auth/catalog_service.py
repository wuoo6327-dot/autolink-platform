"""Maintain existing model references in SQLite without inventing supplier stock."""
import json
import re
import time
import uuid
from urllib.parse import urlsplit
from buyer_service import CATALOG, BuyerError, text


def media_url(value):
    value=text(value,'image URL',1000)
    if not value:return ''
    if '\\' in value or any(ord(char)<32 for char in value):
        raise BuyerError(400,'Invalid image URL.')
    try:parsed=urlsplit(value)
    except ValueError as exc:raise BuyerError(400,'Invalid image URL.') from exc
    if value.startswith('/') and not value.startswith('//') and '..' not in parsed.path.split('/'):
        return value
    if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password:
        return value
    raise BuyerError(400,'Use a same-site image path or an HTTPS image URL.')


def slug(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',value) or len(value)>100:
        raise BuyerError(400,'Use a lowercase slug containing letters, numbers and hyphens.')
    return value


class CatalogService:
    def __init__(self,auth):
        self.auth=auth
        with auth.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS catalog_brands (
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,country TEXT NOT NULL DEFAULT '',
                    logo TEXT NOT NULL DEFAULT '',overview TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS catalog_models (
                    id TEXT PRIMARY KEY,brand_id TEXT NOT NULL REFERENCES catalog_brands(id),
                    name TEXT NOT NULL,model_year INTEGER,body_type TEXT NOT NULL DEFAULT '',
                    energy TEXT NOT NULL DEFAULT '',image TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',specifications TEXT NOT NULL DEFAULT '{}',
                    active INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS catalog_models_brand ON catalog_models(brand_id,active,model_year);
            ''')
            now=int(time.time())
            # Import the current reference library once per ID. Never overwrite admin edits.
            for item in CATALOG.values():
                brand=re.sub(r'[^a-z0-9]+','-',item['brand'].lower()).strip('-')
                db.execute('INSERT OR IGNORE INTO catalog_brands(id,name,created_at,updated_at) VALUES (?,?,?,?)',
                    (brand,item['brand'],now,now))
                db.execute('''INSERT OR IGNORE INTO catalog_models(id,brand_id,name,model_year,body_type,energy,image,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',(item['id'],brand,item['model'],item.get('year'),item.get('bodyType') or '',
                    item.get('energy') or '',item.get('image') or '',now,now))

    @staticmethod
    def model_row(row):
        return {'id':row['id'],'brandId':row['brand_id'],'brand':row['brand_name'],'model':row['name'],
            'year':row['model_year'],'bodyType':row['body_type'],'energy':row['energy'],'image':row['image'],
            'description':row['description'],'specifications':json.loads(row['specifications']),
            'active':bool(row['active']),'brandActive':bool(row['brand_active']),'brandLogo':row['brand_logo'],
            'url':'/trade/models/'+row['id']}

    def models(self,public=True,brand=None):
        with self.auth.connect() as db:
            sql='''SELECT m.*,b.name AS brand_name,b.active AS brand_active,b.logo AS brand_logo FROM catalog_models m
                JOIN catalog_brands b ON b.id=m.brand_id WHERE 1=1''';args=[]
            if public:sql+=' AND m.active=1 AND b.active=1'
            if brand:sql+=' AND b.id=?';args.append(brand)
            rows=db.execute(sql+' ORDER BY b.name,m.name,m.model_year DESC',args).fetchall()
        return [self.model_row(row) for row in rows]

    def get(self,model_id,default=None):
        with self.auth.connect() as db:
            row=db.execute('''SELECT m.*,b.name AS brand_name,b.active AS brand_active,b.logo AS brand_logo FROM catalog_models m
                JOIN catalog_brands b ON b.id=m.brand_id WHERE m.id=?''',(model_id,)).fetchone()
        return self.model_row(row) if row else default

    def __contains__(self,model_id):
        return self.get(model_id) is not None

    def __getitem__(self,model_id):
        row=self.get(model_id)
        if row is None:raise KeyError(model_id)
        return row

    def items(self):
        return [(row['id'],row) for row in self.models(public=False)]

    def enabled(self,model_id):
        model=self.get(model_id)
        return bool(model and model['active'] and model['brandActive'])

    def brands(self,public=True):
        with self.auth.connect() as db:
            sql='''SELECT b.*,(SELECT count(*) FROM catalog_models m WHERE m.brand_id=b.id AND m.active=1) AS model_count
                FROM catalog_brands b'''+(' WHERE b.active=1' if public else '')+' ORDER BY b.name'
            return [{**dict(row),'active':bool(row['active'])} for row in db.execute(sql)]

    def brand(self,brand_id,public=True):
        row=next((r for r in self.brands(public) if r['id']==brand_id),None)
        if not row:raise BuyerError(404,'Brand not found.')
        return {**row,'models':self.models(public,brand_id)}

    @staticmethod
    def admin(db,user):
        if not db.execute("SELECT 1 FROM users WHERE id=? AND role='PLATFORM_ADMIN' AND status='ACTIVE'",(user['id'],)).fetchone():
            raise BuyerError(403,'Platform administrator permission required.')

    @staticmethod
    def audit(db,user,action,entity_type,entity_id):
        db.execute('INSERT INTO trade_audit(id,actor_user_id,action,entity_type,entity_id,created_at) VALUES (?,?,?,?,?,?)',
            ('AUD-'+uuid.uuid4().hex[:16].upper(),user['id'],action,entity_type,entity_id,int(time.time())))

    def save_brand(self,user,body,brand_id=None):
        name=text(body.get('name'),'brand name',160,True)
        ident=brand_id or slug(body.get('id'))
        active=body.get('active',True)
        if type(active) is not bool:raise BuyerError(400,'Invalid active status.')
        fields=(name,text(body.get('country'),'country',120),media_url(body.get('logo')),
            text(body.get('overview'),'overview',2000),int(active),int(time.time()))
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE');self.admin(db,user)
            existing=db.execute('SELECT id FROM catalog_brands WHERE id=?',(ident,)).fetchone()
            if brand_id and not existing:raise BuyerError(404,'Brand not found.')
            if not brand_id and existing:raise BuyerError(409,'This brand slug already exists.')
            if existing:
                db.execute('UPDATE catalog_brands SET name=?,country=?,logo=?,overview=?,active=?,updated_at=? WHERE id=?',(*fields,ident))
            else:
                db.execute('INSERT INTO catalog_brands(name,country,logo,overview,active,updated_at,id,created_at) VALUES (?,?,?,?,?,?,?,?)',(*fields,ident,fields[-1]))
            self.audit(db,user,'BRAND_UPDATED' if existing else 'BRAND_CREATED','brand',ident)
        return self.brand(ident,public=False)

    def save_model(self,user,body,model_id=None):
        ident=model_id or slug(body.get('id'))
        brand=text(body.get('brandId'),'brand',100,True);name=text(body.get('model'),'model',160,True)
        year=body.get('year');active=body.get('active',True)
        if year is not None and (isinstance(year,bool) or not isinstance(year,int) or not 1900<=year<=2100):raise BuyerError(400,'Invalid model year.')
        if type(active) is not bool:raise BuyerError(400,'Invalid active status.')
        specifications=body.get('specifications',{})
        if not isinstance(specifications,dict) or set(specifications)-{'dimensions','power','battery','range'}:
            raise BuyerError(400,'Invalid specification fields.')
        specs={key:text(value,key,200) for key,value in specifications.items()}
        fields=(brand,name,year,text(body.get('bodyType'),'body type',80),text(body.get('energy'),'energy',80),
            media_url(body.get('image')),text(body.get('description'),'description',2000),
            json.dumps(specs),int(active),int(time.time()))
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE');self.admin(db,user)
            if not db.execute('SELECT 1 FROM catalog_brands WHERE id=?',(brand,)).fetchone():raise BuyerError(400,'Brand not found.')
            existing=db.execute('SELECT id FROM catalog_models WHERE id=?',(ident,)).fetchone()
            if model_id and not existing:raise BuyerError(404,'Model not found.')
            if not model_id and existing:raise BuyerError(409,'This model slug already exists.')
            if db.execute('SELECT 1 FROM catalog_models WHERE brand_id=? AND name=? COLLATE NOCASE AND model_year IS ? AND id!=?',(brand,name,year,ident)).fetchone():
                raise BuyerError(409,'This brand, model and year already exist.')
            if existing:
                db.execute('UPDATE catalog_models SET brand_id=?,name=?,model_year=?,body_type=?,energy=?,image=?,description=?,specifications=?,active=?,updated_at=? WHERE id=?',(*fields,ident))
            else:
                db.execute('INSERT INTO catalog_models(brand_id,name,model_year,body_type,energy,image,description,specifications,active,updated_at,id,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(*fields,ident,fields[-1]))
            self.audit(db,user,'MODEL_UPDATED' if existing else 'MODEL_CREATED','model',ident)
        return self.get(ident)
