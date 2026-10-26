"""M5 API factory, composed only in the isolated harness until M10."""
import json
from dataclasses import dataclass
from functools import wraps
from urllib.parse import urlsplit
from uuid import UUID,uuid4

from fastapi import FastAPI,Request,Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool

from backend.errors import PlatformError,invalid


@dataclass(frozen=True)
class BrowserConfig:
    origin: str
    local_http: bool=False
    listen_host: str='127.0.0.1'

    def __post_init__(self):
        parsed=urlsplit(self.origin)
        if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password or not parsed.hostname:
            raise ValueError('An exact browser origin is required.')
        if self.local_http:
            if parsed.scheme!='http' or parsed.hostname not in ('localhost','127.0.0.1') or self.listen_host not in ('localhost','127.0.0.1'):
                raise ValueError('Local HTTP requires loopback origin and listener.')
        elif parsed.scheme!='https':
            raise ValueError('HTTPS browser origin is required.')


class BodyLimit:
    def __init__(self,app):
        self.app=app

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        data=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':
                return
            data.extend(message.get('body',b''))
            if len(data)>16384:
                response=JSONResponse({'error':{'code':'INVALID_INPUT','message':'The supplied input is invalid.',
                    'request_id':str(uuid4())}},status_code=422,headers={'Cache-Control':'no-store'})
                return await response(scope,receive,send)
            if not message.get('more_body',False):
                break
        delivered=False
        async def bounded():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(data),'more_body':False}
            return await receive()
        await self.app(scope,bounded,send)


