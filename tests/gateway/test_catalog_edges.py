import asyncio
from contextlib import asynccontextmanager
from uuid import UUID

from mcp import types
import pytest

from backend.gateway.common import GatewayError
from backend.gateway.upstream_client import UpstreamClient
from tests.gateway.test_lifecycle import isolated


@pytest.mark.parametrize('kind', ['repeated', 'pages', 'count'])
def test_discovery_page_cursor_and_tool_count_limits(kind):
    class Session:
        def __init__(self):
            self.calls=0
        async def list_tools(self,cursor=None):
            self.calls+=1
            return types.ListToolsResult(tools=[types.Tool(name='tool',inputSchema={'type':'object'})]*(201 if kind=='count' else 1),
                nextCursor='repeat' if kind=='repeated' else str(self.calls))
    session=Session()
    upstream=UpstreamClient([])
    @asynccontextmanager
    async def factory(*args):
        yield session
    upstream.session=factory
    async def check():
        with pytest.raises(GatewayError):
            await upstream.discover({},None)
        assert session.calls<=20
    asyncio.run(check())


def test_alias_collision_rejects_whole_new_snapshot(monkeypatch):
    with isolated() as (router,values):
        async def check():
            row=router.registry.get_server(UUID(int=301))
            monkeypatch.setattr('backend.gateway.discovery.public_name',lambda *args:'none__collision')
            await router.discovery.refresh(row)
            assert row['id'] not in router.discovery.snapshots
            assert router.registry.get_server(row['id'])['status']=='Unreachable'
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


def test_bad_refresh_preserves_stale_catalog_then_recovers():
    with isolated() as (router,values):
        async def check():
            principal=router.identity.validate(values['key-a'])
            first=await router.list_tools(principal)
            assert len(first)==2 and not first[0]['stale']
            original=router.upstream.discover
            async def failing(*args):
                raise GatewayError('UPSTREAM_AUTH_FAILED')
            router.upstream.discover=failing
            row=router.registry.get_server(UUID(int=301))
            await router.discovery.refresh(row)
            stale=await router.list_tools(principal)
            assert len(stale)==2 and all(item['stale'] for item in stale)
            assert router.registry.get_server(row['id'])['status_reason']=='AUTH_FAILED'
            router.upstream.discover=original
            await router.discovery.refresh(row)
            assert not (await router.list_tools(principal))[0]['stale']
            await router.discovery.close()
            await router.close()
        asyncio.run(check())


def test_never_discovered_failed_server_has_no_invented_tools():
    with isolated() as (router,values):
        async def check():
            principal=router.identity.validate(values['key-a'])
            async def failing(*args):
                raise GatewayError('UPSTREAM_UNAVAILABLE')
            router.upstream.discover=failing
            assert await router.list_tools(principal)==[]
            preview=await router.discovery.preview(principal,UUID(int=301))
            assert preview['items']==[] and not preview['stale']
            await router.discovery.close()
            await router.close()
        asyncio.run(check())
