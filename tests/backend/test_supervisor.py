import asyncio
from contextlib import contextmanager

import psycopg

from backend.errors import unavailable
from scripts.m5.harness import monitor_owner


def test_supervisor_waits_for_database_without_reacquiring_old_owner():
    restarts = []

    class Database:
        checks = 0
        connections = 0

        def check_owner(self):
            self.checks += 1
            raise unavailable()

        @contextmanager
        def connect(self):
            self.connections += 1
            if self.connections <= 2:
                assert not restarts
                raise psycopg.OperationalError('Controlled test outage.')
            yield self

        def execute(self, statement):
            assert statement == 'SELECT 1'

    db = Database()

    async def check():
        await asyncio.wait_for(monitor_owner(db, restart=restarts.append, interval=0.001), 2)

    asyncio.run(check())
    assert db.checks == 1
    assert db.connections == 3
    assert restarts == [75]
