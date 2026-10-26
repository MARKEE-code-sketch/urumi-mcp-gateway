"""Controlled composition evidence, not a live release or provider proof."""
import asyncio
from contextlib import contextmanager
import json
from threading import Event
from types import SimpleNamespace

import httpx
import psycopg
import pytest

from backend.api import BrowserConfig, create_api
from backend.chat.api import mount_chat
from backend.errors import unavailable
from backend.orchestrator import Config, Runtime, create_application
from scripts.m6.harness import build


WOO = 'http://test-woocommerce-mcp.test.svc.cluster.local:8000/mcp'
ORIGIN = 'https://dashboard.example.test'


def config():
    return Config('fixture-dsn', ORIGIN, ('dashboard.example.test',), (WOO,), WOO, 'test-secrets')


def environment():
    return dict(PGHOST='fixture', PGUSER='fixture', PGDATABASE='fixture', PGPASSWORD='fixture-password',
        URUMI_ORIGIN=ORIGIN, URUMI_ALLOWED_HOSTS='["dashboard.example.test"]',
        URUMI_INTERNAL_URLS='["' + WOO + '"]', URUMI_WOO_URL=WOO, URUMI_SECRET_NAMESPACE='test-secrets')


@pytest.mark.parametrize('key,value', [('URUMI_WORKERS','2'), ('GROQ_MODEL','different'),
    ('URUMI_ORIGIN','http://dashboard.example.test'), ('URUMI_ORIGIN',ORIGIN+'/path'),
    ('URUMI_ALLOWED_HOSTS','{}'), ('URUMI_ALLOWED_HOSTS','["*.example.test"]'),
    ('URUMI_ALLOWED_HOSTS','[]'), ('URUMI_INTERNAL_URLS','["http://127.0.0.1:8000/mcp"]'),
    ('URUMI_INTERNAL_URLS','["https://public.example.test/mcp"]'), ('URUMI_WOO_URL',WOO+'/different'),
    ('URUMI_SECRET_NAMESPACE','../other'), ('URUMI_LISTEN_HOST','192.168.1.1')])
def test_invalid_configuration_is_rejected_without_secret(key, value):
    inputs = environment()
    inputs[key] = value
    with pytest.raises(ValueError) as error:
        Config.from_environment(inputs)
    assert inputs['PGPASSWORD'] not in str(error.value)


def test_release_environment_uses_distinct_explicit_woo_url_and_hides_secrets():
    inputs = environment()
    inputs['GROQ_API_KEY'] = 'fixture-provider-secret'
    result = Config.from_environment(inputs)
    assert result.woo_url == WOO and result.provider_key == inputs['GROQ_API_KEY']
    assert inputs['PGPASSWORD'] not in repr(result) and inputs['GROQ_API_KEY'] not in repr(result)
    assert not Config.from_environment(environment()).provider_key


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class FixtureRuntime(Runtime):
    def build(self):
        tokens = {name: 'fixture-' + name for name in ('key-a','key-b','session-a','session-b','bearer-token','header-token')}
        self.gateway = build({}, tokens, hosts=self.config.hosts)
        self.router = self.gateway.app.state.router
        self.db = self.router.registry.db
        self.db.closed = False
        self.db.close = lambda: setattr(self.db, 'closed', True)
        self.versions, self.pending = [1, 2, 3], 0
        self.db.transaction = self.transaction
        identity = self.router.identity
        identity.check_csrf = lambda principal, value: None if value == 'fixture-csrf' else (_ for _ in ()).throw(unavailable())
        identity.me = lambda principal, token: {'role':principal.role}
        browser = BrowserConfig(self.config.origin)
        self.api = create_api(self.db, identity, None, None, None, None, browser, self.api_blocking.run)
        self.chat_calls = []
        async def blocking(function):
            return function()
        async def run(principal, message):
            self.chat_calls.append((principal.user_id, message))
            return {'state':'completed','answer':'Controlled composition reply.'}
        self.agent = SimpleNamespace(blocking=blocking, run=run, blocking_tasks=set())
        mount_chat(self.api.app, self.agent, identity, browser)
        self.starts = self.stops = 0
        start, stop = self.router.discovery.start, self.router.discovery.close
        async def counted_start():
            self.starts += 1
            await start()
        async def counted_stop():
            self.stops += 1
            await stop()
        self.router.discovery.start, self.router.discovery.close = counted_start, counted_stop

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, sql):
        if sql.startswith('SELECT version'):
            return Result([{'version':version} for version in self.versions])
        if sql.startswith('SELECT count'):
            return Result([{'n':self.pending}])
        raise AssertionError('Unexpected controlled SQL.')


