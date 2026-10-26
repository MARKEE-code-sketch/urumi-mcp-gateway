import asyncio
import json
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.errors import PlatformError, invalid, unavailable
from backend.gateway.context import request_context


def mount_chat(app, agent, identity, browser_config):
    @app.post('/api/v1/chat')
    async def chat(request: Request):
        request_uuid = uuid4()
        request_id = str(request_uuid)
        try:
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 16384:
                    raise invalid()
            try:
                data = json.loads(raw)
                if not isinstance(data, dict) or set(data) != {'message'} or not isinstance(data['message'], str):
                    raise ValueError()
                message = data['message'].strip()
                if not message or len(message) > 4000 or len(message.encode('utf-8')) > 12288:
                    raise ValueError()
            except (ValueError, UnicodeError, TypeError, RecursionError):
                raise invalid() from None
            if request.headers.get('origin') != browser_config.origin:
                raise PlatformError(403, 'REQUEST_REJECTED', 'The request was rejected.')
            def caller():
                principal = identity.session(request.cookies.get('urumi_session'))
                principal = identity.revalidate(principal)
                identity.check_csrf(principal, request.headers.get('x-csrf-token'))
                return principal
            principal = await agent.blocking(caller)
            with request_context(request_uuid, max_completions=12):
                work = asyncio.create_task(agent.run(principal, message))
                async def disconnected():
                    # Starlette's disconnect probe uses a cancellation scope which
                    # can consume cancellation under the account API middleware.
                    while not asyncio.current_task().cancelling() and not await request.is_disconnected():
                        await asyncio.sleep(0.05)
                watcher = asyncio.create_task(disconnected())
                try:
                    done, _ = await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
                    if watcher in done and not work.done():
                        work.cancel()
                        try:
                            await asyncio.wait_for(asyncio.shield(work), timeout=2)
                        except (TimeoutError, asyncio.CancelledError):
                            pass
                        # The disconnected peer cannot be promised delivery.
                        return JSONResponse(status_code=499, content={'error': {'code': 'REQUEST_CANCELLED',
                            'message': 'The request disconnected.', 'request_id': request_id}}, headers={'Cache-Control': 'no-store'})
                    reply = await work
                finally:
                    watcher.cancel()
                    if not work.done():
                        work.cancel()
                    await asyncio.gather(watcher, return_exceptions=True)
            return JSONResponse(reply, headers={'Cache-Control': 'no-store'})
        except PlatformError as error:
            return JSONResponse({'error': {'code': error.code, 'message': error.message, 'request_id': request_id}},
                                status_code=error.status, headers={'Cache-Control': 'no-store'})
        except asyncio.CancelledError:
            raise
        except Exception:
            error = unavailable()
            return JSONResponse({'error': {'code': error.code, 'message': error.message, 'request_id': request_id}},
                                status_code=503, headers={'Cache-Control': 'no-store'})
