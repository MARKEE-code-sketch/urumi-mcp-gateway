"""Contract-compatible in-memory fixtures. These are not M5 integration proof."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock, RLock
from uuid import UUID, uuid4

from backend.errors import PlatformError
from backend.identity.auth import Principal


class Database:
    def __init__(self):
        self.owned = True
        self.locks = {}
        self.guard = Lock()

    def check_owner(self):
        if not self.owned:
            raise PlatformError(503, 'DEPENDENCY_UNAVAILABLE', 'Ownership is unavailable.')

    @contextmanager
    def server_lock(self, server_id):
        with self.guard:
            lock = self.locks.setdefault(server_id, Lock())
        if not lock.acquire(blocking=False):
            raise PlatformError(409, 'CONFLICT', 'Server is busy.')
        try:
            yield
        finally:
            lock.release()


class Identity:
    def __init__(self, db, key_a, key_b, session_a, session_b):
        self.db, self._proof = db, object()
        self.users = [UUID(int=101), UUID(int=102)]
        self.credentials = {}
        for index, (key, session) in enumerate(((key_a, session_a), (key_b, session_b))):
            for value, source in ((key, 'api_key'), (session, 'session')):
                self.credentials[value] = dict(user_id=self.users[index], role='admin' if index == 0 else 'member',
                    auth_source=source, key_id=UUID(int=201+index) if source == 'api_key' else None, active=True)

    def validate(self, raw):
        record = self.credentials.get(raw)
        if not record or record['auth_source'] != 'api_key':
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        principal = self._principal(raw, record)
        if not record['active']:
            raise PlatformError(401, 'KEY_REVOKED', 'This key has been revoked.', principal)
        return self.revalidate(principal)

    def _principal(self, raw, record):
        return Principal(record['user_id'], record['role'], record['auth_source'], record['key_id'], raw, self._proof)

    def session(self, raw):
        record = self.credentials.get(raw)
        if not record or record['auth_source'] != 'session':
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        return self.revalidate(self._principal(raw, record))

    def revalidate(self, principal):
        self.db.check_owner()
        if not isinstance(principal, Principal) or principal._proof is not self._proof:
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        record = self.credentials.get(principal._handle)
        if not record or not record['active'] or principal.user_id != record['user_id']:
            raise PlatformError(401, 'KEY_REVOKED' if principal.auth_source == 'api_key' else 'UNAUTHENTICATED',
                                'Authentication is required.', principal)
        return self._principal(principal._handle, record)


class Registry:
    def __init__(self, db, urls):
        self.db, self.guard = db, RLock()
        self.rows = {UUID(int=301+index): dict(id=UUID(int=301+index), name=mode, slug=mode,
            url=url, enabled=True, version=1, status='Unreachable', status_reason='NOT_CHECKED',
            auth_type=mode, header_name='X-Test-Key' if mode == 'header' else None,
            secret_name=mode if mode != 'none' else None) for index, (mode, url) in enumerate(urls.items())}

    def list_servers(self, enabled_only=False):
        with self.guard:
            return deepcopy([row for row in self.rows.values() if not enabled_only or row['enabled']])

    def get_server(self, server_id):
        with self.guard:
            if server_id not in self.rows:
                raise PlatformError(404, 'NOT_FOUND', 'Server not found.')
            return deepcopy(self.rows[server_id])

    def set_server_status(self, server_id, status, reason=None, *, expected_version=None):
        with self.guard:
            row = self.rows.get(server_id)
            if not row or expected_version is not None and row['version'] != expected_version:
                return False
            row['status'] = status if row['enabled'] else 'Disabled'
            row['status_reason'] = reason if row['enabled'] else None
            return True

    def edit(self, server_id, changes):
        with self.db.server_lock(server_id), self.guard:
            row = self.rows[server_id]
            row.update(changes)
            row['version'] += 1
            row['status'] = 'Unreachable' if row['enabled'] else 'Disabled'


class Secrets:
    def __init__(self, values):
        self.values = values

    def resolve(self, name, server_id):
        return self.values[name]


class Audit:
    def __init__(self, db, identity):
        self.db, self.identity = db, identity
        self.guard, self.records = RLock(), {}
        self.fail_begin = self.fail_finalize = False

    def begin_attempt(self, request_id, principal, server_id, public_tool_name, upstream_tool_name=None):
        self.db.check_owner()
        if not isinstance(request_id, UUID):
            raise ValueError('Request identity must be a UUID.')
        if self.fail_begin:
            raise PlatformError(503, 'AUDIT_UNAVAILABLE', 'Activity is unavailable.')
        if principal is not None and principal._proof is not self.identity._proof:
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        audit_id = uuid4()
        with self.guard:
            self.records[audit_id] = dict(audit_id=str(audit_id), request_id=str(request_id),
                user_id=str(principal.user_id) if principal else None,
                key_id=str(principal.key_id) if principal and principal.key_id else None,
                auth_source=principal.auth_source if principal else None,
                server_id=str(server_id) if server_id else None, public_tool_name=public_tool_name,
                upstream_tool_name=upstream_tool_name, outcome='running', duration_ms=None, error_code=None,
                started_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'), finished_at=None,
                error_summary=None)
        return audit_id

    def finalize_attempt(self, audit_id, outcome, duration_ms=None, error_code=None):
        self.db.check_owner()
        if self.fail_finalize:
            raise PlatformError(503, 'AUDIT_FINALIZATION_FAILED', 'Activity finalization is unavailable.')
        with self.guard:
            row = self.records[audit_id]
            if row['outcome'] != 'running':
                raise PlatformError(409, 'CONFLICT', 'Attempt is already final.')
            row.update(outcome=outcome, duration_ms=duration_ms, error_code=error_code,
                       finished_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                       error_summary='The fixture attempt did not succeed.' if error_code else None)

    def record_denial(self, request_id, principal, server_id, tool_name, code):
        with self.guard:
            value = self.begin_attempt(request_id, principal, server_id, tool_name)
            self.finalize_attempt(value, 'denied', 0, code)
            return value
