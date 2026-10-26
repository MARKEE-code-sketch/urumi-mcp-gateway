import json
from pathlib import Path

import psycopg
import pytest

from backend.db.database import Database
from backend.identity.auth import Identity
from backend.identity.members import Members
from backend.identity.api_keys import ApiKeys


@pytest.fixture
def db():
    password=json.loads(Path('.tools/m5/db.json').read_text())['password']
    dsn=psycopg.conninfo.make_conninfo(host='127.0.0.1',port=15435,user='urumi',dbname='urumi',password=password)
    database=Database(dsn)
    database.migrate()
    database.acquire_owner()
    try:
        with database.transaction() as c:
            c.execute('TRUNCATE users,invitations,sessions,api_keys,servers,secret_operations,canceled_secret_names,audit_records CASCADE')
        yield database
    finally:
        database.close()


@pytest.fixture
def identities(db):
    identity=Identity(db)
    admin=identity.bootstrap('admin@example.test','Example password 123!')
    _,token=identity.login('admin@example.test','Example password 123!')
    principal=identity.session(token)
    return identity,Members(db,'http://127.0.0.1:18005'),ApiKeys(db,identity),principal,token,admin
