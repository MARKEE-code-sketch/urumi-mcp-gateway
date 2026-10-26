from uuid import UUID,uuid4
from threading import Event
from concurrent.futures import ThreadPoolExecutor

from backend.audit.records import Audit
from backend.db.database import Database
from backend.errors import PlatformError
from tests.backend.test_identity import rejects


def test_audit_outcomes_denial_safe_fields_visibility_and_finalization(db,identities):
    identity,members,_,admin,_,_=identities
    audit=Audit(db,identity)
    for outcome in ('success','error','timeout','unknown'):
        record=audit.begin_attempt(uuid4(),admin,None,'fixture__lookup')
        audit.finalize_attempt(record,outcome,4,'TIMEOUT' if outcome=='timeout' else None)
        rejects(lambda:audit.finalize_attempt(record,'success',4),'CONFLICT')
    audit.record_denial(uuid4(),None,None,'unknown','UNAUTHENTICATED')
    invite=members.invite(admin,'member@example.test','member')
    members.redeem(invite['invite_url'].split('#token=')[1],'Member password 123!')
    _,token=identity.login('member@example.test','Member password 123!')
    member=identity.session(token)
    audit.record_denial(uuid4(),member,None,'fixture__lookup','FORBIDDEN')
    assert len(audit.list(admin,1,20)['items'])==6
    assert len(audit.list(member,1,20)['items'])==1
    rejects(lambda:audit.list(member,1,20,user_id=admin.user_id),'FORBIDDEN')
    assert audit.list(member,1,1)['has_more'] is False
    rejects(lambda:audit.record_denial(uuid4(),None,None,'fixture','secret raw exception'),'INVALID_INPUT')
    assert all('run_id' not in r for r in audit.list(admin,1,20)['items'])


def test_audit_recovery_does_not_finalize_active_then_new_owner_recovers(db,identities):
    identity,_,_,admin,_,_=identities
    audit=Audit(db,identity)
    record=audit.begin_attempt(uuid4(),admin,None,'fixture__lookup')
    assert audit.recover()==[]
    second=Database(db.dsn)
    rejects(lambda:second.acquire_owner(),'CONFLICT')
    db.close(); second.acquire_owner()
    try:
        recovered=Audit(second,identity).recover()
        assert len(recovered)==1 and recovered[0]['audit_id']==record
        with second.transaction() as c:
            row=c.execute('SELECT outcome,duration_ms FROM audit_records WHERE audit_id=%s',(record,)).fetchone()
        assert row['outcome']=='unknown' and row['duration_ms'] is None
    finally:
        second.close()


def test_audit_storage_failures_fail_closed_without_false_finalization(db,identities,monkeypatch):
    identity,_,_,admin,_,_=identities
    audit=Audit(db,identity)
    record=audit.begin_attempt(uuid4(),admin,None,'fixture__lookup')
    original=db.transaction
    def failure():
        raise PlatformError(503,'DEPENDENCY_UNAVAILABLE','A required dependency is unavailable.')
    monkeypatch.setattr(db,'transaction',failure)
    rejects(lambda:audit.begin_attempt(uuid4(),admin,None,'fixture'),'AUDIT_UNAVAILABLE')
    rejects(lambda:audit.finalize_attempt(record,'success',1),'AUDIT_FINALIZATION_FAILED')
    monkeypatch.setattr(db,'transaction',original)
    with db.transaction() as c:
        assert c.execute('SELECT outcome FROM audit_records WHERE audit_id=%s',(record,)).fetchone()['outcome']=='running'


def test_real_sql_lock_failure_initial_and_final(db,identities):
    identity,_,_,admin,_,_=identities
    audit=Audit(db,identity)
    existing=audit.begin_attempt(uuid4(),admin,None,'fixture__lookup')
    with db.connect() as blocker:
        blocker.execute('LOCK TABLE audit_records IN ACCESS EXCLUSIVE MODE')
        rejects(lambda:audit.begin_attempt(uuid4(),admin,None,'fixture__lookup'),'AUDIT_UNAVAILABLE')
        rejects(lambda:audit.finalize_attempt(existing,'success',1),'AUDIT_FINALIZATION_FAILED')
    with db.transaction() as c:
        row=c.execute('SELECT count(*) AS n,min(outcome) AS outcome FROM audit_records').fetchone()
    assert row['n']==1 and row['outcome']=='running'


def test_approved_safe_error_codes(db,identities):
    identity,_,_,admin,_,_=identities
    audit=Audit(db,identity)
    for code in ('TOOL_DISABLED','UPSTREAM_TIMEOUT','UPSTREAM_AUTH_FAILED','UPSTREAM_UNAVAILABLE','UPSTREAM_PROTOCOL_ERROR'):
        record=audit.begin_attempt(uuid4(),admin,None,'fixture__lookup')
        audit.finalize_attempt(record,'error',1,code)
    assert len(audit.list(admin,1,20)['items'])==5
