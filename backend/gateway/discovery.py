"""Atomic, version-bound tool catalogs. Failed peers do not block healthy ones."""
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import re

from jsonschema.validators import validator_for

from backend.errors import PlatformError
from backend.gateway.common import Blocking, GatewayError
from backend.gateway.upstream_client import depth, redact
from backend.gateway.schema import check_schema

DISCOVERY_TIMEOUT = 10


def failure_code(error):
    if isinstance(error, GatewayError):
        return error.code
    if isinstance(error, BaseExceptionGroup):
        codes = [failure_code(item) for item in error.exceptions]
        if 'UPSTREAM_AUTH_FAILED' in codes:
            return 'UPSTREAM_AUTH_FAILED'
        if 'UPSTREAM_TIMEOUT' in codes:
            return 'UPSTREAM_TIMEOUT'
        return codes[0]
    if isinstance(error, TimeoutError):
        return 'UPSTREAM_TIMEOUT'
    return 'UPSTREAM_UNAVAILABLE'


def public_name(slug, original):
    if not isinstance(original, str) or not 1 <= len(original) <= 200:
        raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
    try:
        encoded = original.encode('utf-8')
    except UnicodeError:
        raise GatewayError('UPSTREAM_PROTOCOL_ERROR') from None
    if re.fullmatch(r'[A-Za-z0-9_.-]+', original) and not original.startswith('h_') and len(slug + '__' + original) <= 64:
        return slug + '__' + original
    return slug + '__h_' + sha256(encoded).hexdigest()[:32]


