"""Stateless external MCP and session-authenticated tool previews."""
import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
import json
import logging
from uuid import UUID, uuid4

from mcp import McpError, types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.errors import PlatformError
from backend.gateway.context import get_context, request_context


_principal = ContextVar('gateway_principal', default=None)


def safe_error(error):
    context = get_context()
    request_id = context.request_id if context else uuid4()
    return JSONResponse({'error': {'code': error.code, 'message': error.message,
                                  'request_id': str(request_id)}}, status_code=error.status,
                        headers={'Cache-Control': 'no-store'})


class Guard:
    def __init__(self, app, keys, router, hosts, origins):
        self.app, self.keys, self.router = app, keys, router
        self.hosts, self.origins = set(hosts), set(origins)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'] != '/mcp':
            return await self.app(scope, receive, send)
        headers = dict(scope['headers'])
        host = headers.get(b'host', b'').decode('ascii', errors='ignore').split(':')[0]
        if host not in self.hosts or b'origin' in headers and headers[b'origin'].decode(errors='ignore') not in self.origins:
            return await JSONResponse({'error': 'Request rejected.'}, status_code=403)(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while True:
                    message = await receive()
                    if message['type'] == 'http.disconnect':
                        return
                    body.extend(message.get('body', b''))
                    if len(body) > 65536:
                        return await JSONResponse({'error': 'Request too large.'}, status_code=413)(scope, receive, send)
                    if not message.get('more_body'):
                        break
        except TimeoutError:
            return await JSONResponse({'error': 'Request timed out.'}, status_code=408)(scope, receive, send)
        principal = None
        with request_context() as context:
            try:
                value = headers.get(b'authorization', b'').decode('ascii', errors='ignore')
                raw = value[7:] if value.startswith('Bearer ') else ''
                principal = await self.router.blocking.run(self.keys.validate, raw)
            except PlatformError as error:
                try:
                    parsed = json.loads(body)
                    name = parsed.get('params', {}).get('name') if parsed.get('method') == 'tools/call' else None
                    if isinstance(name, str) and 1 <= len(name) <= 64:
                        await self.router.blocking.run(self.router.audit.record_denial, context.request_id,
                            error.principal, None, name, 'KEY_REVOKED' if error.code == 'KEY_REVOKED' else 'UNAUTHENTICATED')
                except PlatformError as audit_error:
                    error = audit_error
                except (ValueError, AttributeError, TypeError):
                    pass
                return await safe_error(error)(scope, receive, send)
            if scope['method'] != 'POST':
                return await JSONResponse({'error': 'POST only.'}, status_code=405,
                                          headers={'Allow': 'POST'})(scope, receive, send)
            if not headers.get(b'content-type', b'').lower().startswith(b'application/json'):
                return await JSONResponse({'error': 'JSON required.'}, status_code=415)(scope, receive, send)
            token = _principal.set(principal)
            delivered = False
            async def buffered():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
                return await receive()
            try:
                await self.app(scope, buffered, send)
            finally:
                _principal.reset(token)


def create_app(router, keys, identity, hosts=('localhost', '127.0.0.1'), origins=()):
    # A child logger can propagate despite its parent's disabled flag.
    for name in ('mcp', 'httpx', 'httpcore', 'uvicorn.access'):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL + 1)
        for child_name, child in list(logging.Logger.manager.loggerDict.items()):
            if child_name.startswith(name + '.') and isinstance(child, logging.Logger):
                child.handlers = []
                child.setLevel(logging.NOTSET)
                child.propagate = True
    server = Server('urumi-team-gateway')

    async def listing(request):
        try:
            items = await router.list_tools(_principal.get())
            tools = [types.Tool(name=item['name'], description=item['description'], inputSchema=item['inputSchema'],
                                **{key: item[key] for key in ('outputSchema', 'annotations') if key in item}) for item in items]
            return types.ServerResult(types.ListToolsResult(tools=tools))
        except Exception:
            raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message='Tool discovery is unavailable.')) from None

    async def calling(request):
        try:
            reply = await router.invoke_tool(_principal.get(), request.params.name, request.params.arguments or {})
            result = reply['result']
            if reply['outcome'] == 'denied':
                code = json.loads(result.content[0].text)['error']['code']
                if code == 'TOOL_NOT_FOUND':
                    raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message='Unknown tool.'))
            return types.ServerResult(result)
        except McpError:
            raise
        except PlatformError as error:
            raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message=error.code)) from None
        except Exception:
            raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message='Tool execution is unavailable.')) from None

    server.request_handlers[types.ListToolsRequest] = listing
    server.request_handlers[types.CallToolRequest] = calling
    manager = StreamableHTTPSessionManager(server, stateless=True, json_response=True)

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            await router.discovery.start()
            try:
                yield
            finally:
                await router.discovery.close()
                await router.close()

    class Endpoint:
        async def __call__(self, scope, receive, send):
            await manager.handle_request(scope, receive, send)

    async def live(request):
        return JSONResponse({'status': 'live'})

    async def ready(request):
        try:
            await router.blocking.run(router.registry.db.check_owner)
            if router.discovery.task is None or router.discovery.task.done():
                raise RuntimeError()
            return JSONResponse({'status': 'ready'})
        except Exception:
            return JSONResponse({'status': 'unavailable'}, status_code=503)

    async def preview(request):
        try:
            principal = await router.blocking.run(identity.session, request.cookies.get('urumi_session', ''))
            result = await router.discovery.preview(principal, UUID(request.path_params['server_id']),
                int(request.query_params.get('page', '1')), int(request.query_params.get('per_page', '20')))
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except PlatformError as error:
            return safe_error(error)
        except (ValueError, TypeError):
            return safe_error(PlatformError(422, 'INVALID_INPUT', 'The supplied input is invalid.'))
        except Exception:
            return safe_error(PlatformError(503, 'DEPENDENCY_UNAVAILABLE', 'Preview is unavailable.'))

    app = Starlette(routes=[Route('/mcp', Endpoint(), methods=['POST', 'GET', 'DELETE']),
        Route('/livez', live), Route('/readyz', ready),
        Route('/api/v1/servers/{server_id}/tools', preview)], lifespan=lifespan)
    app.state.router = router
    return Guard(app, keys, router, hosts, origins)
