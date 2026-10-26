import hmac
import secrets
from uuid import UUID, uuid4

from backend.db.models import page_result, safe_row
from backend.errors import PlatformError, invalid, missing
from backend.identity.auth import digest

KEY_FIELDS = ('id','user_id','label','prefix','created_at','revoked_at')


class ApiKeys:
    def __init__(self, db, identity):
        self.db, self.identity = db, identity

    def owner(self, c, principal, user_id):
        if principal.role != 'admin' and principal.user_id != user_id:
            raise missing()
        if not c.execute('SELECT id FROM users WHERE id=%s', (user_id,)).fetchone():
            raise missing()

    def issue(self, principal, user_id, label):
        if not isinstance(label,str) or not label.strip() or len(label)>100:
            raise invalid()
        key_id = uuid4()
        raw = f'ugw_{key_id}_{secrets.token_urlsafe(32)}'
        with self.db.transaction() as c:
            self.owner(c,principal,user_id)
            row = c.execute('INSERT INTO api_keys(id,user_id,label,prefix,token_hash) VALUES(%s,%s,%s,%s,%s) RETURNING *', (key_id,user_id,label,f'ugw_{str(key_id)[:8]}',digest(raw))).fetchone()
        return {**safe_row(row,KEY_FIELDS),'raw_key':raw}

    def list(self, principal, user_id, page, per_page):
        with self.db.transaction() as c:
            self.owner(c,principal,user_id)
            rows = c.execute('SELECT * FROM api_keys WHERE user_id=%s ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s', (user_id,per_page+1,(page-1)*per_page)).fetchall()
        return page_result([safe_row(r,KEY_FIELDS) for r in rows],page,per_page)

    def revoke(self, principal, user_id, key_id):
        with self.db.transaction() as c:
            self.owner(c,principal,user_id)
            if not c.execute('UPDATE api_keys SET revoked_at=coalesce(revoked_at,now()) WHERE id=%s AND user_id=%s RETURNING id', (key_id,user_id)).fetchone():
                raise missing()

    def validate(self, raw):
        if not isinstance(raw,str) or len(raw)>256:
            raise PlatformError(401,'UNAUTHENTICATED','Authentication is required.')
        try:
            parts = raw.split('_', 2)
            if len(parts)!=3 or parts[0]!='ugw':
                raise ValueError()
            key_id = UUID(parts[1])
        except ValueError:
            raise PlatformError(401,'UNAUTHENTICATED','Authentication is required.') from None
        with self.db.transaction() as c:
            row = c.execute('SELECT k.*,k.id AS key_id,u.role FROM api_keys k JOIN users u ON u.id=k.user_id WHERE k.id=%s', (key_id,)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'],digest(raw)):
            raise PlatformError(401,'UNAUTHENTICATED','Authentication is required.')
        principal = self.identity.principal(row,'api_key',key_id)
        if row['revoked_at']:
            raise PlatformError(401,'KEY_REVOKED','This key has been revoked.',principal)
        return self.identity.revalidate(principal)
