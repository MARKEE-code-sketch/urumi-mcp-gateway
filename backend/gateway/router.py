"""One execution path, with bounded workers and honest audit finalization."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from threading import Event
import time
from uuid import UUID

from jsonschema.validators import validator_for

from backend.errors import PlatformError
from backend.gateway.common import Blocking, GatewayError, error_result
from backend.gateway.context import complete, get_context, has_invocation, invocation_context, request_context
from backend.gateway.discovery import failure_code
from backend.gateway.schema import validate


class LockBridge:
    def __init__(self, db):
        self.db = db
        self.pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix='gateway-lock')
        self.active = set()

    @asynccontextmanager
    async def hold(self, server_id):
        if len(self.active) >= 8:
            raise GatewayError('FORBIDDEN', 'denied')
        loop, release = asyncio.get_running_loop(), Event()
        ready = loop.create_future()
        def announce(error=None):
            if not ready.done():
                ready.set_exception(error) if error else ready.set_result(None)
        def work():
            try:
                with self.db.server_lock(server_id):
                    self.db.check_owner()
                    if release.is_set():
                        return
                    loop.call_soon_threadsafe(announce)
                    release.wait(12)
            except Exception:
                loop.call_soon_threadsafe(announce, PlatformError(503, 'DEPENDENCY_UNAVAILABLE', 'Routing ownership is unavailable.'))
        future = loop.run_in_executor(self.pool, work)
        self.active.add(future)
        future.add_done_callback(self.active.discard)
        try:
            await asyncio.shield(ready)
            if release.is_set() or future.done():
                raise GatewayError('UPSTREAM_UNAVAILABLE')
            yield
        finally:
            release.set()
            # Consume a late readiness failure after caller cancellation.
            if not ready.done():
                ready.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)


class Router:
    def __init__(self, identity, registry, audit, discovery, upstream):
        self.identity, self.registry, self.audit = identity, registry, audit
        self.discovery, self.upstream = discovery, upstream
        self.blocking, self.finalizers = Blocking(8), Blocking(8)
        self.locks = LockBridge(registry.db)
        self.slots = asyncio.Semaphore(8)
        self.server_slots = {}
        self.pending_finalizers = set()

    async def list_tools(self, principal):
        return await self.discovery.list_tools(principal)

    async def _finalize(self, audit_id, outcome, duration, code):
        task = asyncio.create_task(self.finalizers.run(self.audit.finalize_attempt, audit_id, outcome, duration, code))
        self.pending_finalizers.add(task)
        def finished(value):
            self.pending_finalizers.discard(value)
            if not value.cancelled():
                value.exception()
        task.add_done_callback(finished)
        try:
            async with asyncio.timeout(2):
                await asyncio.shield(task)
        except Exception:
            raise PlatformError(503, 'AUDIT_FINALIZATION_FAILED', 'The outcome could not be saved; remote effects are uncertain.') from None

    async def invoke_tool(self, principal, tool_name, arguments):
        if get_context() is None:
            with request_context():
                return await self.invoke_tool(principal, tool_name, arguments)
        if not has_invocation():
            with invocation_context():
                return await self.invoke_tool(principal, tool_name, arguments)
        context = get_context()
        if len(context.completions) >= context.max_completions:
            raise PlatformError(503, 'CALL_LIMIT', 'The request call limit was reached.')
        started, audit_id, server_id, dispatched = time.monotonic(), None, None, False
        outcome, code, result = 'error', None, None
        begin_task = None
        verified = False
        safe_name = tool_name if isinstance(tool_name, str) and 1 <= len(tool_name) <= 64 else '<invalid-tool>'
        try:
            async with asyncio.timeout(10):
                principal = await self.blocking.run(self.identity.revalidate, principal)
                verified = True
                if safe_name == '<invalid-tool>':
                    raise GatewayError('TOOL_NOT_FOUND', 'denied')
                item, version = await self.discovery.lookup(principal, tool_name)
                server_id = UUID(item['server_id'])
                slot = self.server_slots.setdefault(server_id, asyncio.Semaphore(2))
                acquired = server_acquired = False
                try:
                    async with asyncio.timeout(1):
                        await self.slots.acquire()
                        acquired = True
                        await slot.acquire()
                        server_acquired = True
                    async with self.locks.hold(server_id):
                        row = await self.blocking.run(self.registry.get_server, server_id)
                        if not row['enabled']:
                            raise GatewayError('TOOL_DISABLED', 'denied')
                        if row['version'] != version:
                            raise GatewayError('TOOL_NOT_FOUND', 'denied')
                        if not isinstance(arguments, dict):
                            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                        try:
                            await self.blocking.run(validate, item['inputSchema'], arguments)
                        except Exception:
                            raise GatewayError('UPSTREAM_PROTOCOL_ERROR') from None
                        principal = await self.blocking.run(self.identity.revalidate, principal)
                        begin_task = asyncio.create_task(self.blocking.run(self.audit.begin_attempt, context.request_id,
                            principal, server_id, tool_name, item['upstream_name']))
                        audit_id = await asyncio.shield(begin_task)
                        secret = await self.discovery.secret(row)
                        async def before_send():
                            nonlocal principal, dispatched
                            principal = await self.blocking.run(self.identity.revalidate, principal)
                            current = await self.blocking.run(self.registry.get_server, server_id)
                            await self.blocking.run(self.registry.db.check_owner)
                            if not current['enabled']:
                                raise GatewayError('TOOL_DISABLED', 'denied')
                            if current['version'] != version:
                                raise GatewayError('TOOL_NOT_FOUND', 'denied')
                            dispatched = True
                        result = await self.upstream.call(row, secret, item['upstream_name'], arguments, before_send)
                        if result.structuredContent is not None and 'outputSchema' in item and not result.isError:
                            try:
                                await self.blocking.run(validate, item['outputSchema'], result.structuredContent)
                            except Exception:
                                raise GatewayError('UPSTREAM_PROTOCOL_ERROR') from None
                        outcome, code = ('error', 'UPSTREAM_ERROR') if result.isError else ('success', None)
                finally:
                    if server_acquired:
                        slot.release()
                    if acquired:
                        self.slots.release()
        except asyncio.CancelledError:
            if begin_task is not None and audit_id is None:
                async def cancel_late_begin():
                    try:
                        late_id = await begin_task
                        await self._finalize(late_id, 'denied', int((time.monotonic()-started)*1000), 'FORBIDDEN')
                    except Exception:
                        pass
                late = asyncio.create_task(cancel_late_begin())
                self.pending_finalizers.add(late)
                late.add_done_callback(self.pending_finalizers.discard)
            outcome, code = ('unknown', 'INTERRUPTED') if dispatched else ('denied', 'FORBIDDEN')
            if audit_id:
                try:
                    await self._finalize(audit_id, outcome, int((time.monotonic()-started)*1000), code)
                except PlatformError:
                    code = 'AUDIT_FINALIZATION_FAILED'
            complete(audit_id, server_id, int((time.monotonic()-started)*1000), code)
            raise
        except PlatformError as error:
            code = error.code
            if error.status == 401:
                outcome = 'denied'
                code = 'KEY_REVOKED' if error.code == 'KEY_REVOKED' else 'UNAUTHENTICATED'
                principal = error.principal or principal
            elif code in ('AUDIT_UNAVAILABLE', 'AUDIT_FINALIZATION_FAILED'):
                complete(audit_id, server_id, int((time.monotonic()-started)*1000), code)
                raise
            else:
                code = 'UPSTREAM_UNAVAILABLE'
        except Exception as error:
            errors = [error]
            leaves = []
            while errors:
                current_error = errors.pop()
                if isinstance(current_error, BaseExceptionGroup):
                    errors.extend(current_error.exceptions)
                else:
                    leaves.append(current_error)
            denial = next((item for item in leaves if isinstance(item, PlatformError) and item.status == 401), None)
            routing_denial = next((item for item in leaves if isinstance(item, GatewayError) and item.outcome == 'denied'), None)
            if denial:
                code, outcome = ('KEY_REVOKED' if denial.code == 'KEY_REVOKED' else 'UNAUTHENTICATED'), 'denied'
            elif routing_denial:
                code, outcome = routing_denial.code, 'denied'
            else:
                code = failure_code(error)
                outcome = error.outcome if isinstance(error, GatewayError) else ('timeout' if code == 'UPSTREAM_TIMEOUT' else 'error')
        duration = int((time.monotonic()-started)*1000)
        if begin_task is not None and audit_id is None:
            async def finish_late_begin():
                try:
                    late_id = await begin_task
                    await self._finalize(late_id, 'denied', duration, 'FORBIDDEN')
                except Exception:
                    pass
            late = asyncio.create_task(finish_late_begin())
            self.pending_finalizers.add(late)
            late.add_done_callback(self.pending_finalizers.discard)
            complete(None, server_id, duration, 'AUDIT_UNAVAILABLE')
            raise PlatformError(503, 'AUDIT_UNAVAILABLE', 'Activity start was not confirmed; execution was not started.')
        try:
            if audit_id:
                await self._finalize(audit_id, outcome, duration, code)
            else:
                # Validation failures and pre-dispatch denials still have exactly one row.
                audit_id = await self.blocking.run(self.audit.record_denial, context.request_id,
                    principal if verified else None, server_id, safe_name, code or 'FORBIDDEN')
                outcome = 'denied'
        except PlatformError as error:
            complete(audit_id, server_id, duration, error.code)
            raise
        complete(audit_id, server_id, duration, code)
        return dict(request_id=str(context.request_id), audit_id=str(audit_id), outcome=outcome,
                    result=result if result is not None and (outcome == 'success' or code == 'UPSTREAM_ERROR' and result.isError) else error_result(code or 'UPSTREAM_ERROR'))

    async def close(self):
        self.locks.close()
        self.blocking.close()
        self.finalizers.close()
