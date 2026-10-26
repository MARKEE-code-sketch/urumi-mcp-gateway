"""Read-only Context7 lookup through the gateway; never reads its upstream token."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.live_checks import Browser, gateway, tls_context


async def main():
    logging.disable(logging.CRITICAL)
    key = json.loads((ROOT / '.tools/operator/m10/external-key.json').read_text())['raw_key']
    access = json.loads((ROOT / '.tools/operator/m10/access.json').read_text())
    context = tls_context(ROOT / '.tools/operator/m10/tls/ca.pem')
    started = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    async with gateway('https://dashboard-m10.urumi.test', context, key) as session:
        names = [tool.name for tool in (await session.list_tools()).tools]
        assert 'context7__resolve-library-id' in names and 'context7__query-docs' in names
        args = {'libraryName': 'fastapi', 'query': 'Find the official FastAPI Python framework documentation.'}
        reply = await session.call_tool('context7__resolve-library-id', args)
        data = reply.model_dump(mode='json', by_alias=True, exclude_none=True)
        assert not data.get('isError')
        text = '\n'.join(block['text'] for block in data.get('content', []) if block.get('type') == 'text')
        ids = sorted(set(value for value in re.findall(r'/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+', text)
                         if 'fastapi' in value.lower()))
        assert ids and 'invalid api key' not in text.lower() and 'unauthorized' not in text.lower()
    evidence = {'status': 'PASS', 'gateway_tool_count': len(names),
                'context7_tools': [name for name in names if name.startswith('context7__')],
                'tool': 'context7__resolve-library-id', 'arguments': args,
                'fastapi_ids': ids[:8], 'response_bytes': len(text.encode()),
                'response_sha256': hashlib.sha256(text.encode()).hexdigest()}
    admin = Browser('https://dashboard-m10.urumi.test', context)
    try:
        await admin.login(access['admin_email'], access['admin_password'])
        rows = (await admin.request('GET', '/api/v1/audit?per_page=50'))['items']
        row = next(row for row in rows if row['key_id'] == key.split('_', 2)[1]
                   and row['public_tool_name'] == evidence['tool'] and row['started_at'] >= started)
        assert row['outcome'] == 'success'
        evidence['audit'] = {field: row[field] for field in ['audit_id', 'request_id', 'user_id', 'key_id',
            'auth_source', 'server_id', 'public_tool_name', 'upstream_tool_name', 'outcome', 'duration_ms']}
        servers = (await admin.request('GET', '/api/v1/servers?per_page=50'))['items']
        own = next(server for server in servers if server['id'] == row['server_id'])
        assert own['slug'] == 'context7' and own['status'] == 'Connected'
        evidence['server_statuses'] = [{field: server[field] for field in
                                       ['name', 'slug', 'enabled', 'status', 'status_reason']} for server in servers]
    finally:
        await admin.close()
    out = ROOT / 'docs/evidence/fixes/context7-discovery-20261025/gateway-call.json'
    out.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'context7_tools': evidence['context7_tools'],
                      'fastapi_ids': evidence['fastapi_ids'], 'audit_id': evidence['audit']['audit_id']}))


if __name__ == '__main__':
    asyncio.run(main())
