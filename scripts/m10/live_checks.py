"""Explicit, HTTPS-only real API/MCP checks; never imported by the application.

Credentials/config stay in an ignored private file. Only the returned allowlisted
evidence may be published. These deterministic MCP calls are transport/security
checks, not proof of an external LLM client or browser checkout.
"""
import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import ssl
from urllib.parse import parse_qs, urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class CheckFailed(RuntimeError):
    """Fixed safe label; never retain a raw response or request."""


def require(condition, label):
    if not condition:
        raise CheckFailed(label)


def origin_value(value):
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('An exact HTTPS origin is required.')
    return value


def tls_context(ca_path):
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(ca_path))
    return context


class Browser:
    """Cookie login and CSRF exactly as used by the real dashboard."""

    def __init__(self, origin, context, transport=None):
        self.origin = origin_value(origin)
        self.client = httpx.AsyncClient(base_url=origin, verify=context, timeout=35,
            trust_env=False, follow_redirects=False, transport=transport)
        self.csrf = None
        self.user = None

    async def close(self):
        await self.client.aclose()

    async def request(self, method, path, data=None, expected=200):
        require(path.startswith('/api/v1/') and not path.startswith('//'), 'api_path')
        headers = {'Origin': self.origin}
        if self.csrf:
            headers['X-CSRF-Token'] = self.csrf
        response = await self.client.request(method, path, json=data, headers=headers)
        require(response.status_code == expected, 'api_status_' + str(expected))
        return response.json() if response.content else None

    async def login(self, email, password):
        result = await self.request('POST', '/api/v1/auth/login',
                                    {'email': email, 'password': password})
        self.csrf, self.user = result['csrf_token'], result['user']
        require(bool(self.client.cookies.get('urumi_session')), 'session_cookie')
        return self.user


@asynccontextmanager
async def gateway(origin, context, key):
    """No upstream URL, upstream key or provider key is passed to this client."""
    async with httpx.AsyncClient(verify=context, trust_env=False,
            follow_redirects=False, timeout=40,
            headers={'Authorization': 'Bearer ' + key}) as http:
        async with streamable_http_client(origin_value(origin) + '/mcp', http_client=http) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session


def result_data(result):
    require(not result.isError, 'mcp_tool_error')
    if result.structuredContent is not None:
        return result.structuredContent
    blocks = [block.text for block in result.content if block.type == 'text']
    require(len(blocks) == 1, 'mcp_result_shape')
    return json.loads(blocks[0])


