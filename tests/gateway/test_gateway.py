import asyncio
from contextlib import contextmanager
import json
import logging
from threading import Event
import time
from uuid import UUID

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client
import pytest

from backend.errors import PlatformError
from backend.gateway.context import complete, get_context, invocation_context, request_context
from backend.gateway.discovery import public_name
from tests.gateway.helpers import environment


async def external(url, key, operation):
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + key}, timeout=15, trust_env=False) as http:
        async with streamable_http_client(url + '/mcp', http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await operation(session)


@pytest.mark.parametrize('stateful', [False, True])
def test_real_sdk_three_servers_paging_collisions_and_headers(stateful):
    with environment(stateful) as (router, gateway, peers, values):
        async def operation(session):
            listing = await session.list_tools()
            assert len(listing.tools) == 6
            for mode in ('none', 'bearer', 'header'):
                result = await session.call_tool(mode + '__service_info', {})
                assert not result.isError and result.structuredContent['mode'] == mode
        asyncio.run(external(gateway.url, values['key-b'], operation))
        records = list(router.audit.records.values())
        assert len(records) == 3 and all(item['outcome'] == 'success' for item in records)
        assert all(item['user_id'] == str(UUID(int=102)) for item in records)
        for mode, peer in peers.items():
            state = httpx.get(peer.url + '/test/control', trust_env=False).json()
            assert all(not item['cookie'] for item in state['headers'])
            assert all(item['authorization'] == (mode == 'bearer') for item in state['headers'])
            assert all(item['custom_header'] == (mode == 'header') for item in state['headers'])


def test_existing_client_revocation_and_unknown_protocol_error():
    with environment() as (router, gateway, peers, values):
        async def operation(session):
            await session.list_tools()
            with pytest.raises(McpError):
                await session.call_tool('missing__tool', {})
            response = await httpx.AsyncClient(trust_env=False).post(gateway.url + '/test/state',
                headers={'Authorization': 'Bearer ' + values['key-a']}, json={'action': 'revoke_b'})
            assert response.status_code == 200
            with pytest.raises(Exception):
                await session.call_tool('none__service_info', {})
        with pytest.raises(Exception):
            asyncio.run(external(gateway.url, values['key-b'], operation))
        records = list(router.audit.records.values())
        assert len(records) == 2 and all(row['outcome'] == 'denied' for row in records)
        assert records[-1]['key_id'] == str(UUID(int=202))


@pytest.mark.parametrize('credential', ['', 'wrong'])
def test_missing_unknown_keys_and_cookie_not_bearer(credential):
    with environment() as (router, gateway, peers, values):
        reply = httpx.post(gateway.url + '/mcp', headers={'Authorization': 'Bearer ' + credential} if credential else {},
            cookies={'urumi_session': values['session-a']}, json={'jsonrpc': '2.0', 'id': 1,
            'method': 'tools/call', 'params': {'name': 'none__service_info', 'arguments': {}}}, trust_env=False)
        assert reply.status_code == 401
        assert list(router.audit.records.values())[0]['user_id'] is None


def test_context_completion_isolation_and_reset():
    assert get_context() is None
    with request_context(max_completions=1) as context:
        with invocation_context() as invocation:
            complete(None, None, 0, 'AUDIT_UNAVAILABLE')
            complete(None, None, 0, 'AUDIT_UNAVAILABLE')
        assert len(context.completions) == 1
        assert context.completions[0]['invocation_id'] == str(invocation)
    assert get_context() is None


@pytest.mark.parametrize('original', ['normal', 'unsafe name', 'h_reserved', 'x'*150, 'CAPS.Name'])
def test_public_names_stable_bounded_exact(original):
    name = public_name('shop', original)
    assert name == public_name('shop', original) and len(name) <= 64
    if original == 'normal':
        assert name == 'shop__normal'


@pytest.mark.parametrize('original', ['', 'x'*201, '\ud800'])
def test_invalid_original_names_fail(original):
    with pytest.raises(Exception):
        public_name('shop', original)


def test_execution_failure_preserved_invalid_arguments_once_and_preview():
    with environment() as (router, gateway, peers, values):
        async def operation(session):
            error = await session.call_tool('none__service_info', {'action': 'error'})
            assert error.isError
            # Preserve the upstream's safe execution error payload.
            assert json.loads(error.content[0].text).get('fixture_only') is True
            invalid = await session.call_tool('none__service_info', {'extra': 1})
            assert invalid.isError
        asyncio.run(external(gateway.url, values['key-a'], operation))
        state = httpx.get(peers['none'].url + '/test/control', trust_env=False).json()
        assert state['calls'] == 1 and len(router.audit.records) == 2
        preview = httpx.get(gateway.url + '/api/v1/servers/' + str(UUID(int=301)) + '/tools?per_page=1',
                            cookies={'urumi_session': values['session-b']}, trust_env=False)
        assert preview.status_code == 200 and preview.json()['has_more']
        assert 'gateway_name' in preview.json()['items'][0]
        assert 'secret_name' not in preview.text
        invalid_preview = httpx.get(gateway.url + '/api/v1/servers/' + str(UUID(int=301)) + '/tools?page=0',
                            cookies={'urumi_session': values['session-b']}, trust_env=False)
        assert invalid_preview.status_code == 422
        assert UUID(invalid_preview.json()['error']['request_id'])


def test_secret_echo_redaction_and_actual_child_logger_suppression(caplog):
    with environment() as (router, gateway, peers, values):
        async def operation(session):
            result = await session.call_tool('bearer__service_info', {'action': 'echo'})
            assert values['bearer-token'] not in result.model_dump_json()
            assert '[REDACTED]' in result.model_dump_json()
        asyncio.run(external(gateway.url, values['key-a'], operation))
        with caplog.at_level(logging.DEBUG):
            logging.getLogger('mcp.client.streamable_http').error(values['key-a'])
            logging.getLogger('mcp.future.child').error(values['key-b'])
        assert values['key-a'] not in caplog.text and values['key-b'] not in caplog.text


def test_audit_failure_no_dispatch_and_finalization_uncertain():
    with environment() as (router, gateway, peers, values):
        async def operation(session):
            await session.list_tools()
            router.audit.fail_begin = True
            with pytest.raises(McpError):
                await session.call_tool('none__service_info', {})
            router.audit.fail_begin = False
            router.audit.fail_finalize = True
            with pytest.raises(McpError):
                await session.call_tool('none__service_info', {})
        asyncio.run(external(gateway.url, values['key-a'], operation))
        state = httpx.get(peers['none'].url + '/test/control', trust_env=False).json()
        assert state['calls'] == 1 and len(router.audit.records) == 1
        assert next(iter(router.audit.records.values()))['outcome'] == 'running'


def test_disabled_stale_name_and_version_conditional_status():
    with environment() as (router, gateway, peers, values):
        async def operation(session):
            await session.list_tools()
            router.registry.edit(UUID(int=301), {'enabled': False})
            result = await session.call_tool('none__service_info', {})
            assert result.isError and 'TOOL_DISABLED' in result.content[0].text
            assert router.registry.set_server_status(UUID(int=301), 'Connected', expected_version=1) is False
            listing = await session.list_tools()
            assert len(listing.tools) == 4
        asyncio.run(external(gateway.url, values['key-a'], operation))
        assert all(row['outcome'] == 'denied' for row in router.audit.records.values())


@pytest.mark.parametrize('mode', ['bearer', 'header'])
def test_actual_wrong_upstream_credential_safe_error_and_status(mode):
    with environment() as (router, gateway, peers, values):
        async def operation(session):
            await session.list_tools()
            router.discovery.secrets.values[mode] = 'deliberately-wrong-fixture-credential'
            result = await session.call_tool(mode + '__service_info', {})
            assert result.isError and 'UPSTREAM_AUTH_FAILED' in result.content[0].text
            assert values[mode + '-token'] not in result.model_dump_json()
            async with httpx.AsyncClient(trust_env=False) as http:
                state = await http.post(gateway.url + '/test/state',
                    headers={'Authorization': 'Bearer ' + values['key-a']}, json={'action': 'refresh'})
                row = next(row for row in state.json()['servers'] if row['slug'] == mode)
                assert row['status'] == 'Unreachable' and row['status_reason'] == 'AUTH_FAILED'
        asyncio.run(external(gateway.url, values['key-a'], operation))
        state = httpx.get(peers[mode].url + '/test/control', trust_env=False).json()
        assert state['calls'] == 0
        assert len(router.audit.records) == 1
        assert next(iter(router.audit.records.values()))['error_code'] == 'UPSTREAM_AUTH_FAILED'
