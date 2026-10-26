"""M8 controlled API/static fixture. Never mounts production backend adapters."""
import argparse
import asyncio
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
STAMP = '2026-10-18T10:00:00Z'
ADMIN = {'id':'11111111-1111-4111-8111-111111111111','email':'admin@example.test','role':'admin','created_at':STAMP}
MEMBER = {'id':'22222222-2222-4222-8222-222222222222','email':'member@example.test','role':'member','created_at':STAMP}
SID = '33333333-3333-4333-8333-333333333333'
KID = '44444444-4444-4444-8444-444444444444'
TOKEN = 'fixture-invitation-token-for-tests'
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
sessions = {}
keys = []
summary = []
scenario = 'normal'
spent=False
pending_invites=set()
servers = []


def reset():
    global servers, keys, scenario, spent
    keys = []
    spent=False
    pending_invites.clear()
    scenario = 'normal'
    servers = [{'id':SID,'name':'WooCommerce','slug':'woo','enabled':True,'status':'Connected','last_checked_at':STAMP,'status_reason':None,'created_at':STAMP,'updated_at':STAMP,'url':'http://woo-mcp.urumi.svc.cluster.local:8000/mcp','auth_type':'bearer','header_name':None},
               {'id':'55555555-5555-4555-8555-555555555555','name':'Inventory','slug':'inventory','enabled':True,'status':'Unreachable','last_checked_at':STAMP,'status_reason':'TIMEOUT','created_at':STAMP,'updated_at':STAMP,'url':'https://inventory.example.test/mcp','auth_type':'none','header_name':None},
               {'id':'66666666-6666-4666-8666-666666666666','name':'Microsoft Learn','slug':'learn','enabled':False,'status':'Disabled','last_checked_at':None,'status_reason':None,'created_at':STAMP,'updated_at':STAMP,'url':'https://learn.microsoft.com/api/mcp','auth_type':'none','header_name':None},
               {'id':'77777777-7777-4777-8777-777777777777','name':'Never checked','slug':'fresh','enabled':True,'status':'Unreachable','last_checked_at':None,'status_reason':'NOT_CHECKED','created_at':STAMP,'updated_at':STAMP,'url':'https://fresh.example.test/mcp','auth_type':'none','header_name':None}]
reset()


def error(status=401, code='UNAUTHENTICATED', message='Login is required.'):
    return JSONResponse({'error':{'code':code,'message':message,'request_id':'88888888-8888-4888-8888-888888888888'}}, status_code=status)


def page(request, items, **extra):
    n = int(request.query_params.get('page','1'))
    size = int(request.query_params.get('per_page','20'))
    if n < 1 or not 1 <= size <= 50:
        return error(422, 'INVALID_INPUT', 'Invalid page.')
    return {'items':items[(n-1)*size:n*size], 'page':n, 'per_page':size, 'has_more':len(items)>n*size, **extra}


def public(server, user):
    return {k:v for k,v in server.items() if user['role']=='admin' or k not in ('url','auth_type','header_name')}


