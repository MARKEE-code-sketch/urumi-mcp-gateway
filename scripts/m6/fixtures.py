"""Controlled SAMPLE MCP peer, supporting JSON or stateful SSE for acceptance."""
import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import os

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route


def fixture_app(mode='none', secret='', stateful=False):
    server = Server('m6-controlled-' + mode)
    state = dict(discovery='ok', calls=0, headers=[], delay=0)
    schema = {'type': 'object', 'properties': {'action': {'type': 'string'}, 'delay': {'type': 'number'}}, 'additionalProperties': False}

    async def listing(request):
        cursor = request.params.cursor if request.params else None
        if state['discovery'] == 'slow':
            await asyncio.sleep(12)
        if state['discovery'] == 'invalid':
            return types.ServerResult(types.ListToolsResult(tools=[types.Tool(name='service_info', inputSchema={'type': 7})]))
        name = 'service_info' if cursor is None else 'second_tool'
        result = types.ListToolsResult(tools=[types.Tool(name=name, description='Controlled SAMPLE ' + mode,
            inputSchema=schema)], nextCursor='page2' if cursor is None else None)
        return types.ServerResult(result)

    async def calling(request):
        state['calls'] += 1
        args = request.params.arguments or {}
        if args.get('delay'):
            await asyncio.sleep(args['delay'])
        action = args.get('action', 'ok')
        payload = {'fixture_only': True, 'mode': mode, 'tool': request.params.name}
        if action == 'echo':
            payload['echo'] = secret
        return types.ServerResult(types.CallToolResult(isError=action == 'error',
            structuredContent=None if action == 'error' else payload,
            content=[types.TextContent(type='text', text=json.dumps(payload))]))

    server.request_handlers[types.ListToolsRequest] = listing
    server.request_handlers[types.CallToolRequest] = calling
    manager = StreamableHTTPSessionManager(server, stateless=not stateful, json_response=not stateful)
    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    class Endpoint:
        async def __call__(self, scope, receive, send):
            headers = dict(scope['headers'])
            if mode != 'none':
                expected = ('Bearer ' + secret if mode == 'bearer' else secret).encode()
                if not hmac.compare_digest(headers.get(b'authorization' if mode == 'bearer' else b'x-test-key', b''), expected):
                    return await JSONResponse({'error': 'Authentication failed.'}, status_code=401)(scope, receive, send)
            # Persist only presence markers, never raw credentials.
            state['headers'].append({'cookie': b'cookie' in headers,
                'authorization': b'authorization' in headers, 'custom_header': b'x-test-key' in headers})
            state['headers'][:] = state['headers'][-50:]
            if state['discovery'] == 'redirect':
                return await RedirectResponse('http://169.254.169.254/')(scope, receive, send)
            await manager.handle_request(scope, receive, send)

    async def health(request):
        return JSONResponse({'status': 'ready'})

    async def control(request):
        if request.method == 'POST':
            body = await request.json()
            if set(body) - {'discovery'} or body.get('discovery') not in ('ok', 'slow', 'invalid', 'redirect'):
                return JSONResponse({'error': 'Invalid control.'}, status_code=422)
            state['discovery'] = body['discovery']
        return JSONResponse(state)

    app = Starlette(routes=[Route('/mcp', Endpoint(), methods=['POST', 'GET', 'DELETE']),
        Route('/livez', health), Route('/readyz', health), Route('/test/control', control, methods=['GET', 'POST'])], lifespan=lifespan)
    app.state.fixture = state
    return app


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(fixture_app(os.environ.get('MODE', 'none'), os.environ.get('UPSTREAM_TOKEN', ''),
                           os.environ.get('STATEFUL', 'false') == 'true'), host='0.0.0.0', port=8000,
                access_log=False, log_level='critical')