def test_real_mcp_child_lifespan_exact_path_api_and_chat_composition():
    async def scenario():
        app = create_application(config(), FixtureRuntime)
        runtime = app.state.runtime
        async with app.router.lifespan_context(app):
            assert runtime.starts == 1 and runtime.stops == 0
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
                assert (await client.get('/health/ready')).status_code == 200
                assert (await client.get('/api/v1/auth/me')).status_code == 401
                assert (await client.get('/api/v1/auth/me',headers={'cookie':'urumi_session=fixture-session-a'})).json()['role'] == 'admin'
                assert (await client.post('/api/v1/chat', json={'message':'hello'},headers={'origin':ORIGIN})).status_code == 401
                response = await client.post('/api/v1/chat',json={'message':'hello'},headers={
                    'cookie':'urumi_session=fixture-session-a','origin':ORIGIN,'x-csrf-token':'fixture-csrf'})
                assert response.status_code == 200 and len(runtime.chat_calls) == 1
                # The actual MCP manager is running and receives an unchanged /mcp path.
                headers = {'Authorization':'Bearer fixture-key-a','Content-Type':'application/json',
                           'Accept':'application/json, text/event-stream'}
                response = await client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,
                    'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},
                    'clientInfo':{'name':'controlled-composition-test','version':'1'}}})
                assert response.status_code == 200 and response.json()['result']['serverInfo']['name'] == 'urumi-team-gateway'
                assert (await client.post('/mcp',json={})).status_code == 401
                assert (await client.get('/mcp',headers=headers)).status_code == 405
                assert (await client.post('/mcp/mcp',headers=headers,json={})).status_code == 404
                assert (await client.get('/api/v1/servers/00000000-0000-0000-0000-000000000001/tools')).status_code == 401
                assert not runtime.requests
        assert runtime.starts == runtime.stops == 1 and runtime.db.closed
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',['owner','schema','recovery','discovery'])
def test_readiness_fails_closed_but_liveness_survives(failure):
    async def scenario():
        app = create_application(config(), FixtureRuntime)
        async with app.router.lifespan_context(app):
            runtime = app.state.runtime
            if failure == 'owner': runtime.db.owned = False
            if failure == 'schema': runtime.versions = [1,2]
            if failure == 'recovery': runtime.pending = 1
            if failure == 'discovery':
                runtime.router.discovery.task.cancel()
                await asyncio.gather(runtime.router.discovery.task,return_exceptions=True)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
                assert (await client.get('/health/ready')).status_code == 503
                assert (await client.get('/health/live')).status_code == 200
    asyncio.run(scenario())


def test_startup_failure_cleans_partial_resources():
    class Failed(Runtime):
        def build(self):
            self.closed = []
            self.db = SimpleNamespace(close=lambda:self.closed.append('db'))
            self.secrets = SimpleNamespace(close=lambda:self.closed.append('secrets'))
            raise unavailable()
    async def scenario():
        app = create_application(config(), Failed)
        with pytest.raises(Exception):
            async with app.router.lifespan_context(app):
                raise AssertionError('Startup unexpectedly succeeded.')
        assert app.state.runtime.closed == ['secrets','db']
    asyncio.run(scenario())


def test_owner_monitor_fences_before_database_returns_and_never_reacquires():
    async def scenario():
        restarts = []
        runtime = Runtime(config(),restart=restarts.append)
        runtime.accepting = True
        attempts = []
        @contextmanager
        def connect():
            attempts.append(1)
            assert not runtime.accepting
            if len(attempts) < 3:
                raise psycopg.OperationalError('Controlled outage.')
            yield SimpleNamespace(execute=lambda sql:None)
        runtime.db = SimpleNamespace(check_owner=lambda:(_ for _ in ()).throw(unavailable()),connect=connect)
        await asyncio.wait_for(runtime.monitor_owner(.001),2)
        assert restarts == [75] and len(attempts) == 3 and not runtime.accepting
    asyncio.run(scenario())


def test_owner_monitor_retries_busy_adapter_while_fenced():
    async def scenario():
        restarts = []
        runtime = Runtime(config(), restart=restarts.append)
        runtime.accepting = True
        calls = []
        async def run(function):
            calls.append(function)
            assert len(calls) == 1 or not runtime.accepting
            if len(calls) <= 2:
                raise unavailable()
        runtime.lifecycle_blocking.run = run
        runtime.db = SimpleNamespace(check_owner=lambda: None)
        await asyncio.wait_for(runtime.monitor_owner(.001), 1)
        assert len(calls) == 3 and restarts == [75] and not runtime.accepting
        runtime.lifecycle_blocking.close()
        runtime.api_blocking.close()
    asyncio.run(scenario())


