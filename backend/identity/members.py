import secrets
from uuid import uuid4

from backend.db.models import page_result, safe_row
from backend.errors import conflict, invalid
from backend.identity.auth import USER_FIELDS, digest, email_value, hash_password, require_admin


class Members:
    def __init__(self, db, origin):
        self.db, self.origin = db, origin

    def invite(self, principal, email, role):
        require_admin(principal)
        if role != 'member':
            raise invalid()
        email, token, invite_id = email_value(email), secrets.token_urlsafe(32), uuid4()
        with self.db.transaction() as c:
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,51005))', (email,))
            if c.execute('SELECT id FROM users WHERE email=%s', (email,)).fetchone() or c.execute('SELECT id FROM invitations WHERE email=%s AND consumed_at IS NULL AND expires_at>now()', (email,)).fetchone():
                raise conflict()
            row = c.execute("INSERT INTO invitations(id,email,token_hash,expires_at) VALUES(%s,%s,%s,now()+interval '24 hours') RETURNING *", (invite_id,email,digest(token))).fetchone()
        result = safe_row(row, ('id','expires_at'))
        result['invite_url'] = self.origin + '/invite#token=' + token
        return result

    def redeem(self, token, password):
        if not isinstance(token,str) or not 20 <= len(token) <= 256:
            raise invalid()
        password_hash = hash_password(password)
        with self.db.transaction() as c:
            row = c.execute('SELECT *,expires_at<=now() AS expired FROM invitations WHERE token_hash=%s FOR UPDATE', (digest(token),)).fetchone()
            if not row:
                raise invalid()
            if row['consumed_at']:
                raise conflict()
            if row['expired']:
                raise invalid()
            user = c.execute("INSERT INTO users(id,email,role,password_hash) VALUES(%s,%s,'member',%s) RETURNING *", (uuid4(),row['email'],password_hash)).fetchone()
            c.execute('UPDATE invitations SET consumed_at=now() WHERE id=%s', (row['id'],))
        return {'user':safe_row(user,USER_FIELDS)}

    def list(self, principal, page, per_page):
        require_admin(principal)
        with self.db.transaction() as c:
            rows = c.execute('SELECT * FROM users ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s', (per_page+1,(page-1)*per_page)).fetchall()
        return page_result([safe_row(r,USER_FIELDS) for r in rows],page,per_page)
