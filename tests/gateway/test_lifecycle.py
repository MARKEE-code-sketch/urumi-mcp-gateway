import asyncio
from contextlib import contextmanager
import time
from threading import Event
from uuid import UUID, uuid4

from mcp import types
import pytest

from backend.errors import PlatformError
from backend.identity.auth import Principal
from backend.gateway.context import request_context, invocation_context
from backend.gateway.schema import check_schema
from scripts.m6.fixtures import fixture_app
from scripts.m6.harness import build
from tests.gateway.helpers import LocalServer, tokens


@contextmanager
def isolated():
    values = tokens()
    peer = LocalServer(fixture_app())
    app = build({'none':peer.url+'/mcp'}, values)
    router = app.app.state.router
    try:
        yield router, values
    finally:
        peer.close()


def test_cancel_during_audit_begin_never_creates_second_attempt():
    with isolated() as (router, values):
        async def check():
            principal = router.identity.validate(values['key-a'])
            await router.list_tools(principal)
            started = Event()
            original = router.audit.begin_attempt
            def delayed(*args):
                started.set()
                time.sleep(.2)
                return original(*args)
            router.audit.begin_attempt = delayed
            with request_context() as context:
                task = asyncio.create_task(router.invoke_tool(principal,'none__service_info',{}))
                while not started.is_set():
                    await asyncio.sleep(.01)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                await asyncio.sleep(.4)
                assert len(router.audit.records)==1
                assert next(iter(router.audit.records.values()))['outcome']=='denied'
                assert len(context.completions)==1
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


def test_cancel_after_submission_unknown_once_completion_and_no_retry():
    with isolated() as (router, values):
        async def check():
            principal=router.identity.validate(values['key-a'])
            await router.list_tools(principal)
            sent=asyncio.Event()
            original=router.upstream.call
            async def call(row,secret,name,args,before):
                async def marked():
                    await before()
                    sent.set()
                return await original(row,secret,name,args,marked)
            router.upstream.call=call
            with request_context() as context:
                task=asyncio.create_task(router.invoke_tool(principal,'none__service_info',{'delay':2}))
                await sent.wait()
                await asyncio.sleep(.05)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert len(router.audit.records)==1
                assert next(iter(router.audit.records.values()))['outcome']=='unknown'
                assert context.completions[0]['error_code']=='INTERRUPTED'
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


def test_revoke_at_final_boundary_one_denial_and_zero_tool_submission():
    with isolated() as (router, values):
        async def check():
            principal=router.identity.validate(values['key-a'])
            await router.list_tools(principal)
            original=router.upstream.call
            async def call(row,secret,name,args,before):
                router.identity.credentials[values['key-a']]['active']=False
                return await original(row,secret,name,args,before)
            router.upstream.call=call
            reply=await router.invoke_tool(principal,'none__service_info',{})
            assert reply['outcome']=='denied'
            assert len(router.audit.records)==1
            assert next(iter(router.audit.records.values()))['outcome']=='denied'
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


def test_old_discovery_cannot_publish_after_configuration_edit():
    with isolated() as (router, values):
        async def check():
            old=router.registry.get_server(UUID(int=301))
            original=router.upstream.discover
            async def discover(*args):
                result=await original(*args)
                router.registry.edit(old['id'], {'enabled':False})
                return result
            router.upstream.discover=discover
            await router.discovery.refresh(old)
            assert old['id'] not in router.discovery.snapshots
            assert router.registry.get_server(old['id'])['status']=='Disabled'
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


def test_invalid_output_schema_is_execution_error_not_false_success():
    with isolated() as (router, values):
        async def check():
            principal=router.identity.validate(values['key-a'])
            await router.list_tools(principal)
            router.discovery.snapshots[UUID(int=301)]['items'][0]['outputSchema']={
                'type':'object','required':['absent']}
            reply=await router.invoke_tool(principal,'none__service_info',{})
            assert reply['outcome']=='error' and reply['result'].isError
            assert next(iter(router.audit.records.values()))['outcome']=='error'
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


@pytest.mark.parametrize('schema', [{'type':'string','pattern':'(a+)+$'},
    {'$ref':'#'}, {'$dynamicRef':'https://metadata.google.internal/'},
    {'patternProperties':{'.*':{}}}, {'oneOf':[{'oneOf':[{}]*9}]*9}])
def test_dangerous_schema_subset_rejected_before_validation(schema):
    with pytest.raises(Exception):
        check_schema(schema)


def test_trusted_string_request_id_normalizes_for_actual_m5_contract():
    value=uuid4()
    with request_context(str(value)) as context:
        assert isinstance(context.request_id,UUID) and context.request_id==value


def test_healthy_peer_finishes_while_other_call_is_still_slow():
    values=tokens()
    peers={mode:LocalServer(fixture_app(mode, values.get(mode+'-token',''))) for mode in ('none','bearer')}
    router=build({mode:peer.url+'/mcp' for mode,peer in peers.items()},values).app.state.router
    try:
        async def check():
            principal=router.identity.validate(values['key-a'])
            await router.list_tools(principal)
            sent=asyncio.Event()
            original=router.upstream.call
            async def call(row,secret,name,args,before):
                async def marked():
                    await before()
                    if row['slug']=='none':
                        sent.set()
                return await original(row,secret,name,args,marked)
            router.upstream.call=call
            slow=asyncio.create_task(router.invoke_tool(principal,'none__service_info',{'delay':2}))
            await sent.wait()
            started=time.monotonic()
            healthy=await router.invoke_tool(principal,'bearer__service_info',{})
            elapsed=time.monotonic()-started
            assert healthy['outcome']=='success' and elapsed<2 and not slow.done()
            assert (await slow)['outcome']=='success'
            assert len(router.audit.records)==2
            assert all(row['outcome']=='success' for row in router.audit.records.values())
            await router.discovery.close()
            await router.close()
        asyncio.run(check())
    finally:
        for peer in peers.values():
            peer.close()


@pytest.mark.parametrize('kind',['fabricated','invalid_session'])
def test_internal_identity_denials_never_submit_upstream(kind):
    with isolated() as (router,values):
        async def check():
            genuine=router.identity.session(values['session-a'])
            await router.list_tools(genuine)
            called=False
            async def forbidden_call(*args):
                nonlocal called
                called=True
                raise AssertionError('Denied identity reached upstream.')
            router.upstream.call=forbidden_call
            if kind=='fabricated':
                principal=Principal(genuine.user_id,'admin','session',_handle=genuine._handle,_proof=object())
            else:
                principal=genuine
                router.identity.credentials[values['session-a']]['active']=False
            result=await router.invoke_tool(principal,'none__service_info',{})
            assert result['outcome']=='denied' and not called
            assert len(router.audit.records)==1
            row=next(iter(router.audit.records.values()))
            assert row['outcome']=='denied'
            if kind=='fabricated':
                assert row['user_id'] is None
            await router.discovery.close()
            await router.close()
        asyncio.run(check())
