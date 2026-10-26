from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from backend.errors import PlatformError, conflict, unavailable


class Database:
    def __init__(self, dsn):
        self.dsn = dsn
        self.run_id = uuid4()
        self.owner = None
        self._owner_guard = Lock()

    def connect(self, autocommit=False):
        return psycopg.connect(self.dsn, connect_timeout=3, autocommit=autocommit,
                               options="-c statement_timeout=5000 -c lock_timeout=2000 -c timezone=UTC",
                               row_factory=dict_row)

    @contextmanager
    def transaction(self):
        try:
            with self.connect() as connection:
                yield connection
        except psycopg.errors.UniqueViolation:
            raise conflict() from None
        except psycopg.Error:
            raise unavailable() from None

    def migrate(self):
        with self.transaction() as c:
            c.execute("SELECT pg_advisory_xact_lock(51001)")
            c.execute("CREATE TABLE IF NOT EXISTS schema_version(version integer PRIMARY KEY)")
            versions = c.execute("SELECT version FROM schema_version ORDER BY version").fetchall()
            current=[r['version'] for r in versions]
            if current not in ([],[1],[1,2],[1,2,3]):
                raise PlatformError(503, "SCHEMA_UNSUPPORTED", "The database schema is unsupported.")
            if not versions:
                c.execute(Path(__file__).with_name("migrations").joinpath("001_initial.sql").read_text())
                c.execute("INSERT INTO schema_version VALUES (1)")
                c.execute("INSERT INTO installation VALUES (%s)", (uuid4(),))
            if 2 not in current:
                c.execute(Path(__file__).with_name('migrations').joinpath('002_canceled_secret_names.sql').read_text())
                c.execute('INSERT INTO schema_version VALUES (2)')
            if 3 not in current:
                c.execute(Path(__file__).with_name('migrations').joinpath('003_builtin_initialization.sql').read_text())
                c.execute('INSERT INTO schema_version VALUES (3)')

    def acquire_owner(self):
        try:
            c = self.connect(autocommit=True)
            if not c.execute("SELECT pg_try_advisory_lock(51002) AS acquired").fetchone()['acquired']:
                c.close()
                raise conflict()
            self.owner = c
        except psycopg.Error:
            raise unavailable() from None

    def check_owner(self):
        with self._owner_guard:
            try:
                if self.owner is None or self.owner.closed:
                    raise unavailable()
                self.owner.execute("SELECT 1")
            except psycopg.Error:
                self.owner.close()
                raise unavailable() from None

    def close(self):
        if self.owner:
            self.owner.close()

    @contextmanager
    def server_lock(self, server_id):
        try:
            with self.connect(autocommit=True) as c:
                acquired = c.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 51003)) AS acquired",
                                     (str(server_id),)).fetchone()['acquired']
                if not acquired:
                    raise conflict()
                yield c
        except psycopg.errors.UniqueViolation:
            raise conflict() from None
        except psycopg.Error:
            raise unavailable() from None
