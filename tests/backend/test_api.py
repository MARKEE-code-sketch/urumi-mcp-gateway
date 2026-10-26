from uuid import UUID
import asyncio
import json
from threading import Event

import httpx

import pytest
from fastapi.testclient import TestClient

from backend.api import BrowserConfig,create_api
from backend.audit.records import Audit
from tests.backend.test_registry import setup_registry,URL


@pytest.fixture
def api(db,identities):
    identity,members,keys,admin,_,_=identities
    registry,_=setup_registry(db)
    config=BrowserConfig('http://127.0.0.1:18005',True)
    with TestClient(create_api(db,identity,members,keys,registry,Audit(db,identity),config),
                    base_url=config.origin) as client:
        yield client,config,admin,keys


def login(client,config,email='admin@example.test',password='Example password 123!'):
    response=client.post('/api/v1/auth/login',json={'email':email,'password':password},headers={'Origin':config.origin})
    assert response.status_code==200,'Login fixture failed; credential-bearing reply suppressed.'
    return {'Origin':config.origin,'X-CSRF-Token':response.json()['csrf_token']},response


def test_login_origin_csrf_cookie_rotation_and_bearer_separation(api):
    client,config,admin,keys=api
    for origin in (None,'null','https://wrong.example.test'):
        headers={} if origin is None else {'Origin':origin}
        response=client.post('/api/v1/auth/login',json={'email':'admin@example.test','password':'Example password 123!'},headers=headers)
        assert response.status_code==403
    headers,response=login(client,config)
    cookie=response.headers['set-cookie']
    assert 'HttpOnly' in cookie and 'SameSite=lax' in cookie and 'Secure' not in cookie
    assert response.headers['cache-control']=='no-store'
    assert client.get('/api/v1/auth/me').status_code==200
    assert client.get('/api/v1/auth/me').json()['csrf_token']==headers['X-CSRF-Token']
    assert client.post('/api/v1/invitations',json={'email':'member@example.test','role':'member'},headers={'Origin':config.origin}).status_code==403
    raw=keys.issue(admin,admin.user_id,'fixture')['raw_key']
    client.cookies.clear()
    assert client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+raw}).status_code==401


def test_api_admin_member_permissions_redaction_and_shapes(api):
    client,config,admin,_=api
    headers,_=login(client,config)
    invite=client.post('/api/v1/invitations',json={'email':'member@example.test','role':'member'},headers=headers)
    assert invite.status_code==201
    token=invite.json()['invite_url'].split('#token=')[1]
    member=client.post('/api/v1/invitations/redeem',json={'token':token,'password':'Member password 123!'},headers={'Origin':config.origin})
    assert member.status_code==201
    member_id=member.json()['user']['id']
    server=client.post('/api/v1/servers',json={'name':'Inventory','slug':'inventory','url':URL,'credential':{'type':'bearer','value':'fixture-secret'}},headers=headers)
    assert server.status_code==201
    assert 'secret_name' not in server.json()
    assert client.post('/api/v1/servers',json={'name':'Bad','slug':'a'*25,'url':URL},headers=headers).status_code==422
    assert client.patch('/api/v1/servers/'+server.json()['id'],json={'slug':'changed'},headers=headers).status_code==422
    assert client.post('/api/v1/auth/logout',headers=headers).status_code==204
    headers,_=login(client,config,'member@example.test','Member password 123!')
    assert client.get('/api/v1/members').status_code==403
    assert client.post('/api/v1/invitations',json={'email':'other@example.test','role':'member'},headers=headers).status_code==403
    assert client.get(f'/api/v1/members/{admin.user_id}/keys').status_code==404
    assert client.get('/api/v1/audit',params={'user_id':str(admin.user_id)}).status_code==403
    summary=client.get('/api/v1/servers').json()['items'][0]
    assert not {'url','auth_type','header_name','secret_name'}&set(summary)
    key=client.post(f'/api/v1/members/{member_id}/keys',json={'label':'own'},headers=headers)
    assert key.status_code==201
    listed=client.get(f'/api/v1/members/{member_id}/keys').json()
    assert 'raw_key' not in listed['items'][0]
    assert client.delete(f'/api/v1/members/{member_id}/keys/'+key.json()['id'],headers=headers).status_code==204
    assert client.post(f'/api/v1/members/{member_id}/keys',json={'label':'own','role':'admin'},headers=headers).status_code==422
    assert client.get('/api/v1/servers?page=0').status_code==422
    assert client.get('/api/v1/servers?per_page=51').status_code==422


def test_api_input_limits_safe_errors_and_production_cookie(api,db,identities):
    client,config,_,_=api
    headers,_=login(client,config)
    response=client.post('/api/v1/invitations',content='{"email":"'+('x'*17000)+'"}',headers={**headers,'Content-Type':'application/json'})
    assert response.status_code==422 and set(response.json())=={'error'}
    response=client.post('/api/v1/auth/login',content=json.dumps({'email':'admin@example.test','password':'abc123456789\ud800'}),headers={'Origin':config.origin,'Content-Type':'application/json'})
    assert response.status_code==422
    assert 'abc123456789' not in response.text
    identity,members,keys,_,_,_=identities
    registry,_=setup_registry(db)
    prod=BrowserConfig('https://gateway.example.test',False,'0.0.0.0')
    with TestClient(create_api(db,identity,members,keys,registry,Audit(db,identity),prod),base_url=prod.origin) as secure:
        _,reply=login(secure,prod)
        assert 'Secure' in reply.headers['set-cookie']
    with pytest.raises(ValueError):
        BrowserConfig('http://127.0.0.1:18005',True,'0.0.0.0')


def test_blocked_secret_operation_does_not_block_liveness(db,identities):
    identity,members,keys,_,_,_=identities
    registry,secrets=setup_registry(db)
    entered,release=Event(),Event()
    secrets.entered,secrets.release=entered,release
    config=BrowserConfig('http://127.0.0.1:18005',True)
    app=create_api(db,identity,members,keys,registry,Audit(db,identity),config)
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=config.origin) as client:
            login=await client.post('/api/v1/auth/login',json={'email':'admin@example.test','password':'Example password 123!'},headers={'Origin':config.origin})
            headers={'Origin':config.origin,'X-CSRF-Token':login.json()['csrf_token']}
            task=asyncio.create_task(client.post('/api/v1/servers',json={'name':'Blocked','slug':'blocked','url':URL,'credential':{'type':'bearer','value':'fixture'}},headers=headers))
            try:
                assert await asyncio.to_thread(entered.wait,5)
                response=await asyncio.wait_for(client.get('/health/live'),timeout=1)
                assert response.status_code==200
            finally:
                release.set()
            assert (await task).status_code==201
    asyncio.run(exercise())