class Discovery:
    def __init__(self, identity, registry, secrets, upstream, blocking=None):
        self.identity, self.registry, self.secrets, self.upstream = identity, registry, secrets, upstream
        self.blocking = blocking or Blocking()
        self.snapshots = {}
        self.inflight = {}
        self.slots = asyncio.Semaphore(4)
        self.task = None

    async def secret(self, row):
        if row['auth_type'] == 'none':
            return None
        return await self.blocking.run(self.secrets.resolve, row['secret_name'], row['id'])

    async def rows(self):
        rows = await self.blocking.run(self.registry.list_servers, True)
        if len(rows) > 20:
            raise PlatformError(503, 'CATALOG_LIMIT', 'The enabled server limit was exceeded.')
        current = {row['id']: row['version'] for row in rows}
        self.snapshots = {key: value for key, value in self.snapshots.items()
                          if current.get(key) == value['version']}
        return rows

    async def refresh(self, row):
        try:
            async with self.slots:
                # Credential lookup plus remote MCP initialization needs several round trips.
                async with asyncio.timeout(DISCOVERY_TIMEOUT):
                    secret = await self.secret(row)
                    tools = await self.upstream.discover(row, secret)
                    items, names = [], set()
                    for tool in tools:
                        payload = tool.model_dump(mode='json', exclude_none=True)
                        if len(json.dumps(payload).encode()) > 65536:
                            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                        name = public_name(row['slug'], tool.name)
                        if name in names:
                            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                        names.add(name)
                        depth(payload)
                        for schema_name in ('inputSchema', 'outputSchema'):
                            if schema_name in payload:
                                await self.blocking.run(check_schema, payload[schema_name])
                        # Never change routing/schema names to mask a leaked credential.
                        clean = redact(payload, secret)
                        if clean.get('name') != payload.get('name') or clean.get('inputSchema') != payload.get('inputSchema') or clean.get('outputSchema') != payload.get('outputSchema'):
                            raise GatewayError('UPSTREAM_PROTOCOL_ERROR')
                        item = dict(name=name, server_id=str(row['id']), server_slug=row['slug'],
                                    upstream_name=tool.name, description=clean.get('description', ''),
                                    inputSchema=clean['inputSchema'], stale=False)
                        for field in ('outputSchema', 'annotations'):
                            if field in clean:
                                item[field] = clean[field]
                        items.append(item)
                    current = await self.blocking.run(self.registry.get_server, row['id'])
                    if not current['enabled'] or current['version'] != row['version']:
                        return
                    saved = await self.blocking.run(self.registry.set_server_status, row['id'],
                        'Connected', None, expected_version=row['version'])
                    if saved is not False:
                        self.snapshots[row['id']] = dict(version=row['version'], items=items, stale=False)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            code = failure_code(error)
            old = self.snapshots.get(row['id'])
            if old and old['version'] == row['version']:
                old['stale'] = True
            reason = {'UPSTREAM_AUTH_FAILED': 'AUTH_FAILED', 'UPSTREAM_TIMEOUT': 'TIMEOUT'}.get(code, 'CONNECTION_FAILED')
            try:
                await self.blocking.run(self.registry.set_server_status, row['id'],
                    'Unreachable', reason, expected_version=row['version'])
            except Exception:
                pass

    def schedule(self, row):
        key = (row['id'], row['version'])
        existing = self.inflight.get(key)
        if existing:
            return existing
        task = asyncio.create_task(self.refresh(row))
        self.inflight[key] = task
        task.add_done_callback(lambda _: self.inflight.pop(key, None))
        return task

    async def list_tools(self, principal):
        await self.blocking.run(self.identity.revalidate, principal)
        rows = await self.rows()
        missing = [self.schedule(row) for row in rows if row['id'] not in self.snapshots]
        if missing:
            await asyncio.gather(*(asyncio.shield(task) for task in missing))
        # Reread after remote discovery: an admin may have disabled a server meanwhile.
        rows = await self.rows()
        items = []
        for row in rows:
            snapshot = self.snapshots.get(row['id'])
            if snapshot and snapshot['version'] == row['version']:
                for item in snapshot['items']:
                    items.append(dict(item, stale=snapshot['stale']))
        if len(items) > 1000 or len(json.dumps(items).encode()) > 8 * 1024**2:
            raise PlatformError(503, 'CATALOG_LIMIT', 'The merged tool catalog limit was exceeded.')
        return deepcopy(sorted(items, key=lambda item: (item['server_id'], item['name'])))

    async def lookup(self, principal, name):
        # Retain old mappings to identify disabled attempts before current listing evicts them.
        for server_id, snapshot in self.snapshots.items():
            for item in snapshot['items']:
                if item['name'] == name:
                    return deepcopy(item), snapshot['version']
        for item in await self.list_tools(principal):
            if item['name'] == name:
                row = await self.blocking.run(self.registry.get_server, __import__('uuid').UUID(item['server_id']))
                snapshot = self.snapshots.get(row['id'])
                if not snapshot or not row['enabled'] or snapshot['version'] != row['version'] or item not in [dict(value, stale=snapshot['stale']) for value in snapshot['items']]:
                    raise GatewayError('TOOL_NOT_FOUND', 'denied')
                return item, snapshot['version']
        raise GatewayError('TOOL_NOT_FOUND', 'denied')

    async def preview(self, principal, server_id, page=1, per_page=20):
        if type(page) is not int or page < 1 or type(per_page) is not int or not 1 <= per_page <= 50:
            raise PlatformError(422, 'INVALID_INPUT', 'The supplied input is invalid.')
        await self.blocking.run(self.identity.revalidate, principal)
        row = await self.blocking.run(self.registry.get_server, server_id)
        items = [item for item in await self.list_tools(principal) if item['server_id'] == str(server_id)] if row['enabled'] else []
        items.sort(key=lambda item: item['name'])
        offset = (page - 1) * per_page
        selected = []
        for item in items[offset:offset + per_page]:
            selected.append({('gateway_name' if key == 'name' else key): value for key, value in item.items()
                             if key not in ('server_id', 'server_slug', 'stale')})
        return dict(items=selected, page=page, per_page=per_page, has_more=offset + per_page < len(items),
                    stale=bool(items and items[0]['stale']))

    async def poll(self):
        while True:
            try:
                for row in await self.rows():
                    self.schedule(row)
            except Exception:
                pass
            await asyncio.sleep(5)

    async def start(self):
        self.task = asyncio.create_task(self.poll())

    async def close(self):
        tasks = list(self.inflight.values()) + ([self.task] if self.task else [])
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.blocking.close()
