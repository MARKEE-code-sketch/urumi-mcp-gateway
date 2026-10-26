"""One real dependency graph and one owner for its lifetime."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
import os
import re
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from backend.api import BrowserConfig, create_api
from backend.audit.records import Audit
from backend.chat.agent import ChatAgent
from backend.chat.api import mount_chat
from backend.chat.llm_client import GroqClient
from backend.db.database import Database
from backend.errors import PlatformError, unavailable
from backend.gateway.discovery import Discovery
from backend.gateway.common import Blocking
from backend.gateway.router import Router
from backend.gateway.server import create_app as create_gateway
from backend.gateway.upstream_client import UpstreamClient
from backend.identity.api_keys import ApiKeys
from backend.identity.auth import Identity
from backend.identity.members import Members
from backend.registry.secret_store import SecretStore
from backend.registry.servers import Registry, validate_url


@dataclass(frozen=True)
class Config:
    dsn: str = field(repr=False)
    origin: str
    hosts: tuple[str, ...]
    internal_urls: tuple[str, ...]
    woo_url: str
    secret_namespace: str
    listen_host: str = '0.0.0.0'
    provider_key: str = field(default='', repr=False)

    def __post_init__(self):
        BrowserConfig(self.origin, listen_host=self.listen_host)
        if not self.hosts or any(not isinstance(host, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host) for host in self.hosts):
            raise ValueError('Exact allowed hostnames are required.')
        if urlsplit(self.origin).hostname not in self.hosts:
            raise ValueError('Browser hostname must be allowed.')
        if not isinstance(self.secret_namespace, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', self.secret_namespace):
            raise ValueError('Credential namespace is required.')
        if self.listen_host not in ('0.0.0.0', '127.0.0.1', 'localhost'):
            raise ValueError('A supported listener is required.')
        if self.woo_url not in self.internal_urls:
            raise ValueError('Woo URL must be explicitly allowlisted.')
        for url in self.internal_urls:
            parsed = urlsplit(url)
            if parsed.scheme != 'http' or not parsed.hostname or not parsed.hostname.endswith('.svc.cluster.local'):
                raise ValueError('Internal URLs must name exact cluster Services.')
            validate_url(url, self.internal_urls)

    @classmethod
    def from_environment(cls, environment=None):
        env = os.environ if environment is None else environment
        try:
            if env.get('URUMI_WORKERS', '1') != '1' or env.get('GROQ_MODEL', GroqClient.model) != GroqClient.model:
                raise ValueError()
            hosts = json.loads(env['URUMI_ALLOWED_HOSTS'])
            urls = json.loads(env['URUMI_INTERNAL_URLS'])
            if not isinstance(hosts, list) or not isinstance(urls, list):
                raise ValueError()
            dsn = psycopg.conninfo.make_conninfo(host=env['PGHOST'], port=env.get('PGPORT', '5432'),
                user=env['PGUSER'], dbname=env['PGDATABASE'], password=env['PGPASSWORD'])
            return cls(dsn, env['URUMI_ORIGIN'], tuple(hosts), tuple(urls), env['URUMI_WOO_URL'],
                       env['URUMI_SECRET_NAMESPACE'], env.get('URUMI_LISTEN_HOST', '0.0.0.0'),
                       env.get('GROQ_API_KEY', ''))
        except Exception:
            raise ValueError('Release configuration is invalid; check the documented inputs.') from None


def initialize_woocommerce(db, url, allowlist):
    """A durable marker survives edits and deletion; both inserts are atomic."""
    normalized = validate_url(url, allowlist)
    db.check_owner()
    with db.transaction() as connection:
        if connection.execute("SELECT server_id FROM builtin_initializations WHERE name='woocommerce'").fetchone():
            return
        row = connection.execute("SELECT id FROM servers WHERE slug='woocommerce'").fetchone()
        server_id = row['id'] if row else uuid4()
        if not row:
            connection.execute("""INSERT INTO servers(id,name,slug,url,enabled,status,status_reason,auth_type)
                VALUES(%s,'WooCommerce','woocommerce',%s,true,'Unreachable','NOT_CHECKED','none')""",
                (server_id, normalized))
        connection.execute("INSERT INTO builtin_initializations(name,server_id) VALUES('woocommerce',%s)", (server_id,))


class Runtime:
    def __init__(self, config, restart=os._exit, drain_timeout=15, request_timeout=130):
        self.config, self.restart = config, restart
        self.drain_timeout, self.request_timeout = drain_timeout, request_timeout
        self.db = self.secrets = self.provider = self.router = self.agent = None
        self.gateway = self.api = self.gateway_lifespan = self.monitor = None
        self.initialized = self.accepting = False
        self.requests = set()
        self.owner_retained = False
        self.api_blocking, self.lifecycle_blocking = Blocking(8), Blocking(2)

    def build(self):
        self.db = Database(self.config.dsn)
        self.db.migrate()
        self.db.acquire_owner()
        identity = Identity(self.db)
        with self.db.transaction() as connection:
            owner = connection.execute('SELECT id FROM installation').fetchone()['id']
        self.secrets = SecretStore(self.config.secret_namespace, owner)
        registry = Registry(self.db, self.secrets, self.config.internal_urls)
        audit = Audit(self.db, identity)
        audit.recover()
        if registry.recover():
            raise unavailable()
        initialize_woocommerce(self.db, self.config.woo_url, self.config.internal_urls)
        upstream = UpstreamClient(self.config.internal_urls)
        discovery = Discovery(identity, registry, self.secrets, upstream)
        self.router = Router(identity, registry, audit, discovery, upstream)
        self.provider = GroqClient(self.config.provider_key)
        self.agent = ChatAgent(self.provider, self.router, identity)
        browser = BrowserConfig(self.config.origin, listen_host=self.config.listen_host)
        self.api = create_api(self.db, identity, Members(self.db, browser.origin),
                              ApiKeys(self.db, identity), registry, audit, browser, self.api_blocking.run)
        mount_chat(self.api.app, self.agent, identity, browser)
        self.gateway = create_gateway(self.router, ApiKeys(self.db, identity), identity,
                                      hosts=self.config.hosts, origins=(self.config.origin,))

    async def start(self):
        await self.lifecycle_blocking.run(self.build)
        child = self.gateway.app
        context = child.router.lifespan_context(child)
        await context.__aenter__()
        self.gateway_lifespan = context
        self.monitor = asyncio.create_task(self.monitor_owner())
        self.initialized = self.accepting = True

    async def monitor_owner(self, interval=2):
        while True:
            await asyncio.sleep(interval)
            try:
                await self.lifecycle_blocking.run(self.db.check_owner)
            except Exception:
                self.accepting = False
                break
        while True:
            try:
                def reachable():
                    with self.db.connect() as connection:
                        connection.execute('SELECT 1')
                await self.lifecycle_blocking.run(reachable)
            except (psycopg.Error, PlatformError):
                await asyncio.sleep(interval)
                continue
            self.restart(75)
            return

    def check_ready(self):
        if not self.initialized or not self.accepting:
            raise unavailable()
        self.db.check_owner()
        with self.db.transaction() as connection:
            versions = connection.execute('SELECT version FROM schema_version ORDER BY version').fetchall()
            if [row['version'] for row in versions] != [1, 2, 3] or connection.execute(
                    'SELECT count(*) AS n FROM secret_operations').fetchone()['n']:
                raise unavailable()
        if self.router.discovery.task is None or self.router.discovery.task.done():
            raise unavailable()

    def workers(self):
        values = {task for group in (self.api_blocking.active, self.lifecycle_blocking.active)
                  for task in group if not task.done()}
        if self.router:
            for group in (self.router.blocking.active, self.router.finalizers.active,
                          self.router.locks.active, self.router.pending_finalizers,
                          self.router.discovery.blocking.active):
                values.update(task for task in group if not task.done())
        if self.agent:
            values.update(task for task in self.agent.blocking_tasks if not task.done())
        return values

    async def drain(self, tasks, timeout):
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    async def close(self):
        self.accepting = self.initialized = False
        cleanup_error = None
        if self.monitor:
            self.monitor.cancel()
            try:
                await self.monitor
            except asyncio.CancelledError:
                pass
            except Exception as error:
                cleanup_error = error
        await self.drain(self.lifecycle_blocking.active, self.drain_timeout)
        if any(not task.done() for task in self.lifecycle_blocking.active):
            self.owner_retained = True
            self.restart(75)
            raise RuntimeError('Undrained startup work requires process termination.')
        await self.drain(self.requests, self.request_timeout)
        for task in self.requests:
            if not task.done():
                task.cancel()
        if self.router:
            await self.drain(self.router.pending_finalizers, 2)
        try:
            if self.gateway_lifespan:
                await self.gateway_lifespan.__aexit__(None, None, None)
            elif self.router:
                try:
                    await self.router.discovery.close()
                finally:
                    await self.router.close()
        except Exception as error:
            cleanup_error = error
        finally:
            self.gateway_lifespan = None
        self.api_blocking.close()
        self.lifecycle_blocking.close()
        # Cancellation cannot stop Python threads. Keep the owner until they stop.
        deadline = asyncio.get_running_loop().time() + self.drain_timeout
        while self.workers() or any(not task.done() for task in self.requests):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.owner_retained = True
                self.restart(75)
                raise RuntimeError('Undrained work requires process termination.')
            await asyncio.sleep(min(.01, remaining))
        try:
            if self.provider:
                await self.provider.close()
        finally:
            try:
                if self.secrets:
                    await run_in_threadpool(self.secrets.close)
            finally:
                if self.db:
                    await run_in_threadpool(self.db.close)
        if cleanup_error:
            raise RuntimeError('Runtime cleanup did not complete normally.') from None


def create_application(config, runtime_factory=Runtime):
    runtime = runtime_factory(config)

    @asynccontextmanager
    async def lifespan(app):
        try:
            await runtime.start()
            yield
        finally:
            await runtime.close()

    async def live(request):
        return JSONResponse({'status': 'live'}, headers={'Cache-Control': 'no-store'})

    async def ready(request):
        try:
            await runtime.lifecycle_blocking.run(runtime.check_ready)
            return JSONResponse({'status': 'ready'}, headers={'Cache-Control': 'no-store'})
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503, headers={'Cache-Control': 'no-store'})

    class Endpoint:
        def __init__(self, gateway):
            self.gateway = gateway

        async def __call__(self, scope, receive, send):
            if not runtime.accepting:
                return await JSONResponse({'error': 'Service is unavailable.'}, status_code=503)(scope, receive, send)
            task = asyncio.current_task()
            runtime.requests.add(task)
            try:
                target = runtime.gateway if self.gateway else runtime.api
                await target(scope, receive, send)
            finally:
                runtime.requests.discard(task)

    app = Starlette(routes=[Route('/health/live', live), Route('/health/ready', ready),
        Route('/mcp', Endpoint(True), methods=['GET', 'POST', 'DELETE', 'PUT', 'PATCH', 'OPTIONS', 'HEAD']),
        Route('/api/v1/servers/{server_id}/tools', Endpoint(True), methods=['GET']),
        Mount('/', app=Endpoint(False))], lifespan=lifespan)
    app.state.runtime = runtime
    return app
