"""Prove 001 -> 002 preservation in an owned disposable database, never the live DB."""
import json
import os
from pathlib import Path
from uuid import UUID,uuid4

import psycopg
from psycopg import sql

from backend.db.database import Database
from backend.identity.auth import Identity
from backend.identity.api_keys import ApiKeys
from backend.identity.members import Members


def main():
    if os.environ.get('PGDATABASE')!='urumi' or 'urumi-m5-check' not in os.environ.get('PGHOST',''):
        raise RuntimeError('This check requires the isolated M5 PostgreSQL service.')
    settings={'host':os.environ['PGHOST'],'port':os.getenv('PGPORT','5432'),
              'user':os.environ['PGUSER'],'password':os.environ['PGPASSWORD']}
    name='m5_upgrade_'+uuid4().hex
    if not name.startswith('m5_upgrade_') or len(name)!=43:
        raise RuntimeError('Disposable database name guard failed.')
    created=False
    db=None
    try:
        with psycopg.connect(**settings,dbname='postgres',autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            created=True
        db=Database(psycopg.conninfo.make_conninfo(**settings,dbname=name))
        with db.transaction() as c:
            c.execute('CREATE TABLE schema_version(version integer PRIMARY KEY)')
            c.execute(Path('backend/db/migrations/001_initial.sql').read_text())
            c.execute('INSERT INTO schema_version VALUES(1)')
            c.execute('INSERT INTO installation VALUES(%s)',(uuid4(),))
        identity=Identity(db)
        user=identity.bootstrap('upgrade@example.test','Migration fixture password 123!')
        _,old_token=identity.login('upgrade@example.test','Migration fixture password 123!')
        principal=identity.session(old_token)
        keys=ApiKeys(db,identity)
        active=keys.issue(principal,principal.user_id,'active migration fixture')
        revoked=keys.issue(principal,principal.user_id,'revoked migration fixture')
        keys.revoke(principal,principal.user_id,UUID(revoked['id']))
        identity.logout(principal)
        _,active_session=identity.login('upgrade@example.test','Migration fixture password 123!')
        Members(db,'https://gateway.example.test').invite(identity.session(active_session),'pending@example.test','member')
        tables=['installation','users','sessions','api_keys','invitations']
        def snapshot():
            with db.transaction() as c:
                return {table:c.execute(sql.SQL('SELECT * FROM {} ORDER BY id').format(sql.Identifier(table))).fetchall() for table in tables}
        before=snapshot()
        db.migrate()
        if before!=snapshot():
            raise RuntimeError('Migration changed saved identity records.')
        with db.transaction() as c:
            versions=[r['version'] for r in c.execute('SELECT version FROM schema_version ORDER BY version')]
            if versions!=[1,2,3] or c.execute('SELECT count(*) AS n FROM canceled_secret_names').fetchone()['n']!=0:
                raise RuntimeError('Expected migration result was not present.')
        db.migrate()
        if before!=snapshot():
            raise RuntimeError('Repeated migration changed saved identity records.')
        identity.login('upgrade@example.test','Migration fixture password 123!')
        # Only safe flags/counts leave this process; hashes/tokens are compared in memory.
        summary={'check':'M5-01-forward-migration','result':'PASS','from':1,'to':2,
                 'preserved_tables':tables,'password_verified':True,'repeat_preserved':True}
    finally:
        if db:
            db.close()
        if created:
            with psycopg.connect(**settings,dbname='postgres',autocommit=True) as admin:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
    summary['disposable_database_removed']=True
    print(json.dumps(summary))


if __name__=='__main__':
    try:
        main()
    except Exception:
        print('FAIL: disposable migration preservation check failed; sensitive output suppressed.')
        raise SystemExit(1) from None
