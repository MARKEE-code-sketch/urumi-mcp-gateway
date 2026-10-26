"""Opt-in real PostgreSQL checks in a unique disposable schema.

The runner supplies URUMI_M10_TEST_DSN privately. No historical inputs are read.
"""
from pathlib import Path
import asyncio
import os
from uuid import uuid4

import psycopg
from psycopg import sql
import httpx
from mcp import types
import pytest

from backend.db.database import Database
from backend.orchestrator import initialize_woocommerce
from backend.identity.auth import Identity


WOO = 'http://test-woocommerce-mcp.test.svc.cluster.local:8000/mcp'


@pytest.fixture
def database():
    dsn = os.getenv('URUMI_M10_TEST_DSN')
    if not dsn:
        pytest.skip('Explicit disposable PostgreSQL DSN not supplied.')
    settings = psycopg.conninfo.conninfo_to_dict(dsn)
    if settings.get('host') not in ('127.0.0.1','localhost') or not settings.get('dbname','').startswith('urumi_m10_test'):
        pytest.fail('Only an explicit loopback urumi_m10_test database is allowed.')
    schema = 'm10_' + uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))

    class IsolatedDatabase(Database):
        def connect(self,autocommit=False):
            connection = super().connect(autocommit)
            connection.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            if not autocommit:
                connection.commit()
            return connection

    db = IsolatedDatabase(dsn)
    try:
        yield db
    finally:
        db.close()
        with psycopg.connect(dsn,autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def ready(db):
    db.migrate()
    db.acquire_owner()


def test_new_schema_migrates_idempotently_and_refuses_second_owner(database):
    ready(database)
    database.migrate()
    with database.transaction() as connection:
        assert [r['version'] for r in connection.execute('SELECT version FROM schema_version ORDER BY version')] == [1,2,3]
        assert connection.execute('SELECT count(*) AS n FROM installation').fetchone()['n'] == 1
    contender = Database(database.dsn)
    try:
        with pytest.raises(Exception):
            contender.acquire_owner()
    finally:
        contender.close()


def test_schema_two_upgrade_preserves_existing_installation(database):
    owner = uuid4()
    with database.transaction() as connection:
        connection.execute('CREATE TABLE schema_version(version integer PRIMARY KEY)')
        root = Path('backend/db/migrations')
        connection.execute((root/'001_initial.sql').read_text())
        connection.execute((root/'002_canceled_secret_names.sql').read_text())
        connection.execute('INSERT INTO schema_version VALUES(1),(2)')
        connection.execute('INSERT INTO installation VALUES(%s)',(owner,))
    ready(database)
    with database.transaction() as connection:
        assert connection.execute('SELECT id FROM installation').fetchone()['id'] == owner
        assert [r['version'] for r in connection.execute('SELECT version FROM schema_version ORDER BY version')] == [1,2,3]


def test_woo_initialization_preserves_edits_disable_and_deletion_across_restart(database):
    ready(database)
    initialize_woocommerce(database,WOO,[WOO])
    with database.transaction() as connection:
        initial = connection.execute("SELECT * FROM servers WHERE slug='woocommerce'").fetchone()
        assert initial['enabled'] and initial['status_reason'] == 'NOT_CHECKED' and initial['auth_type'] == 'none'
        connection.execute("UPDATE servers SET name='Edited',enabled=false,status='Disabled',url=%s WHERE id=%s",(WOO+'/edited',initial['id']))
    initialize_woocommerce(database,WOO,[WOO])
    with database.transaction() as connection:
        edited = connection.execute('SELECT * FROM servers').fetchone()
        assert edited['id'] == initial['id'] and edited['name'] == 'Edited' and not edited['enabled']
        assert edited['url'] == WOO+'/edited'
        connection.execute('DELETE FROM servers WHERE id=%s',(initial['id'],))
    database.close()
    database.acquire_owner()
    initialize_woocommerce(database,WOO,[WOO])
    with database.transaction() as connection:
        assert connection.execute('SELECT count(*) AS n FROM servers').fetchone()['n'] == 0
        assert connection.execute('SELECT server_id FROM builtin_initializations').fetchone()['server_id'] == initial['id']


def test_existing_woocommerce_row_is_adopted_without_mutation(database):
    ready(database)
    server_id = uuid4()
    with database.transaction() as connection:
        connection.execute("""INSERT INTO servers(id,name,slug,url,enabled,status,auth_type,secret_name)
            VALUES(%s,'Existing','woocommerce',%s,false,'Disabled','bearer','owned-existing-secret')""",(server_id,WOO+'/old'))
        before = connection.execute('SELECT * FROM servers').fetchone()
    initialize_woocommerce(database,WOO,[WOO])
    with database.transaction() as connection:
        assert connection.execute('SELECT * FROM servers').fetchone() == before
        assert connection.execute('SELECT server_id FROM builtin_initializations').fetchone()['server_id'] == server_id


def test_interrupted_marker_insert_rolls_back_server_creation(database):
    ready(database)
    with database.transaction() as connection:
        connection.execute("ALTER TABLE builtin_initializations ADD CONSTRAINT controlled_failure CHECK(name<>'woocommerce')")
    with pytest.raises(Exception):
        initialize_woocommerce(database,WOO,[WOO])
    with database.transaction() as connection:
        assert connection.execute('SELECT count(*) AS n FROM servers').fetchone()['n'] == 0
        assert connection.execute('SELECT count(*) AS n FROM builtin_initializations').fetchone()['n'] == 0
        connection.execute('ALTER TABLE builtin_initializations DROP CONSTRAINT controlled_failure')
    initialize_woocommerce(database,WOO,[WOO])
    with database.transaction() as connection:
        assert connection.execute('SELECT count(*) AS n FROM servers').fetchone()['n'] == 1


def test_actual_factory_real_accounts_keys_gateway_audit_and_recovery(database,monkeypatch):
    """Real composition + PostgreSQL; only remote Kube/upstream boundaries substituted."""
    import backend.orchestrator as module
    from tests.e2e.test_runtime import config, ORIGIN

    class ControlledSecrets:
        def __init__(self,namespace,owner):
            self.namespace,self.owner,self.closed = namespace,owner,False
        def close(self):
            self.closed = True

    calls = []
    async def discover(self,row,secret):
        return [types.Tool(name='service_info',description='Controlled remote service.',inputSchema={'type':'object'})]
    async def call(self,row,secret,name,arguments,before_send):
        await before_send()
        calls.append((row['id'],name))
        return types.CallToolResult(content=[types.TextContent(type='text',text='Controlled upstream reply.')])
    monkeypatch.setattr(module,'Database',lambda dsn:database)
    monkeypatch.setattr(module,'SecretStore',ControlledSecrets)
    monkeypatch.setattr(module.UpstreamClient,'discover',discover)
    monkeypatch.setattr(module.UpstreamClient,'call',call)
    database.migrate()
    Identity(database).bootstrap('admin@example.test','Example password 123!')
    interrupted = uuid4()
    with database.transaction() as connection:
        owner = connection.execute('SELECT id FROM installation').fetchone()['id']
        connection.execute("""INSERT INTO audit_records(audit_id,request_id,public_tool_name,outcome,run_id)
            VALUES(%s,%s,'previous__interrupted','running',%s)""",(interrupted,uuid4(),uuid4()))

    async def scenario():
        app = module.create_application(config())
        runtime = app.state.runtime
        async with app.router.lifespan_context(app):
            assert runtime.secrets.owner == owner
            with database.transaction() as connection:
                recovered = connection.execute('SELECT outcome,error_code FROM audit_records WHERE audit_id=%s',(interrupted,)).fetchone()
                assert recovered == {'outcome':'unknown','error_code':'INTERRUPTED'}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as browser:
                response = await browser.post('/api/v1/auth/login',json={'email':'admin@example.test','password':'Example password 123!'},headers={'origin':ORIGIN})
                assert response.status_code == 200, 'Real admin login failed; reply suppressed.'
                cookie = response.headers['set-cookie']
                assert 'Secure' in cookie and 'HttpOnly' in cookie
                admin_headers = {'origin':ORIGIN,'x-csrf-token':response.json()['csrf_token']}
                response = await browser.get('/api/v1/servers')
                assert response.status_code == 200
                servers = response.json()['items']
                assert len(servers) == 1 and servers[0]['slug'] == 'woocommerce'
                server_id = servers[0]['id']
                response = await browser.post('/api/v1/invitations',json={'email':'member@example.test','role':'member'},headers=admin_headers)
                assert response.status_code == 201, 'Real invitation failed; reply suppressed.'
                token = response.json()['invite_url'].split('#token=')[1]
                response = await browser.post('/api/v1/invitations/redeem',json={'token':token,'password':'Member password 123!'},headers={'origin':ORIGIN})
                assert response.status_code == 201, 'Real redemption failed; reply suppressed.'
                member_id = response.json()['user']['id']
                response = await browser.post('/api/v1/auth/login',json={'email':'member@example.test','password':'Member password 123!'},headers={'origin':ORIGIN})
                assert response.status_code == 200, 'Real member login failed; reply suppressed.'
                member_headers = {'origin':ORIGIN,'x-csrf-token':response.json()['csrf_token']}
                assert (await browser.post('/api/v1/servers',json={'name':'Forbidden','slug':'forbidden','url':WOO},headers=member_headers)).status_code == 403
                response = await browser.post('/api/v1/members/'+member_id+'/keys',json={'label':'Composition test'},headers=member_headers)
                assert response.status_code == 201, 'Real key issue failed; reply suppressed.'
                key = response.json()
                headers = {'authorization':'Bearer '+key['raw_key'],'accept':'application/json, text/event-stream'}
                async def mcp(method,params,request_id):
                    return await browser.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':request_id,'method':method,'params':params})
                response = await mcp('initialize',{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'composition-test','version':'1'}},1)
                assert response.status_code == 200
                response = await mcp('tools/list',{},2)
                assert response.status_code == 200 and response.json()['result']['tools'][0]['name'] == 'woocommerce__service_info'
                response = await mcp('tools/call',{'name':'woocommerce__service_info','arguments':{}},3)
                assert response.status_code == 200 and not response.json()['result'].get('isError') and len(calls) == 1
                response = await browser.delete('/api/v1/members/'+member_id+'/keys/'+key['id'],headers=member_headers)
                assert response.status_code == 204
                response = await mcp('tools/call',{'name':'woocommerce__service_info','arguments':{}},4)
                assert response.status_code == 401 and len(calls) == 1
                with database.transaction() as connection:
                    stored = connection.execute('SELECT token_hash FROM api_keys WHERE id=%s',(key['id'],)).fetchone()
                    assert stored['token_hash'] != key['raw_key']
                    audits = connection.execute("SELECT user_id,key_id,server_id,outcome,error_code FROM audit_records WHERE public_tool_name='woocommerce__service_info' ORDER BY started_at").fetchall()
                    assert len(audits) == 2 and str(audits[0]['user_id']) == member_id
                    assert str(audits[0]['key_id']) == key['id'] and str(audits[0]['server_id']) == server_id
                    assert audits[0]['outcome'] == 'success' and audits[1]['outcome'] == 'denied' and audits[1]['error_code'] == 'KEY_REVOKED'
        assert runtime.secrets.closed and database.owner.closed
    asyncio.run(scenario())
