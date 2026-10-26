"""Explicit bounded JSON Schema subset; no network references or unsafe regex."""
import json

from jsonschema.validators import validator_for

from backend.gateway.common import GatewayError


SAFE_PATTERNS = {r'\S', r'^(0|[1-9][0-9]*)(\.[0-9]{1,2})?$',
                 r'^(0|[1-9][0-9]*)(\.[0-9]{2})?$', r'^[A-Z]{3}$', r'^[A-Za-z0-9_.-]+$'}


def check_schema(schema):
    stack, nodes = [(schema, 0, 1)], 0
    while stack:
        value, level, branches = stack.pop()
        nodes += 1
        if nodes > 512 or level > 32 or branches > 64:
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        if isinstance(value, dict):
            if any(key in value for key in ('$ref', '$dynamicRef', '$recursiveRef', 'patternProperties')):
                raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
            if 'pattern' in value and value['pattern'] not in SAFE_PATTERNS:
                raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
            for key, child in value.items():
                factor = len(child) if key in ('allOf', 'anyOf', 'oneOf') and isinstance(child, list) else 1
                stack.append((child, level+1, branches * max(1, factor)))
        elif isinstance(value, list):
            stack.extend((child, level+1, branches) for child in value)
    validator_for(schema).check_schema(schema)


def validate(schema, value):
    check_schema(schema)
    if len(json.dumps(value).encode()) > 65536:
        raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
    stack, nodes = [(value, 0)], 0
    while stack:
        item, level = stack.pop()
        nodes += 1
        if nodes > 2000 or level > 32 or isinstance(item, list) and len(item) > 200:
            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
        if isinstance(item, dict):
            stack.extend((child, level+1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, level+1) for child in item)
    try:
        validator_for(schema)(schema).validate(value)
    except Exception:
        raise GatewayError('UPSTREAM_PROTOCOL_ERROR') from None
