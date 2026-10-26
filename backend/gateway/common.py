"""Fixed, credential-free gateway failures and bounded blocking adapters."""
import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor

from mcp import types

from backend.errors import PlatformError


class GatewayError(Exception):
    def __init__(self, code, outcome='error'):
        self.code, self.outcome = code, outcome
        super().__init__(code)


def error_result(code):
    import json
    return types.CallToolResult(isError=True, content=[types.TextContent(
        type='text', text=json.dumps({'error': {'code': code, 'message': {
            'UPSTREAM_TIMEOUT': 'The deadline expired; remote effects may be uncertain.',
            'AUDIT_FINALIZATION_FAILED': 'The outcome could not be saved; remote effects are uncertain.',
        }.get(code, 'The tool request could not be completed.')}}))])


class Blocking:
    """A timed-out caller does not free a slot while its SQL is still running."""
    def __init__(self, capacity=8):
        self.pool = ThreadPoolExecutor(max_workers=capacity, thread_name_prefix='gateway-adapter')
        self.capacity = capacity
        self.active = set()

    async def run(self, function, *args, **kwargs):
        if len(self.active) >= self.capacity:
            raise PlatformError(503, 'DEPENDENCY_UNAVAILABLE', 'Adapter capacity is exhausted.')
        context = contextvars.copy_context()
        future = asyncio.get_running_loop().run_in_executor(
            self.pool, lambda: context.run(function, *args, **kwargs))
        self.active.add(future)
        def finished(task):
            self.active.discard(task)
            if not task.cancelled():
                task.exception()
        future.add_done_callback(finished)
        return await asyncio.shield(future)

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)
