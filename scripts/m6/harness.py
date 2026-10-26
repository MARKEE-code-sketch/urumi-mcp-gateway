"""Disposable M6 app using labelled, in-memory account/registry/audit stand-ins."""
from copy import deepcopy
import hmac
import os
from uuid import UUID

from starlette.responses import JSONResponse
from starlette.routing import Route

from backend.gateway.discovery import Discovery
from backend.gateway.router import Router
from backend.gateway.server import create_app
from backend.gateway.upstream_client import UpstreamClient
from scripts.m6.standins import Audit, Database, Identity, Registry, Secrets


def build(urls, tokens, hosts=('localhost', '127.0.0.1', 'urumi-m6-check-gateway')):
    db = Database()
    identity = Identity(db, tokens['key-a'], tokens['key-b'], tokens['session-a'], tokens['session-b'])
    registry = Registry(db, urls)
    secrets = Secrets({'bearer': tokens['bearer-token'], 'header': tokens['header-token']})
    audit = Audit(db, identity)
    upstream = UpstreamClient(urls.values())
    discovery = Discovery(identity, registry, secrets, upstream)
    router = Router(identity, registry, audit, discovery, upstream)
    app = create_app(router, identity, identity, hosts=hosts)

    async def control(request):
        value = request.headers.get('authorization', '')
        if not hmac.compare_digest(value, 'Bearer ' + tokens['key-a']):
            return JSONResponse({'error': 'Authentication required.'}, status_code=401)
        if request.method == 'POST':
            try:
                body = await request.json()
                action = body['action']
                if action == 'revoke_b':
                    identity.credentials[tokens['key-b']]['active'] = False
                elif action == 'audit_begin_failure':
                    audit.fail_begin = bool(body['enabled'])
                elif action == 'audit_finalize_failure':
                    audit.fail_finalize = bool(body['enabled'])
                elif action == 'server':
                    server_id = UUID(body['server_id'])
                    changes = body['changes']
                    if set(changes) - {'enabled', 'auth_type'}:
                        raise ValueError()
                    registry.edit(server_id, changes)
                elif action == 'refresh':
                    for row in await discovery.rows():
                        await discovery.schedule(row)
                else:
                    raise ValueError()
            except Exception:
                return JSONResponse({'error': 'Invalid fixture control.'}, status_code=422)
        with audit.guard:
            records = deepcopy(list(audit.records.values()))
        rows = registry.list_servers()
        return JSONResponse(dict(fixture_only=True, audit=records, servers=[dict(
            id=str(row['id']), slug=row['slug'], enabled=row['enabled'], status=row['status'],
            status_reason=row['status_reason'], version=row['version']) for row in rows]))

    app.app.routes.append(Route('/test/state', control, methods=['GET', 'POST']))
    return app


if __name__ == '__main__':
    import uvicorn
    names = {'key-a': 'GATEWAY_KEY_A', 'key-b': 'GATEWAY_KEY_B', 'session-a': 'SESSION_A',
             'session-b': 'SESSION_B', 'bearer-token': 'BEARER_TOKEN', 'header-token': 'HEADER_TOKEN'}
    tokens = {key: os.environ[value] for key, value in names.items()}
    urls = {mode: os.environ[mode.upper() + '_URL'] for mode in ('none', 'bearer', 'header')}
    uvicorn.run(build(urls, tokens), host='0.0.0.0', port=8000, access_log=False, log_level='critical')
