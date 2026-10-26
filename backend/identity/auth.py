import base64
import hashlib
import hmac
import re
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import BoundedSemaphore
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type

from backend.db.models import safe_row
from backend.errors import PlatformError, invalid, unavailable

USER_FIELDS = ('id', 'email', 'role', 'created_at')
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                                hash_len=32, salt_len=16, type=Type.ID)
PASSWORD_SLOTS = BoundedSemaphore(2)
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_value(token):
    value = hmac.new(token.encode(), b'urumi-csrf-v1', hashlib.sha256).digest()
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def email_value(value):
    if not isinstance(value, str):
        raise invalid()
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&\'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}', value):
        raise invalid()
    return value


def password_value(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise invalid()
    try:
        if len(value.encode('utf-8')) > 512:
            raise invalid()
    except UnicodeEncodeError:
        raise invalid() from None
    return value


@contextmanager
def password_slot():
    if not PASSWORD_SLOTS.acquire(timeout=2):
        raise unavailable()
    try:
        yield
    finally:
        PASSWORD_SLOTS.release()


def hash_password(value):
    with password_slot():
        return PASSWORD_HASHER.hash(password_value(value))


@dataclass(frozen=True)
class Principal:
    user_id: object
    role: str
    auth_source: str
    key_id: object = None
    _handle: object = field(default=None, repr=False, compare=False)
    _proof: object = field(default=None, repr=False, compare=False)


class Identity:
    def __init__(self, db):
        self.db = db
        self._proof = object()

    def principal(self, row, source, handle):
        return Principal(row['user_id'], row['role'], source,
                         row.get('key_id'), handle, self._proof)

    def bootstrap(self, email, password):
        email, password_hash = email_value(email), hash_password(password)
        with self.db.transaction() as c:
            c.execute('SELECT pg_advisory_xact_lock(51004)')
            existing = c.execute("SELECT * FROM users WHERE role='admin' ORDER BY created_at,id LIMIT 1").fetchone()
            if existing:
                return safe_row(existing, USER_FIELDS)
            row = c.execute("INSERT INTO users(id,email,role,password_hash) VALUES(%s,%s,'admin',%s) RETURNING *",
                            (uuid4(), email, password_hash)).fetchone()
            return safe_row(row, USER_FIELDS)

    def login(self, email, password, old_token=None):
        email = email_value(email)
        password_value(password)
        with self.db.transaction() as c:
            user = c.execute('SELECT * FROM users WHERE email=%s', (email,)).fetchone()
        with password_slot():
            try:
                valid = PASSWORD_HASHER.verify(user['password_hash'] if user else DUMMY_HASH, password)
            except VerificationError:
                valid = False
        if not user or not valid:
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        token = secrets.token_urlsafe(32)
        csrf = csrf_value(token)
        with self.db.transaction() as c:
            if old_token:
                c.execute('UPDATE sessions SET revoked_at=now() WHERE token_hash=%s AND revoked_at IS NULL',
                          (digest(old_token),))
            c.execute("INSERT INTO sessions(id,user_id,token_hash,csrf_hash,expires_at) VALUES(%s,%s,%s,%s,now()+interval '8 hours')",
                      (uuid4(), user['id'], digest(token), digest(csrf)))
        return {'user': safe_row(user, USER_FIELDS), 'csrf_token': csrf}, token

    def session(self, token):
        if not isinstance(token, str) or len(token) > 256:
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        with self.db.transaction() as c:
            row = c.execute('SELECT s.id AS session_id,s.user_id,u.role,s.token_hash FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>now()',
                            (digest(token),)).fetchone()
        if not row or not hmac.compare_digest(row['token_hash'], digest(token)):
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        return self.principal(row, 'session', row['session_id'])

    def revalidate(self, principal):
        if not isinstance(principal, Principal) or principal._proof is not self._proof:
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        self.db.check_owner()
        with self.db.transaction() as c:
            if principal.auth_source == 'session':
                row = c.execute('SELECT s.user_id,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.id=%s AND s.revoked_at IS NULL AND s.expires_at>now()',
                                (principal._handle,)).fetchone()
            else:
                row = c.execute('SELECT k.user_id,u.role,k.id AS key_id FROM api_keys k JOIN users u ON u.id=k.user_id WHERE k.id=%s AND k.revoked_at IS NULL',
                                (principal._handle,)).fetchone()
        if not row or row['user_id'] != principal.user_id:
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        return self.principal(row, principal.auth_source, principal._handle)

    def check_csrf(self, principal, value):
        if not isinstance(value, str) or len(value)>256:
            raise PlatformError(403, 'REQUEST_REJECTED', 'The request was rejected.')
        with self.db.transaction() as c:
            row = c.execute('SELECT csrf_hash FROM sessions WHERE id=%s', (principal._handle,)).fetchone()
        if not row or not hmac.compare_digest(row['csrf_hash'], digest(value)):
            raise PlatformError(403, 'REQUEST_REJECTED', 'The request was rejected.')

    def me(self, principal, token):
        with self.db.transaction() as c:
            row = c.execute('SELECT * FROM users WHERE id=%s', (principal.user_id,)).fetchone()
        return {'user': safe_row(row, USER_FIELDS), 'csrf_token': csrf_value(token)}

    def logout(self, principal):
        with self.db.transaction() as c:
            c.execute('UPDATE sessions SET revoked_at=coalesce(revoked_at,now()) WHERE id=%s', (principal._handle,))


def require_admin(principal):
    if principal.role != 'admin':
        raise PlatformError(403, 'FORBIDDEN', 'Admin access is required.')
