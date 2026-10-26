"""Discovery allows a normal remote handshake while bounding stalled peers."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from mcp import types
import pytest

import backend.gateway.discovery as discovery_module
from backend.gateway.discovery import Discovery


class Registry:
    def __init__(self, *rows):
        self.rows = {row['id']: row for row in rows}

    def list_servers(self, enabled_only=False):
        return [dict(row) for row in self.rows.values() if not enabled_only or row['enabled']]

    def get_server(self, server_id):
        return dict(self.rows[server_id])

    def set_server_status(self, server_id, status, reason=None, *, expected_version=None):
        row = self.rows[server_id]
        if expected_version != row['version']:
            return False
        row.update(status=status, status_reason=reason)
        return True


def row(slug):
    return dict(id=uuid4(), slug=slug, enabled=True, version=1, auth_type='none',
                status='Unreachable', status_reason='NOT_CHECKED')


def tool():
    return types.Tool(name='lookup', description='Fixture lookup',
                      inputSchema={'type': 'object', 'properties': {}})


def test_remote_handshake_longer_than_three_seconds_can_be_discovered():
    async def scenario():
        remote = row('remote')
        registry = Registry(remote)

        async def discover(server, credential):
            # The observed remote initialization/list round trips take over three seconds.
            await asyncio.sleep(3.1)
            return [tool()]

        discovery = Discovery(SimpleNamespace(revalidate=lambda principal: principal), registry,
                              None, SimpleNamespace(discover=discover))
        try:
            items = await discovery.list_tools(object())
            assert [item['name'] for item in items] == ['remote__lookup']
            assert remote['status'] == 'Connected' and remote['status_reason'] is None
            assert not items[0]['stale']
        finally:
            await discovery.close()

    asyncio.run(scenario())


@pytest.mark.parametrize('stalled_stage', ['credential', 'upstream'])
def test_whole_discovery_deadline_stops_stalled_stage_without_losing_healthy_peer(monkeypatch, stalled_stage):
    # Keep the deadline test fast while exercising the same production timeout scope.
    monkeypatch.setattr(discovery_module, 'DISCOVERY_TIMEOUT', .05)

    async def scenario():
        stalled, healthy = row('stalled'), row('healthy')
        registry = Registry(stalled, healthy)
        cancelled = []
        reached_upstream = []

        async def never_finishes(stage):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(stage)

        async def secret(server):
            if server['id'] == stalled['id'] and stalled_stage == 'credential':
                await never_finishes('credential')
            return None

        async def discover(server, credential):
            reached_upstream.append(server['id'])
            if server['id'] == stalled['id'] and stalled_stage == 'upstream':
                await never_finishes('upstream')
            return [tool()]

        discovery = Discovery(SimpleNamespace(revalidate=lambda principal: principal), registry,
                              None, SimpleNamespace(discover=discover))
        monkeypatch.setattr(discovery, 'secret', secret)
        try:
            items = await asyncio.wait_for(discovery.list_tools(object()), timeout=2)
            assert [item['name'] for item in items] == ['healthy__lookup']
            assert healthy['status'] == 'Connected'
            assert stalled['status'] == 'Unreachable' and stalled['status_reason'] == 'TIMEOUT'
            assert stalled['id'] not in discovery.snapshots
            assert cancelled == [stalled_stage]
            if stalled_stage == 'credential':
                assert stalled['id'] not in reached_upstream
        finally:
            await discovery.close()

    asyncio.run(scenario())
