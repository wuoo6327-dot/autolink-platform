"""Email invitations add company-scoped access only after verified acceptance."""
import time
import uuid
from buyer_service import BuyerError
from platform_service import PlatformService
from business_mail import BusinessMailer
from email_auth import EmailError, normalized_email


def identity(prefix):
    return prefix + '-' + uuid.uuid4().hex[:16].upper()


class SupplierTeam:
    def __init__(self, auth):
        self.auth = auth
        with auth.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS supplier_team_members (
                    supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    user_id TEXT NOT NULL REFERENCES users(id), role TEXT NOT NULL DEFAULT 'SALES',
                    status TEXT NOT NULL DEFAULT 'ACTIVE', joined_at INTEGER NOT NULL,
                    removed_at INTEGER, PRIMARY KEY(supplier_id,user_id)
                );
                CREATE INDEX IF NOT EXISTS supplier_team_user ON supplier_team_members(user_id,status);
                CREATE TABLE IF NOT EXISTS supplier_team_invites (
                    id TEXT PRIMARY KEY, supplier_id TEXT NOT NULL REFERENCES supplier_profiles(user_id),
                    email TEXT NOT NULL, invited_by TEXT NOT NULL REFERENCES users(id),
                    status TEXT NOT NULL DEFAULT 'PENDING', created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL, accepted_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS supplier_invites_recipient ON supplier_team_invites(email,status,expires_at);
                CREATE INDEX IF NOT EXISTS supplier_invites_company_time ON supplier_team_invites(supplier_id,created_at);
                CREATE INDEX IF NOT EXISTS supplier_invites_email_time ON supplier_team_invites(email,created_at);
            ''')

    @staticmethod
    def actor(principal):
        return principal.get('actor_user_id', principal['id'])

    @staticmethod
    def owner(principal):
        if principal.get('supplier_role', 'OWNER') != 'OWNER':
            raise BuyerError(403, 'Only the company owner may perform this operation.')

    def active_owner(self, db, principal, *, allow_test=False):
        self.owner(principal)
        if self.actor(principal) != principal['id'] or not db.execute('''SELECT 1 FROM users u
            JOIN supplier_applications a ON a.supplier_id=u.id WHERE u.id=?
            AND u.status='ACTIVE' AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL
            AND u.role IN ('BUYER','MERCHANT','SUPPLIER') AND a.status='APPROVED'
            AND (? OR u.is_test_workspace=0) ''',
            (principal['id'], int(allow_test))).fetchone():
            raise BuyerError(403, 'An active approved company owner is required.')

    @staticmethod
    def audit(db, actor, company, action, entity):
        db.execute('INSERT INTO trade_audit VALUES (?,?,?,?,?,?,?,?)',
                   (identity('AUD'), actor, company, action, 'team', entity, int(time.time()), ''))

    def contexts(self, user):
        if not user['email_verified_at'] or user['role'] not in ('BUYER', 'MERCHANT', 'SUPPLIER'):
            raise BuyerError(403, 'A verified business account is required.')
        with self.auth.connect() as db:
            actor = db.execute("""SELECT is_test_workspace FROM users WHERE id=? AND status='ACTIVE'
                AND deleted_at IS NULL AND email_verified_at IS NOT NULL
                AND role IN ('BUYER','MERCHANT','SUPPLIER')""", (user['id'],)).fetchone()
            if not actor:
                raise BuyerError(403, 'A verified business account is required.')
            own = db.execute('SELECT status FROM supplier_applications WHERE supplier_id=?', (user['id'],)).fetchone()
            result = [{'supplier_id': user['id'], 'company_name': user['company_name'] or user['display_name'],
                       'role': 'OWNER', 'status': own['status'] if own else 'DRAFT'}]
            result += [dict(row) for row in db.execute('''SELECT m.supplier_id,u.company_name,
                m.role,a.status FROM supplier_team_members m JOIN users u ON u.id=m.supplier_id
                JOIN supplier_applications a ON a.supplier_id=m.supplier_id
                WHERE m.user_id=? AND m.status='ACTIVE' AND u.status='ACTIVE' AND a.status='APPROVED'
                AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL AND u.is_test_workspace=0
                AND u.role IN ('BUYER','MERCHANT','SUPPLIER')
                AND ?=0
                ORDER BY m.joined_at''', (user['id'], actor['is_test_workspace']))]
        return result

    def principal(self, user, company=None, approved=False):
        choices = self.contexts(user)
        selected = next((row for row in choices if row['supplier_id'] == (company or user['id'])), None)
        if not selected:
            raise BuyerError(404, 'Supplier workspace not found.')
        if approved and selected['status'] != 'APPROVED':
            raise BuyerError(403, 'Supplier approval required.')
        return {**dict(user), 'id': selected['supplier_id'], 'actor_user_id': user['id'],
                'supplier_role': selected['role'], 'company_name': selected['company_name']}

    def members(self, supplier):
        with self.auth.connect() as db:
            owner = db.execute('SELECT id AS user_id,display_name,email FROM users WHERE id=?', (supplier['id'],)).fetchone()
            result = [{**dict(owner), 'role': 'OWNER', 'status': 'ACTIVE'}]
            result += [dict(row) for row in db.execute('''SELECT m.user_id,m.role,m.status,m.joined_at,
                u.display_name,u.email FROM supplier_team_members m JOIN users u ON u.id=m.user_id
                WHERE m.supplier_id=? AND m.status='ACTIVE' AND u.status='ACTIVE' ORDER BY m.joined_at''',
                (supplier['id'],))]
        return result

    def invitations(self, user):
        with self.auth.connect() as db:
            return [dict(row) for row in db.execute('''SELECT i.id,i.supplier_id,u.company_name,i.created_at,i.expires_at
                FROM supplier_team_invites i JOIN users u ON u.id=i.supplier_id
                JOIN supplier_applications a ON a.supplier_id=i.supplier_id
                WHERE i.email=? AND i.status='PENDING' AND i.expires_at>? AND u.status='ACTIVE'
                AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL AND u.is_test_workspace=0
                AND u.role IN ('BUYER','MERCHANT','SUPPLIER') AND a.status='APPROVED'
                AND EXISTS (SELECT 1 FROM users recipient WHERE recipient.id=? AND recipient.email=i.email
                    AND recipient.status='ACTIVE' AND recipient.deleted_at IS NULL AND recipient.is_test_workspace=0
                    AND recipient.email_verified_at IS NOT NULL AND recipient.role IN ('BUYER','MERCHANT','SUPPLIER'))
                ORDER BY i.created_at DESC''', (user['email'], int(time.time()), user['id']))]

    def team(self, supplier):
        self.owner(supplier)
        with self.auth.connect() as db:
            invitations = [dict(row) for row in db.execute('''SELECT id,email,status,created_at,expires_at
                FROM supplier_team_invites WHERE supplier_id=? AND status='PENDING' AND expires_at>?
                ORDER BY created_at DESC''', (supplier['id'], int(time.time())))]
        return {'members': self.members(supplier), 'invitations': invitations}

    def invite(self, supplier, body):
        self.owner(supplier)
        if set(body) != {'email'}:
            raise BuyerError(400, 'Invalid invitation fields.')
        try:
            email = normalized_email(body.get('email'))
        except EmailError as exc:
            raise BuyerError(400, 'Invalid email address.') from exc
        now = int(time.time()); invitation = identity('INV')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.active_owner(db, supplier)
            owner_email = db.execute('SELECT email FROM users WHERE id=?', (supplier['id'],)).fetchone()[0]
            if email == owner_email:
                raise BuyerError(400, 'You cannot invite your own account.')
            recipient = db.execute("SELECT id FROM users WHERE email=? AND status='ACTIVE' AND deleted_at IS NULL AND email_verified_at IS NOT NULL AND role IN ('BUYER','MERCHANT','SUPPLIER')", (email,)).fetchone()
            if recipient and db.execute("SELECT 1 FROM supplier_team_members WHERE supplier_id=? AND user_id=? AND status='ACTIVE'", (supplier['id'], recipient['id'])).fetchone():
                raise BuyerError(409, 'This account is already a team member.')
            if db.execute("SELECT 1 FROM supplier_team_invites WHERE supplier_id=? AND email=? AND status='PENDING' AND expires_at>?", (supplier['id'], email, now)).fetchone():
                raise BuyerError(409, 'A pending invitation already exists.')
            if db.execute('SELECT count(*) FROM supplier_team_invites WHERE supplier_id=? AND created_at>?', (supplier['id'], now-3600)).fetchone()[0] >= 10:
                raise BuyerError(429, 'Team invitation limit reached.')
            if db.execute('SELECT count(*) FROM supplier_team_invites WHERE email=? AND created_at>?', (email,now-86400)).fetchone()[0] >= 5:
                raise BuyerError(429, 'Team invitation limit reached.')
            db.execute('INSERT INTO supplier_team_invites(id,supplier_id,email,invited_by,created_at,expires_at) VALUES (?,?,?,?,?,?)',
                       (invitation, supplier['id'], email, self.actor(supplier), now, now+7*86400))
            if recipient:
                PlatformService.notify(db, recipient['id'], 'TEAM_INVITED', invitation, '/supplier/team')
            else:
                BusinessMailer.enqueue_invitation(db, supplier['id'], invitation)
            self.audit(db, self.actor(supplier), supplier['id'], 'TEAM_INVITED', invitation)
        return {'id': invitation, 'status': 'PENDING'}

    def accept(self, user, invitation):
        if not user['email_verified_at'] or user['role'] not in ('BUYER', 'MERCHANT', 'SUPPLIER'):
            raise BuyerError(403, 'Verify your account before accepting a team invitation.')
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute("SELECT email FROM users WHERE id=? AND status='ACTIVE' AND deleted_at IS NULL AND is_test_workspace=0 AND email_verified_at IS NOT NULL AND role IN ('BUYER','MERCHANT','SUPPLIER')", (user['id'],)).fetchone()
            if not current or current['email'] != user['email']:
                raise BuyerError(403, 'Verify your account before accepting a team invitation.')
            row = db.execute('''SELECT i.* FROM supplier_team_invites i
                JOIN users u ON u.id=i.supplier_id JOIN supplier_applications a ON a.supplier_id=i.supplier_id
                WHERE i.id=? AND i.email=? AND i.status='PENDING' AND i.expires_at>?
                AND u.status='ACTIVE' AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL AND u.is_test_workspace=0
                AND u.role IN ('BUYER','MERCHANT','SUPPLIER') AND a.status='APPROVED' ''', (invitation, current['email'], now)).fetchone()
            if not row:
                raise BuyerError(404, 'Invitation not found or expired.')
            db.execute('''INSERT INTO supplier_team_members(supplier_id,user_id,joined_at) VALUES (?,?,?)
                ON CONFLICT(supplier_id,user_id) DO UPDATE SET status='ACTIVE',joined_at=excluded.joined_at,removed_at=NULL''',
                (row['supplier_id'], user['id'], now))
            db.execute("UPDATE supplier_team_invites SET status='ACCEPTED',accepted_at=? WHERE id=?", (now, invitation))
            PlatformService.notify(db, row['supplier_id'], 'TEAM_JOINED', user['id'], '/supplier/team')
            self.audit(db, user['id'], row['supplier_id'], 'TEAM_JOINED', user['id'])
        return {'supplier_id': row['supplier_id'], 'role': 'SALES'}

    def cancel(self, supplier, invitation):
        self.owner(supplier)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.active_owner(db, supplier)
            result = db.execute("UPDATE supplier_team_invites SET status='CANCELLED' WHERE id=? AND supplier_id=? AND status='PENDING'", (invitation, supplier['id']))
            if not result.rowcount:
                raise BuyerError(404, 'Invitation not found.')
            self.audit(db, self.actor(supplier), supplier['id'], 'TEAM_INVITATION_CANCELLED', invitation)
        return {'id': invitation, 'status': 'CANCELLED'}

    def remove(self, supplier, member):
        self.owner(supplier)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.active_owner(db, supplier)
            result = db.execute("UPDATE supplier_team_members SET status='REMOVED',removed_at=? WHERE supplier_id=? AND user_id=? AND status='ACTIVE'", (int(time.time()), supplier['id'], member))
            if not result.rowcount:
                raise BuyerError(404, 'Team member not found.')
            db.execute('UPDATE buyer_inquiries SET assigned_to=NULL WHERE supplier_id=? AND assigned_to=?', (supplier['id'], member))
            db.execute('UPDATE supplier_crm SET assigned_to=NULL WHERE supplier_id=? AND assigned_to=?', (supplier['id'], member))
            self.audit(db, self.actor(supplier), supplier['id'], 'TEAM_REMOVED', member)
        return {'user_id': member, 'status': 'REMOVED'}

    def assign(self, supplier, buyer, body):
        self.owner(supplier)
        member = body.get('userId') or None
        if member is not None and not isinstance(member, str):
            raise BuyerError(400, 'Invalid team member.')
        now = int(time.time())
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.active_owner(db, supplier)
            relationship = db.execute('SELECT 1 FROM supplier_crm WHERE supplier_id=? AND buyer_id=?', (supplier['id'], buyer)).fetchone()
            if not relationship:
                raise BuyerError(404, 'Buyer relationship not found.')
            if member and member != supplier['id'] and not db.execute('''SELECT 1 FROM supplier_team_members m
                JOIN users u ON u.id=m.user_id WHERE m.supplier_id=? AND m.user_id=? AND m.status='ACTIVE'
                AND u.status='ACTIVE' AND u.deleted_at IS NULL AND u.email_verified_at IS NOT NULL
                AND u.role IN ('BUYER','MERCHANT','SUPPLIER')''', (supplier['id'], member)).fetchone():
                raise BuyerError(404, 'Active team member not found.')
            db.execute('UPDATE supplier_crm SET assigned_to=?,updated_at=? WHERE supplier_id=? AND buyer_id=?', (member, now, supplier['id'], buyer))
            db.execute('UPDATE buyer_inquiries SET assigned_to=?,updated_at=? WHERE supplier_id=? AND buyer_id=?', (member, now, supplier['id'], buyer))
            if member and member != supplier['id']:
                PlatformService.notify(db, member, 'BUYER_ASSIGNED', buyer, '/supplier/buyers/'+buyer+'?company='+supplier['id'])
            self.audit(db, self.actor(supplier), supplier['id'], 'BUYER_ASSIGNED', buyer)
        return {'buyer_id': buyer, 'assigned_to': member}

    def check_assignment(self, db, supplier, inquiry=None, buyer=None):
        """Recheck membership under each mutation's database lock."""
        if supplier.get('supplier_role', 'OWNER') == 'OWNER':
            return
        actor = self.actor(supplier)
        if not db.execute('''SELECT 1 FROM supplier_team_members m JOIN users u ON u.id=m.user_id
            JOIN users o ON o.id=m.supplier_id JOIN supplier_applications a ON a.supplier_id=m.supplier_id
            WHERE m.supplier_id=? AND m.user_id=? AND m.status='ACTIVE' AND u.status='ACTIVE'
            AND u.email_verified_at IS NOT NULL AND u.deleted_at IS NULL AND u.is_test_workspace=0
            AND u.role IN ('BUYER','MERCHANT','SUPPLIER') AND o.status='ACTIVE'
            AND o.deleted_at IS NULL AND o.email_verified_at IS NOT NULL AND o.is_test_workspace=0
            AND o.role IN ('BUYER','MERCHANT','SUPPLIER') AND a.status='APPROVED' ''', (supplier['id'], actor)).fetchone():
            raise BuyerError(403, 'Supplier membership is no longer active.')
        if not inquiry and not buyer:
            return
        if inquiry:
            visible = db.execute('SELECT 1 FROM buyer_inquiries WHERE id=? AND supplier_id=? AND assigned_to=?', (inquiry, supplier['id'], actor)).fetchone()
        else:
            visible = db.execute('SELECT 1 FROM supplier_crm WHERE buyer_id=? AND supplier_id=? AND assigned_to=?', (buyer, supplier['id'], actor)).fetchone()
        if not visible:
            raise BuyerError(404, 'Assigned business record not found.')