def test_undrained_worker_never_releases_owner_even_when_exit_callback_returns():
    async def scenario():
        restarts, closed = [], []
        runtime = Runtime(config(),restart=restarts.append,drain_timeout=.01)
        runtime.db = SimpleNamespace(close=lambda:closed.append('db'))
        pending = asyncio.get_running_loop().create_future()
        runtime.agent = SimpleNamespace(blocking_tasks={pending})
        with pytest.raises(RuntimeError,match='Undrained'):
            await runtime.close()
        assert runtime.owner_retained and not closed and restarts == [75]
        pending.set_result(None)
    asyncio.run(scenario())


def test_shutdown_waits_for_actual_worker_before_owner_close():
    async def scenario():
        runtime = Runtime(config(),drain_timeout=1)
        pending = asyncio.get_running_loop().create_future()
        runtime.agent = SimpleNamespace(blocking_tasks={pending})
        runtime.db = SimpleNamespace(close=lambda:None if pending.done() else pytest.fail('Owner released early.'))
        asyncio.get_running_loop().call_later(.03,pending.set_result,None)
        await runtime.close()
        assert pending.done() and not runtime.owner_retained
    asyncio.run(scenario())


@pytest.mark.parametrize('endpoint',['sync','login'])
def test_cancelled_real_api_thread_is_drained_before_database_owner_release(endpoint):
    async def scenario():
        entered, release, finished = Event(), Event(), Event()
        runtime = FixtureRuntime(config(),request_timeout=.01,drain_timeout=1)
        app = create_application(config(),lambda _:runtime)
        async with app.router.lifespan_context(app):
            identity = runtime.router.identity
            def slow(*args):
                entered.set()
                assert release.wait(2)
                finished.set()
                return ({'csrf_token':'fixture-csrf'},'fixture-session-a') if endpoint == 'login' else {'role':'admin'}
            identity.me = identity.login = slow
            original_close = runtime.db.close
            def close():
                assert finished.is_set(), 'The actual account API worker outlived database ownership.'
                original_close()
            runtime.db.close = close
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
                if endpoint == 'login':
                    request = asyncio.create_task(client.post('/api/v1/auth/login',
                        json={'email':'fixture@example.test','password':'fixture-password'},headers={'origin':ORIGIN}))
                else:
                    request = asyncio.create_task(client.get('/api/v1/auth/me',headers={'cookie':'urumi_session=fixture-session-a'}))
                while not entered.is_set():
                    await asyncio.sleep(.001)
                request.cancel()
                await asyncio.gather(request,return_exceptions=True)
                assert not finished.is_set() and runtime.api_blocking.active
                asyncio.get_running_loop().call_later(.03,release.set)
        assert runtime.db.closed and finished.is_set()
    asyncio.run(scenario())


def test_failed_owner_monitor_does_not_skip_resource_cleanup():
    async def scenario():
        runtime = Runtime(config())
        closed = []
        runtime.db = SimpleNamespace(close=lambda:closed.append('db'))
        async def failed():
            raise RuntimeError('Controlled monitor failure.')
        runtime.monitor = asyncio.create_task(failed())
        await asyncio.sleep(0)
        with pytest.raises(RuntimeError,match='cleanup'):
            await runtime.close()
        assert closed == ['db']
    asyncio.run(scenario())


def test_routed_api_and_mcp_keep_their_separate_body_budgets():
    async def scenario():
        app = create_application(config(),FixtureRuntime)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url=ORIGIN) as client:
                assert (await client.post('/api/v1/chat',json={'message':'x'*17000})).status_code == 422
                message = {'jsonrpc':'2.0','id':1,'method':'initialize','params':{
                    'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'x'*20000,'version':'1'}}}
                headers = {'authorization':'Bearer fixture-key-a','accept':'application/json, text/event-stream'}
                assert 16384 < len(json.dumps(message).encode()) < 65536
                response = await client.post('/mcp',headers=headers,json=message)
                assert response.status_code == 200 and 'serverInfo' in response.json()['result']
                message['params']['clientInfo']['name'] = 'x'*65536
                assert (await client.post('/mcp',headers=headers,json=message)).status_code == 413
    asyncio.run(scenario())
