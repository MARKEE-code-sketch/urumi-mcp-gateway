import asyncio
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from backend.chat.agent import ChatAgent
from backend.chat.api import mount_chat
from backend.chat.llm_client import ChatFailure, GroqClient
from scripts.m7.fixtures import GatewayFixture, IdentityFixture, ScriptedProvider, tool_call

ANSWER = {'role': 'assistant', 'content': 'Fixture answer.'}


class Bytes(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


def provider_response(message=None, reason='stop'):
    return json.dumps({'choices': [{'message': message or ANSWER, 'finish_reason': reason}]}).encode()


@pytest.mark.parametrize('status,code', [(401, 'PROVIDER_AUTH_FAILED'), (403, 'PROVIDER_AUTH_FAILED'),
    (429, 'PROVIDER_RATE_LIMIT'), (500, 'PROVIDER_UNAVAILABLE'), (302, 'PROVIDER_UNAVAILABLE')])
def test_provider_statuses_no_retry_or_raw_error(status, code):
    async def scenario():
        requests = []
        async def handler(request):
            requests.append(request)
            return httpx.Response(status, stream=Bytes([b'credential SECRET exception']))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = GroqClient('SECRET', http)
            with pytest.raises(ChatFailure) as error:
                await client.complete([], [])
            assert error.value.code == code and 'SECRET' not in error.value.message
            assert ('rate limit' in error.value.message) is (status == 429)
            assert len(requests) == 1 and requests[0].url.host == 'api.groq.com'
    asyncio.run(scenario())


@pytest.mark.parametrize('headers,expected', [
    ({'retry-after': '0'}, 0), ({'retry-after': '0.01'}, .01),
    ({'retry-after': '60'}, 60), ({'x-ratelimit-reset-tokens': '1.5s'}, 1.5),
    ({}, None), ({'retry-after': '-1'}, None), ({'retry-after': 'NaN'}, None),
    ({'retry-after': 'inf'}, None), ({'retry-after': '60.01'}, None),
    ({'retry-after': 'untrusted header value'}, None),
    ({'x-ratelimit-reset-tokens': '-1s'}, None),
    ({'x-ratelimit-reset-tokens': '61s'}, None),
])
def test_rate_limit_wait_hint_is_bounded_header_data_without_reading_body(headers, expected):
    class UnreadBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError('The 429 body must not be read')
            yield b'unsafe diagnostic SECRET'
    async def scenario():
        requests = []
        async def handler(request):
            requests.append(request)
            return httpx.Response(429, headers=headers, stream=UnreadBody())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(ChatFailure) as error:
                await GroqClient('SECRET', http).complete([], [])
            assert error.value.code == 'PROVIDER_RATE_LIMIT'
            assert error.value.retry_after == expected
            assert 'SECRET' not in error.value.message and 'untrusted header value' not in error.value.message
            assert len(requests) == 1
    asyncio.run(scenario())


def test_non_rate_limit_response_does_not_carry_a_retry_hint():
    async def scenario():
        async def handler(request):
            return httpx.Response(500, headers={'retry-after': '0.01'}, stream=Bytes([b'SECRET']))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(ChatFailure) as error:
                await GroqClient('SECRET', http).complete([], [])
            assert error.value.code == 'PROVIDER_UNAVAILABLE' and error.value.retry_after is None
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['length', 'invalid', 'compressed', 'large', 'key_echo'])
def test_provider_invalid_compressed_oversized_and_truncated_reply(kind):
    async def scenario():
        body, headers = provider_response(), {}
        if kind == 'length': body = provider_response(tool_call(), 'length')
        if kind == 'invalid': body = b'not json'
        if kind == 'compressed': headers['content-encoding'] = 'gzip'
        if kind == 'large': body = b'x' * (128 * 1024 + 1)
        if kind == 'key_echo': body = provider_response(dict(ANSWER, content='SECRET'))
        async def handler(request):
            return httpx.Response(200, headers=headers, stream=Bytes([body]))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = GroqClient('SECRET', http)
            with pytest.raises(ChatFailure):
                await client.complete([], [])
    asyncio.run(scenario())


def test_provider_final_request_has_no_tools_and_payload_redacts_key():
    async def scenario():
        observed = []
        async def handler(request):
            observed.append(json.loads(request.content))
            assert request.headers['accept-encoding'] == 'identity'
            return httpx.Response(200, stream=Bytes([provider_response()]))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = GroqClient('SECRET', http)
            await client.complete([{'role': 'user', 'content': 'SECRET'}], [{'type': 'function'}], final=True)
            assert observed[0]['tool_choice'] == 'none' and 'tools' not in observed[0]
            assert observed[0]['messages'][0]['content'] == '[REDACTED]'
            with pytest.raises(ChatFailure):
                await client.complete([{'content': 'x' * (256 * 1024)}], [])
            assert len(observed) == 1
    asyncio.run(scenario())


