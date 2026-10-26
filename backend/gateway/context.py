"""Trusted request correlation; never populate these values from request JSON."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class RequestContext:
    request_id: object
    max_completions: int
    completions: list = field(default_factory=list)


_request = ContextVar('gateway_request', default=None)
_invocation = ContextVar('gateway_invocation', default=None)


@contextmanager
def request_context(request_id=None, max_completions=32):
    if not 1 <= max_completions <= 32:
        raise ValueError('Invalid completion limit.')
    value = RequestContext(UUID(str(request_id)) if request_id else uuid4(), max_completions)
    token = _request.set(value)
    try:
        yield value
    finally:
        _request.reset(token)


@contextmanager
def invocation_context(invocation_id=None):
    value = UUID(str(invocation_id)) if invocation_id else uuid4()
    token = _invocation.set(value)
    try:
        yield value
    finally:
        _invocation.reset(token)


def get_context():
    return _request.get()


def complete(audit_id, server_id, duration_ms, error_code):
    context = get_context()
    if context is None:
        return
    invocation_id = _invocation.get()
    if invocation_id is None:
        raise RuntimeError('Missing invocation context.')
    if any(item['invocation_id'] == str(invocation_id) for item in context.completions):
        return
    if len(context.completions) >= context.max_completions:
        raise RuntimeError('Completion capacity exhausted.')
    context.completions.append(dict(invocation_id=str(invocation_id),
                                    audit_id=str(audit_id) if audit_id else None,
                                    server_id=str(server_id) if server_id else None,
                                    duration_ms=duration_ms, error_code=error_code))


def has_invocation():
    return _invocation.get() is not None
