import json
from uuid import uuid4

import httpx

from backend.registry.secret_store import SecretStore
from tests.backend.test_identity import rejects


def test_secret_ownership_immutable_metadata_and_delete_uid():
    server_id,owner=uuid4(),uuid4()
    name='urumi-upstream-'+str(uuid4())
    document=None
    def handle(request):
        nonlocal document
        if request.method=='GET':
            return httpx.Response(404 if document is None else 200,json=document or {})
        data=json.loads(request.content)
        if request.method=='POST':
            assert data['immutable'] is True
            data['metadata']['uid']='observed-uid'
            document=data
        elif request.method=='PUT':
            assert data['data']==document['data'] and data['immutable'] is True
            document=data
        elif request.method=='DELETE':
            assert data['preconditions']['uid']=='observed-uid'
            document=None
        return httpx.Response(200,json={})
    client=httpx.Client(base_url='https://kubernetes.test',transport=httpx.MockTransport(handle))
    store=SecretStore('check',owner,client)
    store.create(name,server_id,'fixture-value')
    assert store.resolve(name,server_id)=='fixture-value'
    store.update_owned(name,server_id)
    rejects(lambda:store.resolve(name,uuid4()),'DEPENDENCY_UNAVAILABLE')
    store.delete(name,server_id)
    assert document is None
    store.close()


def test_foreign_name_collision_and_response_bound_fail_closed():
    server_id,owner=uuid4(),uuid4()
    name='urumi-upstream-'+str(uuid4())
    foreign={'metadata':{'name':name,'namespace':'check','labels':{'urumi-module':'other'}}}
    requests=[]
    def handle(request):
        requests.append(request.method)
        return httpx.Response(200,json=foreign)
    store=SecretStore('check',owner,httpx.Client(base_url='https://kubernetes.test',transport=httpx.MockTransport(handle)))
    rejects(lambda:store.create(name,server_id,'fixture'),'DEPENDENCY_UNAVAILABLE')
    rejects(lambda:store.delete(name,server_id),'DEPENDENCY_UNAVAILABLE')
    assert requests==['GET','GET']
    store.close()
    store=SecretStore('check',owner,httpx.Client(base_url='https://kubernetes.test',transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*262145))))
    rejects(lambda:store.get(name,server_id),'DEPENDENCY_UNAVAILABLE')
    store.close()