def create_api(db,identity,members,keys,registry,audit,config,blocking=run_in_threadpool):
    app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)

    def in_adapter(function):
        @wraps(function)
        async def adapted(*args,**kwargs):
            return await blocking(function,*args,**kwargs)
        return adapted

    @app.exception_handler(PlatformError)
    async def platform_error(request,error):
        return JSONResponse({'error':{'code':error.code,'message':error.message,
             'request_id':getattr(request.state,'request_id',str(uuid4()))}},status_code=error.status,
             headers={'Cache-Control':'no-store'})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request,error):
        return await platform_error(request,invalid())

    @app.exception_handler(HTTPException)
    async def http_error(request,error):
        code='NOT_FOUND' if error.status_code==404 else 'INVALID_INPUT'
        return await platform_error(request,PlatformError(error.status_code,code,'The request could not be completed.'))

    @app.middleware('http')
    async def context(request,call_next):
        request.state.request_id=str(uuid4())
        try:
            response=await call_next(request)
        except PlatformError as error:
            response=await platform_error(request,error)
        except Exception:
            response=await platform_error(request,PlatformError(503,'DEPENDENCY_UNAVAILABLE','A required dependency is unavailable.'))
        response.headers['Cache-Control']='no-store'
        return response

    def origin(request):
        if request.headers.get('origin')!=config.origin:
            raise PlatformError(403,'REQUEST_REJECTED','The request was rejected.')

    def caller(request,change=False):
        principal=identity.session(request.cookies.get('urumi_session'))
        principal=identity.revalidate(principal)
        if change:
            origin(request)
            identity.check_csrf(principal,request.headers.get('x-csrf-token'))
        return principal

    async def body(request,required,optional=()):
        try:
            data=await request.json()
        except (ValueError,UnicodeError):
            raise invalid() from None
        if not isinstance(data,dict) or not set(required)<=set(data) or set(data)-set(required)-set(optional):
            raise invalid()
        return data

    def pages(page,per_page):
        if page<1 or not 1<=per_page<=50:
            raise invalid()

    @app.get('/health/live')
    @in_adapter
    def live():
        return {'status':'live'}

    @app.get('/health/ready')
    @in_adapter
    def ready():
        db.check_owner()
        with db.transaction() as c:
            if c.execute('SELECT max(version) AS version FROM schema_version').fetchone()['version']!=3 or c.execute('SELECT count(*) AS n FROM secret_operations').fetchone()['n']:
                raise PlatformError(503,'DEPENDENCY_UNAVAILABLE','Recovery is required.')
        return {'status':'ready'}

    @app.post('/api/v1/auth/login')
    async def login(request:Request,response:Response):
        origin(request)
        data=await body(request,('email','password'))
        reply,token=await blocking(identity.login,data['email'],data['password'],request.cookies.get('urumi_session'))
        response.set_cookie('urumi_session',token,max_age=28800,httponly=True,secure=not config.local_http,samesite='lax',path='/')
        return reply

    @app.post('/api/v1/auth/logout',status_code=204)
    @in_adapter
    def logout(request:Request):
        identity.logout(caller(request,True))
        response=Response(status_code=204)
        response.delete_cookie('urumi_session',path='/',httponly=True,secure=not config.local_http,samesite='lax')
        return response

    @app.get('/api/v1/auth/me')
    @in_adapter
    def me(request:Request):
        return identity.me(caller(request),request.cookies.get('urumi_session'))

    @app.post('/api/v1/invitations',status_code=201)
    async def invite(request:Request):
        data=await body(request,('email','role'))
        def perform():
            return members.invite(caller(request,True),data['email'],data['role'])
        return await blocking(perform)

    @app.post('/api/v1/invitations/redeem',status_code=201)
    async def redeem(request:Request):
        origin(request)
        data=await body(request,('token','password'))
        return await blocking(members.redeem,data['token'],data['password'])

    @app.get('/api/v1/members')
    @in_adapter
    def list_members(request:Request,page:int=1,per_page:int=20):
        pages(page,per_page)
        return members.list(caller(request),page,per_page)

    @app.post('/api/v1/members/{user_id}/keys',status_code=201)
    async def issue_key(user_id:UUID,request:Request):
        data=await body(request,('label',))
        def perform():
            return keys.issue(caller(request,True),user_id,data['label'])
        return await blocking(perform)

    @app.get('/api/v1/members/{user_id}/keys')
    @in_adapter
    def list_keys(user_id:UUID,request:Request,page:int=1,per_page:int=20):
        pages(page,per_page)
        return keys.list(caller(request),user_id,page,per_page)

    @app.delete('/api/v1/members/{user_id}/keys/{key_id}',status_code=204)
    @in_adapter
    def revoke_key(user_id:UUID,key_id:UUID,request:Request):
        keys.revoke(caller(request,True),user_id,key_id)
        return Response(status_code=204)

    @app.get('/api/v1/servers')
    @in_adapter
    def list_servers(request:Request,page:int=1,per_page:int=20):
        pages(page,per_page)
        return registry.list(caller(request),page,per_page)

    @app.get('/api/v1/servers/{server_id}')
    @in_adapter
    def get_server(server_id:UUID,request:Request):
        return registry.get(caller(request),server_id)

    @app.post('/api/v1/servers',status_code=201)
    async def create_server(request:Request):
        data=await body(request,('name','slug','url'),('enabled','credential'))
        def perform():
            return registry.create_server(caller(request,True),data)
        return await blocking(perform)

    @app.patch('/api/v1/servers/{server_id}')
    async def update_server(server_id:UUID,request:Request):
        data=await body(request,(),('name','url','enabled','credential'))
        def perform():
            return registry.update_server(caller(request,True),server_id,data)
        return await blocking(perform)

    @app.delete('/api/v1/servers/{server_id}',status_code=204)
    @in_adapter
    def remove_server(server_id:UUID,request:Request):
        registry.remove_server(caller(request,True),server_id)
        return Response(status_code=204)

    @app.get('/api/v1/audit')
    @in_adapter
    def list_audit(request:Request,page:int=1,per_page:int=20,server_id:UUID|None=None,
                   outcome:str|None=None,user_id:UUID|None=None):
        pages(page,per_page)
        return audit.list(caller(request),page,per_page,server_id,outcome,user_id)

    return BodyLimit(app)
