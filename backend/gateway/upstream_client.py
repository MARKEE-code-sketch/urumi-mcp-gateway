"""Short-lived MCP sessions with checked numeric dialing and bounded streams."""
import asyncio
from contextlib import asynccontextmanager
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urlsplit

import dns.asyncresolver
import httpcore
import httpx
from jsonschema.validators import validator_for
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from backend.gateway.common import GatewayError
from backend.registry.servers import validate_url


def depth(value, maximum=32):
    stack = [(value, 0)]
    while stack:
        item, level = stack.pop()
        if level > maximum:
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        if isinstance(item, dict):
            if '$ref' in item and not str(item['$ref']).startswith('#'):
                raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
            stack.extend((v, level + 1) for v in item.values())
        elif isinstance(item, list):
            stack.extend((v, level + 1) for v in item)


def redact(value, secret):
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]')
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    if isinstance(value, dict):
        return {redact(k, secret): redact(v, secret) for k, v in value.items()}
    return value


class CheckedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, url, allowlist, resolver=None, backend=None, dns_slots=None):
        self.url = validate_url(url, allowlist)
        parsed = urlsplit(self.url)
        self.host, self.port = parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80)
        self.internal = self.url in allowlist
        self.resolver = resolver or dns.asyncresolver.Resolver()
        self.backend = backend or httpcore.AnyIOBackend()
        self.dns_slots = dns_slots or asyncio.Semaphore(4)

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != self.host or port != self.port or local_address is not None:
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        try:
            addresses = [ipaddress.ip_address(host)]
        except ValueError:
            async with self.dns_slots:
                answers = await self.resolver.resolve_name(host, family=socket.AF_UNSPEC,
                                                           lifetime=1, search=False)
            addresses = [ipaddress.ip_address(item) for item in answers.addresses()]
        if not addresses or (not self.internal and any(not item.is_global for item in addresses)):
            raise GatewayError('UPSTREAM_UNAVAILABLE')
        last = None
        for address in addresses:
            try:
                return await self.backend.connect_tcp(str(address), port, timeout=timeout,
                                                       socket_options=socket_options)
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as error:
                last = error
        raise last or GatewayError('UPSTREAM_UNAVAILABLE')

    async def connect_unix_socket(self, *args, **kwargs):
        raise GatewayError('UPSTREAM_UNAVAILABLE')

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class Budget:
    def __init__(self):
        self.total = 0


class LimitedStream(httpx.AsyncByteStream):
    def __init__(self, stream, budget, sse=False):
        self.stream, self.budget, self.sse = stream, budget, sse

    async def __aiter__(self):
        count, pending = 0, b''
        async for chunk in self.stream:
            count += len(chunk)
            self.budget.total += len(chunk)
            if count > 2 * 1024**2 or self.budget.total > 8 * 1024**2:
                raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
            if self.sse:
                parts = re.split(rb'\r?\n\r?\n', pending + chunk)
                if any(len(part) > 256 * 1024 for part in parts):
                    raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                pending = parts[-1]
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class CheckedTransport(httpx.AsyncBaseTransport):
    def __init__(self, url, allowlist, budget, resolver=None, ssl_context=None, backend=None, dns_slots=None):
        self.url = url
        self.budget = budget
        self.pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_context or ssl.create_default_context(),
            max_connections=3, max_keepalive_connections=3, retries=0, http2=False,
            network_backend=CheckedBackend(url, allowlist, resolver, backend, dns_slots))

    async def handle_async_request(self, request):
        if str(request.url) != self.url:
            raise GatewayError('UPSTREAM_UNAVAILABLE')
        if int(request.headers.get('content-length', '0')) > 65536:
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        try:
            response = await self.pool.handle_async_request(httpcore.Request(
                method=request.method, url=httpcore.URL(scheme=request.url.raw_scheme,
                    host=request.url.raw_host, port=request.url.port, target=request.url.raw_path),
                headers=request.headers.raw, content=request.stream, extensions=request.extensions))
        except httpcore.TimeoutException:
            raise GatewayError('UPSTREAM_TIMEOUT', 'timeout') from None
        except (httpcore.NetworkError, httpcore.ProtocolError):
            raise GatewayError('UPSTREAM_UNAVAILABLE') from None
        headers = httpx.Headers(response.headers)
        if response.status in (401, 403):
            await response.stream.aclose()
            raise GatewayError('UPSTREAM_AUTH_FAILED')
        if 300 <= response.status < 400 or headers.get('content-encoding', 'identity') != 'identity':
            await response.stream.aclose()
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        return httpx.Response(response.status, headers=headers,
            stream=LimitedStream(response.stream, self.budget,
                                 'text/event-stream' in headers.get('content-type', '')),
            extensions=response.extensions)

    async def aclose(self):
        await self.pool.aclose()


class UpstreamClient:
    def __init__(self, allowlist, resolver=None, ssl_context=None):
        self.allowlist = set(allowlist)
        self.resolver, self.ssl_context = resolver, ssl_context
        self.dns_slots = asyncio.Semaphore(4)

    @asynccontextmanager
    async def session(self, row, secret):
        headers = {'Accept-Encoding': 'identity'}
        if row['auth_type'] == 'bearer':
            headers['Authorization'] = 'Bearer ' + secret
        elif row['auth_type'] == 'header':
            headers[row['header_name']] = secret
        transport = CheckedTransport(row['url'], self.allowlist, Budget(), self.resolver,
                                     self.ssl_context, dns_slots=self.dns_slots)
        async with httpx.AsyncClient(transport=transport, headers=headers,
                                     timeout=httpx.Timeout(2, read=10), follow_redirects=False,
                                     trust_env=False) as client:
            async with streamable_http_client(row['url'], http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session

    async def discover(self, row, secret):
        tools, cursors, cursor = [], set(), None
        async with self.session(row, secret) as session:
            for _ in range(20):
                result = await session.list_tools(cursor=cursor)
                tools.extend(result.tools)
                if len(tools) > 200:
                    raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                if not result.nextCursor:
                    return tools
                if result.nextCursor in cursors:
                    raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                cursor = result.nextCursor
                cursors.add(cursor)
        raise GatewayError('UPSTREAM_PROTOCOL_ERROR')

    async def call(self, row, secret, name, arguments, before_send):
        async with self.session(row, secret) as session:
            await before_send()
            # SDK call_tool would fetch/validate unchecked output schemas on the event loop.
            result = await session.send_request(types.ClientRequest(types.CallToolRequest(
                method='tools/call', params=types.CallToolRequestParams(name=name, arguments=arguments))),
                types.CallToolResult)
        payload = result.model_dump(mode='json', exclude_none=True)
        depth(payload)
        # Binary blocks cannot be made credential-safe by replacing base64 text.
        if secret and any(block.get('type') in ('image', 'audio') or
                          isinstance(block.get('resource'), dict) and 'blob' in block['resource']
                          for block in payload.get('content', [])):
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        return type(result).model_validate(redact(payload, secret))
