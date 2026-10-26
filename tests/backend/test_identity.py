from concurrent.futures import ThreadPoolExecutor
from uuid import UUID
from threading import Event

import pytest

from backend.errors import PlatformError
from backend.identity.auth import Principal,csrf_value,digest,password_value
from backend.identity.auth import Identity


def rejects(function,code):
    with pytest.raises(PlatformError) as result:
        function()
    assert result.value.code==code


def test_simultaneous_first_admin(db):
    identity=Identity(db)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda n:identity.bootstrap(f'admin{n}@example.test','Example password 123!'),range(2)))
    assert results[0]['id']==results[1]['id']
    with db.transaction() as c:
        assert c.execute('SELECT count(*) AS n FROM users').fetchone()['n']==1


def test_concurrent_key_revocation_boundary(identities):
    identity,_,keys,admin,_,_=identities
    key=keys.issue(admin,admin.user_id,'concurrency fixture')
    validated,revoked=Event(),Event()
    def validator():
        principal=keys.validate(key['raw_key'])
        validated.set()
        assert revoked.wait(5)
        rejects(lambda:identity.revalidate(principal),'UNAUTHENTICATED')
    def revoker():
        assert validated.wait(5)
        keys.revoke(admin,admin.user_id,UUID(key['id']))
        revoked.set()
    with ThreadPoolExecutor(2) as pool:
        first,second=pool.submit(validator),pool.submit(revoker)
        first.result(); second.result()


def test_bootstrap_migrations_and_race(db,identities):
    identity,_,_,_,_,admin=identities
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:identity.bootstrap('different@example.test','Different password 123!'),range(2)))
    assert all(r['id']==admin['id'] for r in results)
    db.migrate()
    identity.login('admin@example.test','Example password 123!')
    rejects(lambda:identity.login('admin@example.test','Different password 123!'),'UNAUTHENTICATED')
    with db.transaction() as c:
        assert c.execute("SELECT count(*) AS n FROM users WHERE role='admin'").fetchone()['n']==1


def test_invitation_race_expiry_and_reinvite(db,identities):
    _,members,_,admin,_,_=identities
    invite=members.invite(admin,' Member@Example.test ','member')
    token=invite['invite_url'].split('#token=')[1]
    rejects(lambda:members.invite(admin,'member@example.test','member'),'CONFLICT')
    def redeem(_):
        try:
            members.redeem(token,'Member password 123!')
            return 'created'
        except PlatformError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(redeem,range(2)))==['CONFLICT','created']
    rejects(lambda:members.redeem('invalid','Member password 123!'),'INVALID_INPUT')
    expired=members.invite(admin,'expired@example.test','member')
    with db.transaction() as c:
        c.execute("UPDATE invitations SET expires_at=now()-interval '1 second' WHERE email='expired@example.test'")
        assert c.execute('SELECT count(*) AS n FROM invitations WHERE token_hash=%s',(digest(token),)).fetchone()['n']==1
    rejects(lambda:members.redeem(expired['invite_url'].split('#token=')[1],'Member password 123!'),'INVALID_INPUT')
    members.invite(admin,'expired@example.test','member')


def test_session_rotation_expiry_logout_and_forgery(db,identities):
    identity,_,_,principal,token,_=identities
    reply,new_token=identity.login('admin@example.test','Example password 123!',token)
    rejects(lambda:identity.session(token),'UNAUTHENTICATED')
    current=identity.session(new_token)
    assert reply['csrf_token']==csrf_value(new_token)
    assert identity.me(current,new_token)['csrf_token']==reply['csrf_token']
    identity.check_csrf(current,reply['csrf_token'])
    rejects(lambda:identity.check_csrf(current,'bad'),'REQUEST_REJECTED')
    rejects(lambda:identity.revalidate(Principal(principal.user_id,'admin','session')),'UNAUTHENTICATED')
    with db.transaction() as c:
        c.execute("UPDATE sessions SET expires_at=now()-interval '1 second' WHERE id=%s",(current._handle,))
    rejects(lambda:identity.revalidate(current),'UNAUTHENTICATED')
    _,next_token=identity.login('admin@example.test','Example password 123!')
    identity.logout(identity.session(next_token))
    rejects(lambda:identity.session(next_token),'UNAUTHENTICATED')


def test_key_ownership_hashes_revocation_and_underscore(db,identities,monkeypatch):
    identity,members,keys,admin,session_token,user=identities
    invite=members.invite(admin,'member@example.test','member')
    member=members.redeem(invite['invite_url'].split('#token=')[1],'Member password 123!')['user']
    _,token=identity.login('member@example.test','Member password 123!')
    principal=identity.session(token)
    monkeypatch.setattr('backend.identity.api_keys.secrets.token_urlsafe',lambda _: 'safe_random_token_with_underscores_1234567890')
    key=keys.issue(admin,UUID(member['id']),'issued to member')
    verified=keys.validate(key['raw_key'])
    assert str(verified.user_id)==member['id'] and verified.role=='member'
    rejects(lambda:keys.list(principal,UUID(user['id']),1,20),'NOT_FOUND')
    rejects(lambda:members.list(principal,1,20),'FORBIDDEN')
    rejects(lambda:keys.validate(key['raw_key']+'wrong'),'UNAUTHENTICATED')
    second=keys.issue(principal,principal.user_id,'second')
    keys.revoke(admin,principal.user_id,UUID(key['id']))
    keys.revoke(admin,principal.user_id,UUID(key['id']))
    rejects(lambda:keys.validate(key['raw_key']),'KEY_REVOKED')
    rejects(lambda:identity.revalidate(verified),'UNAUTHENTICATED')
    keys.validate(second['raw_key'])
    identity.session(token)
    assert all('raw_key' not in row for row in keys.list(principal,principal.user_id,1,20)['items'])
    with db.transaction() as c:
        row=c.execute('SELECT token_hash FROM api_keys WHERE id=%s',(UUID(key['id']),)).fetchone()
        assert row['token_hash']==digest(key['raw_key']) and row['token_hash']!=key['raw_key']


def test_invalid_unicode_password_and_owner_loss(db,identities):
    identity,_,_,principal,_,_=identities
    rejects(lambda:password_value('abc123456789\ud800'),'INVALID_INPUT')
    db.close()
    rejects(lambda:identity.revalidate(principal),'DEPENDENCY_UNAVAILABLE')
