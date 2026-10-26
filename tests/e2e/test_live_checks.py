"""Safety/transport contracts only; these are not live acceptance evidence."""
import asyncio
import ssl

import httpx
from mcp import types
import pytest

from scripts.m10.live_checks import (Browser, CheckFailed, ensure_server,
                                    origin_value, result_data, run_owned_demo)


@pytest.mark.parametrize('value', ['http://dashboard.test', 'https://dashboard.test/',
    'https://user:password@dashboard.test', 'https://dashboard.test?key=secret',
    'https://dashboard.test#secret'])
def test_origin_rejects_credentials_http_and_extra_url_parts(value):
    with pytest.raises(ValueError):
        origin_value(value)


def test_no_live_mutations_without_explicit_flag():
    with pytest.raises(CheckFailed, match='explicit_mutation_flag_required'):
        asyncio.run(run_owned_demo({}))


def test_browser_cookie_and_csrf_are_used_without_bearer_or_redirects():
    seen = []
    def handle(request):
        seen.append(request)
        if request.url.path.endswith('/login'):
            return httpx.Response(200, json={'user': {'id': 'owned-user', 'role': 'member'},
                'csrf_token': 'private-csrf'}, headers={
                'Set-Cookie': 'urumi_session=private-session; Path=/; HttpOnly; Secure; SameSite=Lax'})
        assert request.headers['x-csrf-token'] == 'private-csrf'
        assert 'urumi_session=private-session' in request.headers['cookie']
        assert 'authorization' not in request.headers
        assert request.headers['origin'] == 'https://dashboard.test'
        return httpx.Response(302, headers={'location': 'https://elsewhere.test'})
    async def check():
        browser = Browser('https://dashboard.test', ssl.create_default_context(), httpx.MockTransport(handle))
        try:
            await browser.login('owned@example.test', 'private-password')
            with pytest.raises(CheckFailed, match='api_status_200'):
                await browser.request('GET', '/api/v1/auth/me')
            with pytest.raises(CheckFailed, match='api_path'):
                await browser.request('GET', 'https://elsewhere.test/api/v1/auth/me')
        finally:
            await browser.close()
    asyncio.run(check())
    assert len(seen) == 2


def test_mcp_error_payload_never_becomes_exception_text():
    result = types.CallToolResult(isError=True, content=[types.TextContent(type='text', text='private-error-body')])
    with pytest.raises(CheckFailed, match='mcp_tool_error') as error:
        result_data(result)
    assert 'private-error-body' not in str(error.value)


def test_result_uses_structured_content_and_single_json_fallback():
    assert result_data(types.CallToolResult(structuredContent={'items': []}, content=[])) == {'items': []}
    assert result_data(types.CallToolResult(content=[types.TextContent(type='text', text='{"items": []}')])) == {'items': []}


def test_registration_never_overwrites_an_existing_mismatched_server():
    class Existing:
        calls = 0
        async def request(self, *args):
            self.calls += 1
            return {'items': [{'slug': 'inventory', 'url': 'http://different/mcp', 'enabled': True}]}
    browser = Existing()
    with pytest.raises(CheckFailed, match='existing_server_mismatch'):
        asyncio.run(ensure_server(browser, 'inventory', 'Inventory', 'http://expected/mcp'))
    assert browser.calls == 1