@app.middleware('http')
async def protection(request, call_next):
    response = await call_next(request)
    response.headers.update({'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"})
    if request.url.path.startswith('/api/v1'):
        summary.append({'method':request.method,'path':request.url.path,'status':response.status_code})
        if len(summary)>1000: del summary[:500]
    return response


@app.get('/livez')
async def live(): return Response('live', media_type='text/plain')


@app.get('/readyz')
async def ready():
    target = os.getenv('M8_STATIC_ORIGIN')
    if target:
        try:
            async with httpx.AsyncClient(timeout=2, trust_env=False, follow_redirects=False) as client:
                r = await client.get(target+'/readyz')
                if r.status_code != 200: return Response(status_code=503)
        except Exception: return Response(status_code=503)
    return Response('ready', media_type='text/plain')


@app.post('/test/control')
async def control(request:Request):
    global scenario
    data = await request.json()
    if data.get('reset'): reset(); sessions.clear(); summary.clear()
    if data.get('expire'): sessions.clear()
    scenario = data.get('scenario', scenario)
    return {'ok':True}


@app.get('/test/summary')
async def observed(): return {'requests':summary}


@app.api_route('/api/v1/{path:path}', methods=['GET','POST','PATCH','DELETE'])
async def api(path:str, request:Request):
    global servers, spent
    change = request.method != 'GET'
    raw=bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw)>16384:return error(422,'INVALID_INPUT','Input is too large.')
    try:
        data=json.loads(raw) if raw else {}
        if not isinstance(data,dict):raise ValueError()
    except (ValueError,UnicodeError):return error(422,'INVALID_INPUT','Input is invalid.')
    origin = os.getenv('M8_ORIGIN','http://127.0.0.1:18080')
    if change and request.headers.get('origin') != origin:
        return error(403,'REQUEST_REJECTED','Origin was rejected.')
    if path=='auth/login':
        user = ADMIN if data.get('email')==ADMIN['email'] else MEMBER if data.get('email')==MEMBER['email'] else None
        if not user or data.get('password')!='Fixture-password-123': return error()
        token = secrets.token_urlsafe(24); csrf=secrets.token_urlsafe(24)
        sessions[token]=(user,csrf)
        response=JSONResponse({'user':user,'csrf_token':csrf})
        response.set_cookie('urumi_session',token,httponly=True,samesite='lax',path='/')
        return response
    if path=='invitations/redeem':
        if scenario=='expired' or data.get('token')!=TOKEN: return error(422,'INVALID_INPUT','Invitation is invalid or expired.')
        if spent:return error(409,'CONFLICT','Invitation is invalid or already consumed.')
        password=data.get('password','')
        if not 12<=len(password)<=128 or len(password.encode('utf-8'))>512:return error(422,'INVALID_INPUT','Password does not meet limits.')
        spent=True
        return JSONResponse({'user':MEMBER},status_code=201)
    entry=sessions.get(request.cookies.get('urumi_session'))
    if not entry: return error()
    user,csrf=entry
    if change and request.headers.get('x-csrf-token')!=csrf: return error(403,'REQUEST_REJECTED','CSRF was rejected.')
    if path=='auth/me': return {'user':user,'csrf_token':csrf}
    if path=='auth/logout':
        sessions.pop(request.cookies.get('urumi_session'),None)
        response=Response(status_code=204); response.delete_cookie('urumi_session'); return response
    if scenario=='unavailable': return error(503,'DEPENDENCY_UNAVAILABLE','A required dependency is unavailable.')
    if scenario=='forbidden': return error(403,'FORBIDDEN','This action is denied.')
    if scenario=='delay': await asyncio.sleep(1)
    if path=='members':
        return page(request,[ADMIN,MEMBER]) if user['role']=='admin' else error(403,'FORBIDDEN','Admin access is required.')
    if path=='invitations':
        if user['role']!='admin': return error(403,'FORBIDDEN','Admin access is required.')
        if data.get('email') in (ADMIN['email'],MEMBER['email']) or data.get('email') in pending_invites: return error(409,'CONFLICT','The account already exists.')
        pending_invites.add(data.get('email'))
        return JSONResponse({'id':KID,'expires_at':'2026-10-19T10:00:00Z','invite_url':origin+'/invite#token='+TOKEN},status_code=201)
    if path.startswith('members/') and '/keys' in path:
        parts=path.split('/'); owner=parts[1]
        if user['role']!='admin' and owner!=user['id']: return error(403,'FORBIDDEN','This owner is not permitted.')
        if request.method=='GET': return page(request,[k for k in keys if k['user_id']==owner])
        if request.method=='DELETE':
            for key in keys:
                if key['id']==parts[-1] and key['user_id']==owner:key['revoked_at']=STAMP
            return Response(status_code=204)
        key={'id':str(uuid4()),'user_id':owner,'label':data.get('label'),'prefix':'demo-prefix','created_at':STAMP,'revoked_at':None}
        keys.append(key)
        return JSONResponse({**key,'raw_key':'fixture-one-time-key-not-a-real-credential'},status_code=201)
    if path=='servers' and request.method=='GET': return page(request,[public(s,user) for s in servers])
    if path=='servers' and request.method=='POST':
        if user['role']!='admin': return error(403,'FORBIDDEN','Admin access is required.')
        if any(s['slug']==data['slug'] for s in servers):return error(409,'CONFLICT','This slug already exists.')
        s={**servers[0],**{k:v for k,v in data.items() if k!='credential'},'id':'99999999-9999-4999-8999-999999999999','status':'Unreachable','status_reason':'NOT_CHECKED','last_checked_at':None}
        s['auth_type']=data.get('credential',{'type':'none'})['type'];servers.append(s);return JSONResponse(public(s,user),status_code=201)
    if path.startswith('servers/'):
        sid=path.split('/')[1]; s=next((s for s in servers if s['id']==sid),None)
        if not s:return error(404,'NOT_FOUND','Server not found.')
        if path.endswith('/tools'):
            tools=[] if not s['enabled'] or s['status_reason']=='NOT_CHECKED' else [{'gateway_name':s['slug']+'__service_info','upstream_name':'service_info','description':'<img src="https://evil.example/x" onerror="alert(1)"> untrusted text','inputSchema':{'type':'object','properties':{}}}]
            return page(request,tools,stale=s['enabled'] and s['status']=='Unreachable' and bool(tools))
        if request.method=='GET':return public(s,user)
        if user['role']!='admin':return error(403,'FORBIDDEN','Admin access is required.')
        if request.method=='DELETE':servers.remove(s);return Response(status_code=204)
        s.update({k:v for k,v in data.items() if k!='credential'})
        if 'credential'in data:s['auth_type']=data['credential']['type'];s['header_name']=data['credential'].get('header_name')
        if 'enabled'in data:s['status']='Unreachable' if s['enabled'] else 'Disabled'
        return public(s,user)
    if path=='audit':
        rows=[{'audit_id':f'aaaaaaaa-aaaa-4aaa-8aaa-{i:012d}','request_id':KID,'user_id':MEMBER['id'] if i%2 else ADMIN['id'],'key_id':None,'auth_source':'session','server_id':SID if i%2 else None,'public_tool_name':'woo__list_orders','upstream_tool_name':'list_orders','started_at':STAMP,'finished_at':None if i==0 else STAMP,'duration_ms':None if i==0 else 12,'outcome':o,'error_code':None,'error_summary':None}for i,o in enumerate(['running','success','error','timeout','denied','unknown'])]
        if user['role']=='member':rows=[r for r in rows if r['user_id']==user['id']]
        for field in ('outcome','server_id','user_id'):
            if request.query_params.get(field):rows=[r for r in rows if r[field]==request.query_params[field]]
        return page(request,rows)
    if path=='chat':
        if set(data)!={'message'}:return error(422,'INVALID_INPUT','Only message is accepted.')
        if scenario=='overload':return error(429,'OVERLOADED','Chat is busy. Try later.')
        if scenario=='provider':return error(503,'DEPENDENCY_UNAVAILABLE','Provider is unavailable.')
        text=data['message']; tools=[]; answer='Hello. No tools were needed.'; state='completed'
        if 'product'in text:answer='Product created.'; tools=['woo__create_product']
        if 'today'in text:answer="Today's orders: 2. Asia/Kolkata.";tools=['woo__list_orders']
        if 'cross'in text:answer='Inventory and shop checked.';tools=['woo__list_orders','inventory__lookup_sku']
        if 'partial'in text:answer='Partial result; not all orders could be read.';tools=['woo__list_orders'];state='limit_reached'
        if 'unknown'in text:answer='The remote write may have happened. Inspect Audit before repeating.';tools=['woo__create_product'];state='failed'
        if 'hostile'in text:answer='<script>alert(1)</script> is plain text.'
        if 'formatted'in text:
            answer='Products with **IDs**, **SKUs** and **INR prices**:\n\n| Product ID | SKU | INR price |\n| --- | --- | ---: |\n| 12 | DEMO-001 | ₹499.00 |\n| 18 | M10-BROWSER-NOTEBOOK | ₹129.00 |\n| 20 | M10-TLS-PROBE | ₹1.00 |\n\nPrices are current regular prices.'
            tools=['woo__list_products']
        return {'request_id':KID,'state':state,'answer':answer,'tool_calls':[{'call_id':str(i),'tool_name':t,'server_id':SID,'outcome':'unknown' if 'unknown'in text else 'timeout' if 'partial'in text else 'success','duration_ms':None if 'unknown'in text else 12,'audit_id':KID,'error_code':None}for i,t in enumerate(tools)]}
    return error(404,'NOT_FOUND','Route not found.')


@app.get('/{path:path}')
async def asset(path:str):
    if path.startswith(('api/','mcp','test/')):return Response(status_code=404)
    known=path in ('','login','invite','servers','members','keys','audit','chat')
    target=os.getenv('M8_STATIC_ORIGIN')
    if target:
        if not known and not path.startswith('assets/'):return Response(status_code=404)
        try:
            async with httpx.AsyncClient(timeout=3,trust_env=False,follow_redirects=False) as client:r=await client.get(target+'/'+path)
            return Response(r.content,status_code=r.status_code,media_type=r.headers.get('content-type'))
        except Exception:return Response(status_code=503)
    root=Path(os.getenv('M8_DIST',str(ROOT/'frontend/dist'))).resolve()
    file=root/('index.html' if known else path)
    if not file.resolve().is_relative_to(root) or not file.is_file():return Response(status_code=404)
    import mimetypes
    return Response(file.read_bytes(),media_type=mimetypes.guess_type(str(file))[0])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=18080);args=parser.parse_args()
    uvicorn.run(app,host=args.host,port=args.port,access_log=False,log_level='warning')