async def wait_tools(session, prefixes, timeout=70):
    """Read-only discovery retries; writes and tool calls are never retried."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        names = [tool.name for tool in (await session.list_tools()).tools]
        if all(any(name.startswith(prefix + '__') for name in names) for prefix in prefixes):
            return names
        require(asyncio.get_running_loop().time() < deadline, 'discovery_deadline')
        await asyncio.sleep(2)


async def ensure_server(admin, slug, name, url):
    existing = (await admin.request('GET', '/api/v1/servers?per_page=50'))['items']
    matches = [item for item in existing if item['slug'] == slug]
    if matches:
        require(len(matches) == 1 and matches[0]['url'] == url and matches[0]['enabled'],
                'existing_server_mismatch')
        return matches[0]
    return await admin.request('POST', '/api/v1/servers',
        {'slug': slug, 'name': name, 'url': url, 'credential': {'type': 'none'}}, 201)


async def run_owned_demo(config, *, run_owned_demo=False):
    """Create an owned member/key, register demo servers and test real boundaries.

    Optional ``product`` creates ONE product with a unique supplied SKU. Optional
    ``order_id`` reads ONE owned browser-checkout order and updates its status.
    No order is invented here. All writes run once. On failure, owned key cleanup
    is attempted; a created member/product/server remains inspectable.
    """
    require(run_owned_demo is True, 'explicit_mutation_flag_required')
    origin = origin_value(config['origin'])
    context = tls_context(config['ca_path'])
    admin, member = Browser(origin, context), Browser(origin, context)
    evidence = {'checked_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'Real HTTPS API and MCP checks; no LLM client or browser proof.',
                'checks': [], 'ids': {}}
    member_key = None
    member_id = None
    cleanup_ok = True
    try:
        user = await admin.login(config['admin_email'], config['admin_password'])
        require(user['role'] == 'admin', 'admin_role')
        evidence['ids']['admin_user_id'] = user['id']
        inventory = await ensure_server(admin, 'inventory', 'Inventory', config['inventory_url'])
        learn = await ensure_server(admin, 'learn', 'Microsoft Learn', 'https://learn.microsoft.com/api/mcp')
        evidence['ids'].update(inventory_server_id=inventory['id'], learn_server_id=learn['id'])
        invitation = await admin.request('POST', '/api/v1/invitations',
            {'email': config['member_email'], 'role': 'member'}, 201)
        token = parse_qs(urlsplit(invitation['invite_url']).fragment)['token'][0]
        redeemed = await member.request('POST', '/api/v1/invitations/redeem',
            {'token': token, 'password': config['member_password']}, 201)
        member_id = redeemed['user']['id']
        await member.login(config['member_email'], config['member_password'])
        require(member.user['role'] == 'member', 'member_role')
        member_key = await member.request('POST', f'/api/v1/members/{member_id}/keys',
                                         {'label': 'M10 owned API/MCP checks'}, 201)
        evidence['ids'].update(member_user_id=member_id, key_id=member_key['id'])
        await member.request('GET', '/api/v1/members', expected=403)
        await member.request('POST', '/api/v1/servers',
            {'name': 'Denied', 'slug': 'denied', 'url': config['inventory_url']}, 403)
        await member.request('GET', f"/api/v1/members/{user['id']}/keys", expected=404)
        summaries = (await member.request('GET', '/api/v1/servers?per_page=50'))['items']
        require(all(not {'url', 'auth_type', 'header_name', 'credential', 'secret_name'} & set(item)
                    for item in summaries), 'member_registry_redaction')
        evidence['checks'].append({'check': 'identity_roles_and_redaction', 'status': 'PASS'})
        async with gateway(origin, context, member_key['raw_key']) as session:
            names = await wait_tools(session, ['woocommerce', 'inventory', 'learn'])
            expected = {'woocommerce__' + name for name in
                ('list_products', 'create_product', 'list_orders', 'get_order', 'update_order_status')}
            require(expected <= set(names), 'five_woo_tools')
            evidence['tool_names'] = names
            inventory_data = result_data(await session.call_tool('inventory__lookup_sku',
                {'sku': config.get('inventory_sku', 'DEMO-001')}))
            require(type(inventory_data.get('found')) is bool and
                    isinstance(inventory_data.get('warehouses'), list), 'inventory_result_shape')
            evidence['checks'].append({'check': 'sample_inventory_lookup', 'status': 'PASS',
                                      'found': inventory_data['found']})
            # Select from actual schemas, never invent a hosted tool signature.
            discovered = (await session.list_tools()).tools
            searches = [tool for tool in discovered if tool.name.startswith('learn__') and
                'search' in tool.name.lower() and
                tool.inputSchema.get('properties', {}).get('query', {}).get('type') == 'string' and
                set(tool.inputSchema.get('required', [])) <= {'query'}]
            require(bool(searches), 'learn_search_schema')
            search = await session.call_tool(searches[0].name,
                {'query': 'Kubernetes readiness versus liveness probes'})
            require(not search.isError and bool(search.content), 'learn_search_result')
            evidence['checks'].append({'check': 'real_learn_search_through_gateway', 'status': 'PASS',
                                      'tool_name': searches[0].name})
            for name in ('list_products', 'list_orders'):
                data = result_data(await session.call_tool('woocommerce__' + name, {'per_page': 5}))
                require(isinstance(data.get('items'), list), 'woo_list_shape')
                evidence['checks'].append({'check': name, 'status': 'PASS', 'item_count': len(data['items'])})
            if config.get('product'):
                product = result_data(await session.call_tool('woocommerce__create_product', config['product']))['product']
                evidence['ids']['product_id'] = product['id']
                evidence['checks'].append({'check': 'create_product', 'status': 'PASS'})
            if config.get('order_id'):
                order_id = config['order_id']
                require(type(order_id) is int and order_id > 0, 'owned_order_id')
                result_data(await session.call_tool('woocommerce__get_order', {'order_id': order_id}))
                result_data(await session.call_tool('woocommerce__update_order_status',
                    {'order_id': order_id, 'status': config.get('order_status', 'processing')}))
                evidence['ids']['order_id'] = order_id
                evidence['checks'].append({'check': 'get_and_update_owned_order', 'status': 'PASS'})
            await admin.request('PATCH', '/api/v1/servers/' + inventory['id'], {'enabled': False})
            try:
                disabled_names = [tool.name for tool in (await session.list_tools()).tools]
                require(not any(name.startswith('inventory__') for name in disabled_names), 'disabled_discovery')
                result_data(await session.call_tool('woocommerce__list_products', {'per_page': 1}))
                evidence['checks'].append({'check': 'disable_isolation', 'status': 'PASS'})
            finally:
                await admin.request('PATCH', '/api/v1/servers/' + inventory['id'], {'enabled': True})
        own_audit = (await member.request('GET', '/api/v1/audit?per_page=50'))['items']
        require(bool(own_audit) and all(row['user_id'] == member_id for row in own_audit), 'audit_member_scope')
        evidence['audit'] = [{field: row[field] for field in
            ('audit_id', 'user_id', 'key_id', 'auth_source', 'public_tool_name', 'outcome', 'error_code')}
            for row in own_audit if row['key_id'] == member_key['id']]
        require(bool(evidence['audit']), 'audit_key_attribution')
        evidence['checks'].append({'check': 'audit_attribution', 'status': 'PASS'})
    finally:
        if member_key and member_id:
            try:
                await member.request('DELETE', f"/api/v1/members/{member_id}/keys/{member_key['id']}", expected=204)
                response = await member.client.post('/mcp', json={'jsonrpc': '2.0', 'id': 1,
                    'method': 'tools/call', 'params': {'name': 'woocommerce__list_products', 'arguments': {}}},
                    headers={'Authorization': 'Bearer ' + member_key['raw_key']})
                require(response.status_code == 401 and response.json()['error']['code'] == 'KEY_REVOKED',
                        'revoked_key_rejected')
                evidence['checks'].append({'check': 'key_revoked_and_rejected', 'status': 'PASS'})
            except Exception:
                cleanup_ok = False
        await member.close()
        await admin.close()
    require(cleanup_ok, 'owned_key_cleanup_or_revocation_check_failed')
    evidence['status'] = 'PASS_API_MCP_ONLY'
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--run-owned-demo', action='store_true')
    args = parser.parse_args()
    if not args.run_owned_demo:
        parser.error('--run-owned-demo explicitly authorizes the owned demo writes.')
    root = Path(__file__).resolve().parents[2]
    if not args.private_config.resolve().is_relative_to(root / '.tools'):
        parser.error('Private config must stay under ignored .tools.')
    if not args.output.resolve().is_relative_to(root / 'docs/evidence/m10'):
        parser.error('Allowlisted evidence must stay under docs/evidence/m10.')
    for name in ('httpx', 'httpcore', 'mcp'):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL + 1)
    try:
        config = json.loads(args.private_config.read_text(encoding='utf-8-sig'))
        evidence = asyncio.run(run_owned_demo(config, run_owned_demo=True))
    except Exception:
        print('FAIL: real demo check did not complete. No raw diagnostics were emitted; inspect scoped state before retrying writes.')
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(evidence['status'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