def make_app(replies=None):
    identity = IdentityFixture()
    gateway = GatewayFixture(identity)
    provider = ScriptedProvider(replies or [ANSWER])
    agent = ChatAgent(provider, gateway, identity)
    app = FastAPI()
    mount_chat(app, agent, identity, SimpleNamespace(origin='https://gateway.example.test'))
    @app.get('/health/live')
    async def health():
        return {'status': 'live'}
    return app, agent, provider, gateway, identity


@pytest.mark.parametrize('case,status', [('no_cookie', 401), ('bearer', 401), ('origin', 403), ('csrf', 403),
    ('blank', 422), ('extra', 422), ('large', 422), ('surrogate', 422), ('body_limit', 422), ('non_string', 422)])
def test_chat_api_protection_and_input_no_inference(case, status):
    async def scenario():
        app, agent, provider, gateway, identity = make_app()
        headers = {'origin': 'https://gateway.example.test', 'x-csrf-token': 'fixture-csrf', 'cookie': 'urumi_session=session-a'}
        body = {'message': 'hello'}
        if case in ('no_cookie', 'bearer'): headers.pop('cookie')
        if case == 'bearer': headers['authorization'] = 'Bearer personal-key'
        if case == 'origin': headers['origin'] = 'https://evil.test'
        if case == 'csrf': headers['x-csrf-token'] = 'wrong'
        if case == 'blank': body['message'] = ' '
        if case == 'extra': body['user_id'] = str(identity.b.user_id)
        if case == 'large': body['message'] = 'x' * 4001
        if case == 'surrogate': body['message'] = '\ud800'
        if case == 'body_limit': body['message'] = 'x' * 17000
        if case == 'non_string': body['message'] = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://gateway.example.test') as client:
            response = await client.post('/api/v1/chat', headers=headers, content=json.dumps(body))
        assert response.status_code == status and response.headers['cache-control'] == 'no-store'
        assert provider.requests == [] and gateway.calls == []
    asyncio.run(scenario())


def test_valid_api_request_and_blocking_identity_does_not_block_health():
    async def scenario():
        app, agent, provider, gateway, identity = make_app()
        original = identity.session
        def slow(token):
            time.sleep(0.2)
            return original(token)
        identity.session = slow
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://gateway.example.test') as client:
            pending = asyncio.create_task(client.post('/api/v1/chat', json={'message': 'hello'}, headers={
                'origin': 'https://gateway.example.test', 'x-csrf-token': 'fixture-csrf', 'cookie': 'urumi_session=session-a'}))
            await asyncio.sleep(0.02)
            started = time.monotonic()
            assert (await client.get('/health/live')).status_code == 200
            assert time.monotonic() - started < 0.1
            response = await pending
            assert response.status_code == 200 and response.json()['state'] == 'completed'
    asyncio.run(scenario())


def test_actual_asgi_disconnect_cancels_model_and_releases_slot():
    async def scenario():
        entered, canceled = asyncio.Event(), asyncio.Event()
        async def stall(*args):
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                canceled.set()
        app, agent, provider, gateway, identity = make_app([stall])
        body = json.dumps({'message': 'hello'}).encode()
        first = True
        async def receive():
            nonlocal first
            if first:
                first = False
                return {'type': 'http.request', 'body': body, 'more_body': False}
            await entered.wait()
            return {'type': 'http.disconnect'}
        sent = []
        async def send(message):
            sent.append(message)
        scope = {'type': 'http', 'http_version': '1.1', 'method': 'POST', 'path': '/api/v1/chat',
                 'raw_path': b'/api/v1/chat', 'query_string': b'', 'scheme': 'https',
                 'server': ('gateway.example.test', 443), 'client': ('127.0.0.1', 1234),
                 'headers': [(b'origin', b'https://gateway.example.test'), (b'x-csrf-token', b'fixture-csrf'),
                             (b'cookie', b'urumi_session=session-a'), (b'content-type', b'application/json')]}
        await asyncio.wait_for(app(scope, receive, send), 2)
        assert canceled.is_set() and agent.active == 0 and gateway.calls == []
    asyncio.run(scenario())


def test_real_tcp_provider_read_timeout_has_one_bounded_request():
    class Handler(BaseHTTPRequestHandler):
        calls = 0
        def do_POST(self):
            Handler.calls += 1
            self.rfile.read(int(self.headers['content-length']))
            time.sleep(0.2)
            try:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(provider_response())
            except (BrokenPipeError, ConnectionResetError):
                pass
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    class LocalTransport(httpx.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx.AsyncHTTPTransport()
        async def handle_async_request(self, request):
            request.url = httpx.URL(f'http://127.0.0.1:{server.server_port}/')
            return await self.inner.handle_async_request(request)
        async def aclose(self):
            await self.inner.aclose()
    async def scenario():
        async with httpx.AsyncClient(transport=LocalTransport(), timeout=0.05) as http:
            client = GroqClient('fixture-key', http)
            started = time.monotonic()
            with pytest.raises(ChatFailure) as error:
                await client.complete([], [])
            assert error.value.code == 'PROVIDER_TIMEOUT' and time.monotonic() - started < 1
            assert Handler.calls == 1
    try:
        asyncio.run(scenario())
    finally:
        server.shutdown()
        server.server_close()
