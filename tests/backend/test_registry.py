from threading import Event
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID
from contextlib import contextmanager

import pytest

from backend.errors import unavailable
from backend.registry.servers import Registry,validate_url,validate_credential
from tests.backend.test_identity import rejects

URL='http://urumi-inventory-mcp.urumi.svc.cluster.local:8000/mcp'


class FakeSecrets:
    def __init__(self):
        self.values={}; self.failure=None; self.entered=None; self.release=None

    def create(self,name,server_id,value):
        if self.failure=='before_create':
            raise unavailable()
        self.values[name]=(server_id,value)
        if self.entered:
            self.entered.set(); assert self.release.wait(5)
        if self.failure=='after_create':
            raise unavailable()

    def delete(self,name,server_id):
        if not name:
            return
        if self.failure=='delete':
            raise unavailable()
        if name in self.values:
            assert self.values[name][0]==server_id
            del self.values[name]


def setup_registry(db):
    secrets=FakeSecrets()
    return Registry(db,secrets,[URL]),secrets


def create(registry,principal,slug='inventory',credential=None):
    return registry.create_server(principal,{'name':'Inventory','slug':slug,'url':URL,'credential':credential or {'type':'none'}})


def test_registry_modes_retention_clear_visibility_and_status(db,identities):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    row=create(registry,admin,credential={'type':'bearer','value':'fixture-secret'})
    server_id=UUID(row['id'])
    assert row['status']=='Unreachable' and row['status_reason']=='NOT_CHECKED'
    assert 'secret_name' not in row and 'value' not in row
    old=registry.get_server(server_id)['secret_name']
    registry.update_server(admin,server_id,{'name':'Renamed'})
    assert registry.get_server(server_id)['secret_name']==old
    registry.update_server(admin,server_id,{'credential':{'type':'header','header_name':'X-API-Key','value':'second-fixture'}})
    assert old not in secrets.values
    registry.update_server(admin,server_id,{'credential':{'type':'none'},'enabled':False})
    assert not secrets.values
    registry.set_server_status(server_id,'Connected')
    assert registry.get(admin,server_id)['status']=='Disabled'
    rejects(lambda:registry.update_server(admin,server_id,{'slug':'changed'}),'INVALID_INPUT')
    rejects(lambda:create(registry,admin),'CONFLICT')
    registry.remove_server(admin,server_id)
    rejects(lambda:registry.get_server(server_id),'NOT_FOUND')


@pytest.mark.parametrize('stage',['before_create','after_create'])
def test_staged_create_crash_rollback_and_existing_retained(db,identities,stage):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    row=create(registry,admin,credential={'type':'bearer','value':'original-fixture'})
    server_id=UUID(row['id']); old=registry.get_server(server_id)['secret_name']
    secrets.failure=stage
    rejects(lambda:registry.update_server(admin,server_id,{'credential':{'type':'bearer','value':'new-fixture'}}),'DEPENDENCY_UNAVAILABLE')
    assert registry.get_server(server_id)['secret_name']==old
    with db.transaction() as c:
        operation=c.execute('SELECT * FROM secret_operations').fetchone()
        assert operation['staged_name'] and operation['phase']=='prepared'
    secrets.failure=None
    assert registry.recover()==0 and set(secrets.values)=={old}
    secrets.failure=stage
    rejects(lambda:create(registry,admin,'new',{'type':'bearer','value':'new-fixture'}),'DEPENDENCY_UNAVAILABLE')
    assert all(not r['enabled'] for r in registry.list_servers() if r['slug']=='new')
    secrets.failure=None
    assert registry.recover()==0
    assert all(r['slug']!='new' for r in registry.list_servers())


def test_postcommit_retire_and_removal_failure_recover(db,identities):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    row=create(registry,admin,credential={'type':'bearer','value':'first-fixture'}); server_id=UUID(row['id'])
    old=registry.get_server(server_id)['secret_name']; secrets.failure='delete'
    rejects(lambda:registry.update_server(admin,server_id,{'credential':{'type':'bearer','value':'second-fixture'}}),'DEPENDENCY_UNAVAILABLE')
    assert registry.get_server(server_id)['secret_name']!=old
    rejects(lambda:registry.update_server(admin,server_id,{'enabled':False}),'CONFLICT')
    secrets.failure=None
    assert registry.recover()==0 and old not in secrets.values
    secrets.failure='delete'
    rejects(lambda:registry.remove_server(admin,server_id),'DEPENDENCY_UNAVAILABLE')
    assert registry.get(admin,server_id)['status']=='Disabled'
    secrets.failure=None
    assert registry.recover()==0 and not secrets.values
    rejects(lambda:registry.get_server(server_id),'NOT_FOUND')


def test_conflicting_update_recovery_and_remove_share_lock(db,identities):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    server_id=UUID(create(registry,admin)['id'])
    secrets.entered,secrets.release=Event(),Event()
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(registry.update_server,admin,server_id,{'credential':{'type':'bearer','value':'fixture'}})
        assert secrets.entered.wait(5)
        rejects(lambda:registry.remove_server(admin,server_id),'CONFLICT')
        rejects(lambda:registry.update_server(admin,server_id,{'enabled':False}),'CONFLICT')
        assert registry.recover()==1
        secrets.release.set(); future.result()
    assert registry.recover()==0


