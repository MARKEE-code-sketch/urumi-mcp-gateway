"""Disposable stand-ins. Never connects to a store, database or upstream MCP."""
import copy
import json
from pathlib import Path
from uuid import UUID, uuid4

from backend.errors import PlatformError
from backend.identity.auth import Principal
from backend.gateway.context import complete, get_context


ROOT = Path(__file__).resolve().parents[2]


def catalog():
    definitions = json.loads((ROOT / 'contracts/mcp-tools.schema.json').read_text('utf-8'))['tools']
    shop, inventory = uuid4(), uuid4()
    return [dict(name=('inventory' if item['name'] == 'lookup_sku' else 'woocommerce') + '__' + item['name'],
                 server_id=inventory if item['name'] == 'lookup_sku' else shop,
                 server_slug='inventory' if item['name'] == 'lookup_sku' else 'woocommerce',
                 upstream_name=item['name'], description=item['description'], inputSchema=item['inputSchema'],
                 outputSchema=item.get('outputSchema'), stale=False) for item in definitions]


def result(data):
    return {'content': [{'type': 'text', 'text': json.dumps(data)}], 'structuredContent': data, 'isError': False}


class IdentityFixture:
    def __init__(self):
        self._proof = object()
        self.a = Principal(uuid4(), 'admin', 'session', None, 'a', self._proof)
        self.b = Principal(uuid4(), 'member', 'session', None, 'b', self._proof)
        self.valid = {'a', 'b'}

    def revalidate(self, principal):
        if (not isinstance(principal, Principal) or principal._proof is not self._proof or
                principal._handle not in self.valid):
            raise PlatformError(401, 'UNAUTHENTICATED', 'Authentication is required.')
        return principal

    def session(self, token):
        principal = {'session-a': self.a, 'session-b': self.b}.get(token)
        return self.revalidate(principal)

    def check_csrf(self, principal, value):
        self.revalidate(principal)
        if value != 'fixture-csrf':
            raise PlatformError(403, 'REQUEST_REJECTED', 'The request was rejected.')


class GatewayFixture:
    def __init__(self, identity, handler=None):
        self.identity, self.handler = identity, handler
        self.tools, self.calls, self.list_count = catalog(), [], 0
        self.outcome, self.error_code = 'success', None

    async def list_tools(self, principal):
        self.identity.revalidate(principal)
        self.list_count += 1
        return copy.deepcopy(self.tools)

    async def invoke_tool(self, principal, name, arguments):
        self.identity.revalidate(principal)
        if not isinstance(get_context().request_id, UUID):
            raise TypeError('M5 audit requires a UUID request identifier.')
        tool = next((tool for tool in self.tools if tool['name'] == name), None)
        if tool is None:
            complete(uuid4(), None, 0, 'TOOL_DISABLED')
            raise PlatformError(403, 'TOOL_DISABLED', 'The server is disabled.')
        audit_id = uuid4()
        self.calls.append((principal, name, copy.deepcopy(arguments)))
        try:
            data = await self.handler(name, arguments) if self.handler else self.default(name, arguments)
        except PlatformError as error:
            complete(None if error.code == 'AUDIT_UNAVAILABLE' else audit_id, tool['server_id'], 1, error.code)
            raise
        complete(audit_id, tool['server_id'], 1, self.error_code)
        return {'request_id': str(get_context().request_id), 'audit_id': str(audit_id),
                'outcome': self.outcome, 'result': data}

    @staticmethod
    def default(name, arguments):
        if name == 'inventory__lookup_sku':
            return result({'sku': arguments['sku'], 'found': True,
                           'warehouses': [{'name': 'Bengaluru', 'quantity': 12}]})
        if name == 'woocommerce__list_products':
            return result({'items': [{'id': 12, 'sku': 'DEMO-001', 'name': 'Demo Mug'}],
                           'page': 1, 'per_page': 20, 'has_more': False})
        if name == 'woocommerce__create_product':
            return result({'product': {'id': 77, 'name': arguments['name'], 'regular_price': arguments['regular_price']}})
        if name == 'woocommerce__list_orders':
            return result({'items': [], 'page': arguments.get('page', 1),
                           'per_page': arguments.get('per_page', 20), 'has_more': False})
        return result({'ok': True})


def tool_call(name='inventory__lookup_sku', arguments=None, call_id='fixture-call'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': call_id, 'type': 'function',
        'function': {'name': name, 'arguments': json.dumps(arguments if arguments is not None else {'sku': 'DEMO-001'})}}]}


class ScriptedProvider:
    key = 'fixture-provider-key'

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    async def complete(self, messages, tools, final=False):
        self.requests.append((copy.deepcopy(messages), copy.deepcopy(tools), final))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            return await reply(messages, tools, final)
        return reply

    def redact(self, value):
        return value.replace(self.key, '[REDACTED]')
