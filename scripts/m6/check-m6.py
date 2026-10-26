"""Live isolated Kubernetes checks. Outputs contain no fixture credential values."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import subprocess
import time
from uuid import UUID

import httpx
from mcp import ClientSession, McpError
from mcp.client.streamable_http import streamable_http_client

from scripts.m6.prepare import kubectl, NAMESPACE


EVIDENCE = ROOT / 'docs/evidence/m6'
BASE = 'http://127.0.0.1:18008'


def save(name, value):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE/name).write_text(json.dumps(value, indent=2), encoding='utf-8')


@asynccontextmanager
async def client(key):
    async with httpx.AsyncClient(headers={'Authorization': 'Bearer ' + key}, timeout=20, trust_env=False) as http:
        async with streamable_http_client(BASE+'/mcp', http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                yield session, initialized.protocolVersion


async def checks(values, results):
    async with httpx.AsyncClient(base_url=BASE, timeout=20, trust_env=False,
                                headers={'Authorization': 'Bearer '+values['key-a']}) as http:
        async def state(body=None):
            response = await (http.post('/test/state', json=body) if body else http.get('/test/state'))
            response.raise_for_status()
            return response.json()
        async def record(name, value):
            results.append(dict(check=name, status='PASS', evidence=value))
            print(name+': PASS', flush=True)
        async with client(values['key-b']) as (session, protocol):
            started = time.monotonic()
            listing = await session.list_tools()
            elapsed = time.monotonic()-started
            assert len(listing.tools) == 6 and elapsed < 5
            await record('three_servers_pagination_names_protocol', dict(tool_count=6, protocol=protocol, listing_seconds=round(elapsed,3)))
            for mode in ('none','bearer','header'):
                started = time.monotonic()
                reply = await session.call_tool(mode+'__service_info', {})
                assert not reply.isError and reply.structuredContent['mode'] == mode
                assert time.monotonic()-started < 2
            current = await state()
            assert all(row['user_id'] == str(UUID(int=102)) and row['outcome']=='success' for row in current['audit'])
            await record('routing_auth_modes_and_user_b_attribution', dict(attempts=len(current['audit'])))
            result = await session.call_tool('bearer__service_info', {'action':'echo'})
            assert values['bearer-token'] not in result.model_dump_json()
            await record('echo_secret_sanitization', {'secret_matches':0})
            with_error = await session.call_tool('none__service_info', {'action':'error'})
            assert with_error.isError and json.loads(with_error.content[0].text)['fixture_only']
            await record('preserved_upstream_execution_error', {'isError':True})
            try:
                await session.call_tool('missing__tool', {})
                raise AssertionError('Unknown tool accepted.')
            except McpError:
                pass
            invalid = await session.call_tool('none__service_info', {'unknown':1})
            assert invalid.isError
            await record('unknown_protocol_and_invalid_arguments', {'denials_or_errors_visible':True})
            preview = await http.get('/api/v1/servers/'+str(UUID(int=301))+'/tools?per_page=1',
                cookies={'urumi_session':values['session-b']})
            assert preview.status_code==200 and preview.json()['has_more'] and not preview.json()['stale']
            await record('session_preview_pagination', {'items':len(preview.json()['items']), 'has_more':True})
            await state({'action':'audit_begin_failure','enabled':True})
            before = len((await state())['audit'])
            try:
                await session.call_tool('none__service_info', {})
                raise AssertionError('Audit failure accepted.')
            except McpError:
                pass
            assert len((await state())['audit'])==before
            await state({'action':'audit_begin_failure','enabled':False})
            await record('audit_start_fail_closed', {'new_attempts':0})
            started=time.monotonic()
            slow = await session.call_tool('none__service_info', {'delay':12})
            elapsed=time.monotonic()-started
            assert slow.isError and 'UPSTREAM_TIMEOUT' in slow.content[0].text and 9 <= elapsed <= 12.5
            healthy = await session.call_tool('bearer__service_info', {})
            assert not healthy.isError
            await record('ten_second_timeout_and_healthy_peer', {'timeout_seconds':round(elapsed,3)})
            # Stop an owned upstream workload, keeping the gateway and other peers live.
            old_header=json.loads(kubectl('-n',NAMESPACE,'get','pods','-l','app.kubernetes.io/component=header','-o','json').stdout)
            old_uids=[item['metadata']['uid'] for item in old_header['items']]
            kubectl('-n',NAMESPACE,'scale','deployment','urumi-m6-check-header','--replicas=0')
            started=time.monotonic()
            while time.monotonic()-started<15:
                current=await state()
                if next(row for row in current['servers'] if row['slug']=='header')['status']=='Unreachable':
                    break
                await asyncio.sleep(.5)
            else:
                raise AssertionError('Unreachable status was not observed.')
            status_seconds=time.monotonic()-started
            assert (await http.get('/readyz')).status_code==200
            assert not (await session.call_tool('bearer__service_info', {})).isError
            listing=await session.list_tools()
            assert len(listing.tools)==6 # last known header catalog retained as stale
            preview=await http.get('/api/v1/servers/'+str(UUID(int=303))+'/tools',cookies={'urumi_session':values['session-b']})
            assert preview.json()['stale']
            kubectl('-n',NAMESPACE,'scale','deployment','urumi-m6-check-header','--replicas=1')
            kubectl('-n',NAMESPACE,'rollout','status','deployment/urumi-m6-check-header','--timeout=90s')
            await state({'action':'refresh'})
            recovered=await state()
            assert next(row for row in recovered['servers'] if row['slug']=='header')['status']=='Connected'
            assert not (await session.call_tool('header__service_info', {})).isError
            new_header=json.loads(kubectl('-n',NAMESPACE,'get','pods','-l','app.kubernetes.io/component=header','-o','json').stdout)
            new_uids=[item['metadata']['uid'] for item in new_header['items']]
            assert old_uids and new_uids and set(old_uids).isdisjoint(new_uids)
            await record('controlled_pod_outage_stale_status_recovery', {'status_seconds':round(status_seconds,3),'old_pod_uids':old_uids,'new_pod_uids':new_uids})
            await state({'action':'server','server_id':str(UUID(int=301)),'changes':{'enabled':False}})
            disabled=await session.call_tool('none__service_info', {})
            assert disabled.isError and 'TOOL_DISABLED' in disabled.content[0].text
            assert len((await session.list_tools()).tools)==4
            await record('disabled_stale_name_and_fresh_listing', {'visible_tools':4})
            await state({'action':'audit_finalize_failure','enabled':True})
            try:
                await session.call_tool('bearer__service_info', {})
                raise AssertionError('Finalization failure accepted.')
            except McpError:
                pass
            assert (await state())['audit'][-1]['outcome']=='running'
            await state({'action':'audit_finalize_failure','enabled':False})
            await record('audit_finalization_uncertainty', {'durable_fixture_state':'running'})
        # Revoke B and reject its next call on an already initialized connection.
        returned_after_revoke=False
        successes_before=sum(row['outcome']=='success' for row in (await state())['audit'])
        try:
            async with client(values['key-b']) as (session,_):
                await session.list_tools()
                await state({'action':'revoke_b'})
                try:
                    await session.call_tool('bearer__service_info', {})
                    returned_after_revoke=True
                except Exception:
                    pass
        except Exception:
            pass # SDK propagates HTTP401 through its background transport task group.
        assert not returned_after_revoke
        assert sum(row['outcome']=='success' for row in (await state())['audit'])==successes_before
        response=await http.post('/mcp', headers={'Authorization':'Bearer '+values['key-b']}, json={
            'jsonrpc':'2.0','id':99,'method':'tools/call','params':{'name':'bearer__service_info','arguments':{}}})
        assert response.status_code==401
        current=await state()
        assert current['audit'][-1]['error_code']=='KEY_REVOKED'
        await record('existing_client_revocation', {'http_status':401})
        save('cluster-audit-status.json',current)
        return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cleanup',action='store_true')
    args=parser.parse_args()
    values=json.loads((ROOT/'.tools/m6/access.json').read_text())
    namespace=json.loads(kubectl('get','namespace',NAMESPACE,'-o','json').stdout)
    if namespace['metadata'].get('labels',{}).get('urumi.dev/module')!='m6-check':
        raise RuntimeError('Refusing an unowned namespace.')
    original=json.loads(kubectl('-n','urumi','get','pods,pvc','-o','json').stdout)
    baseline={item['metadata']['name']:item['metadata']['uid'] for item in original['items']}
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
    forward=subprocess.Popen(['kubectl','--kubeconfig',str(ROOT/'.tools/m1/kubeconfig.yaml'),
        '--context','k3d-urumi','-n',NAMESPACE,'port-forward','service/urumi-m6-check-gateway','18008:8000'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**flags)
    result={'status':'FAIL','checks':[]}
    try:
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            try:
                if httpx.get(BASE+'/readyz',timeout=1,trust_env=False).status_code==200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(.2)
        else:
            raise RuntimeError('Gateway did not become ready.')
        asyncio.run(checks(values,result['checks']))
        resources=json.loads(kubectl('-n',NAMESPACE,'get','pods,services,deployments,networkpolicies','-o','json').stdout)
        save('cluster-resources.json',resources)
        logs=kubectl('-n',NAMESPACE,'logs','deployment/urumi-m6-check-gateway').stdout
        if any(value in logs for value in values.values()):
            raise RuntimeError('Credential detected in logs; raw logs were not saved.')
        (EVIDENCE/'gateway-log.txt').write_text(logs,encoding='utf-8')
        saved='\n'.join(path.read_text(encoding='utf-8') for path in EVIDENCE.glob('*.json'))
        assert not any(value in saved for value in values.values())
        result.update(status='PASS_RUNTIME_REVIEW_PENDING',redaction_matches=0)
    except Exception as error:
        result['failure_type']=type(error).__name__ # never raw exception text/credentials
        raise
    finally:
        forward.terminate()
        forward.wait(timeout=10)
        after=json.loads(kubectl('-n','urumi','get','pods,pvc','-o','json').stdout)
        result['retained_identities_unchanged']=baseline=={item['metadata']['name']:item['metadata']['uid'] for item in after['items']}
        save('cluster-results.json',result)
        if args.cleanup and result['status']=='PASS_RUNTIME_REVIEW_PENDING':
            kubectl('delete','namespace',NAMESPACE,'--wait=true','--timeout=90s')
            result['owned_namespace_removed']=True
            save('cluster-results.json',result)


if __name__=='__main__':
    main()