@pytest.mark.parametrize('url',['http://example.com/mcp','https://127.0.0.1/mcp','https://169.254.169.254/','https://10.0.0.1/','https://2130706433/','https://0x7f000001/','https://user:pass@example.com/','https://example.com/#fragment','https://example.com/?token=value',URL+'/other','https://metadata.google.internal/'])
def test_url_policy_denies(url):
    rejects(lambda:validate_url(url,{URL}),'INVALID_INPUT')


def test_url_and_header_policy_allows_and_rejects():
    assert validate_url(URL,{URL})==URL
    assert validate_url('https://learn.microsoft.com/api/mcp',{URL})=='https://learn.microsoft.com/api/mcp'
    for name in ['Host','Authorization','Mcp-Session-Id','Content-Type','Bad\r\nName']:
        rejects(lambda:validate_credential({'type':'header','header_name':name,'value':'fixture'}),'INVALID_INPUT')
    rejects(lambda:validate_credential({'type':'bearer','value':'bad\r\nvalue'}),'INVALID_INPUT')
    validate_credential({'type':'header','header_name':'X-API-Key','value':'fixture'})


def test_late_ambiguous_create_known_name_retained(db,identities):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    secrets.failure='before_create'
    rejects(lambda:create(registry,admin,'late',{'type':'bearer','value':'fixture'}),'DEPENDENCY_UNAVAILABLE')
    with db.transaction() as c:
        intent=c.execute('SELECT * FROM secret_operations').fetchone()
    secrets.failure=None
    assert registry.recover()==0
    # Simulate the old timed-out remote create completing after the first absent GET.
    secrets.values[intent['staged_name']]=(intent['server_id'],'late-fixture')
    with db.transaction() as c:
        assert c.execute('SELECT count(*) AS n FROM canceled_secret_names').fetchone()['n']==1
    assert registry.recover()==0 and not secrets.values
    with db.transaction() as c:
        assert c.execute('SELECT count(*) AS n FROM canceled_secret_names').fetchone()['n']==1


def test_delayed_create_lock_connection_loss_and_active_recovery(db,identities,monkeypatch):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    original=db.server_lock
    captured={}
    @contextmanager
    def capture(server_id):
        with original(server_id) as c:
            captured['connection']=c
            yield c
    monkeypatch.setattr(db,'server_lock',capture)
    entered,release=Event(),Event()
    def delayed_create(name,server_id,value):
        captured['connection'].close()  # Actual PostgreSQL session advisory lock is lost.
        entered.set()
        assert release.wait(5)
        secrets.values[name]=(server_id,value)
    monkeypatch.setattr(secrets,'create',delayed_create)
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(create,registry,admin,'delayed',{'type':'bearer','value':'fixture'})
        assert entered.wait(5)
        assert registry.recover()==1  # Active operation cannot be rolled back under its caller.
        release.set()
        rejects(lambda:future.result(),'DEPENDENCY_UNAVAILABLE')
    assert registry.recover()==0 and not secrets.values
    with db.transaction() as c:
        assert c.execute('SELECT count(*) AS n FROM canceled_secret_names').fetchone()['n']==1


@pytest.mark.parametrize('table,event', [('secret_operations','INSERT'),('servers','UPDATE'),('servers','DELETE')])
def test_real_db_failure_before_intent_activation_and_after_remote_delete(db,identities,table,event):
    _,_,_,admin,_,_=identities
    registry,secrets=setup_registry(db)
    server_id=UUID(create(registry,admin,credential={'type':'bearer','value':'original'})['id'])
    original=registry.get_server(server_id)['secret_name']
    with db.transaction() as c:
        c.execute("CREATE OR REPLACE FUNCTION m5_test_reject() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'controlled M5 database failure'; END $$")
        c.execute(f'CREATE TRIGGER m5_test_reject BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION m5_test_reject()')
    try:
        if event=='DELETE':
            rejects(lambda:registry.remove_server(admin,server_id),'DEPENDENCY_UNAVAILABLE')
            assert original not in secrets.values
            assert registry.get_server(server_id)['status']=='Disabled'
        else:
            rejects(lambda:registry.update_server(admin,server_id,{'credential':{'type':'bearer','value':'replacement'}}),'DEPENDENCY_UNAVAILABLE')
            assert registry.get_server(server_id)['secret_name']==original
            if table=='secret_operations':
                assert set(secrets.values)=={original}
            else:
                assert len(secrets.values)==2
    finally:
        with db.transaction() as c:
            c.execute(f'DROP TRIGGER m5_test_reject ON {table}')
            c.execute('DROP FUNCTION m5_test_reject()')
    assert registry.recover()==0
    if event=='DELETE':
        assert not secrets.values
        rejects(lambda:registry.get_server(server_id),'NOT_FOUND')
    else:
        assert set(secrets.values)=={original}
