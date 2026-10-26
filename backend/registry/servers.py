import ipaddress
import re
from contextlib import contextmanager
from threading import Lock
from urllib.parse import urlsplit,urlunsplit
from uuid import uuid4

from backend.db.models import page_result,safe_row
from backend.errors import conflict,invalid,missing,unavailable
from backend.identity.auth import require_admin

FIELDS=('id','name','slug','enabled','status','last_checked_at','status_reason','created_at','updated_at')
RESERVED={'host','cookie','authorization','proxy-authorization','content-length','connection',
          'transfer-encoding','origin','accept','content-type'}
REASONS={'NOT_CHECKED','AUTH_FAILED','TIMEOUT','CONNECTION_FAILED',None}


def validate_url(value,allowlist):
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise invalid()
    try:
        p=urlsplit(value)
        host=p.hostname
        port=p.port
        if not host or p.username is not None or p.password is not None or p.fragment or p.query or '\\' in value:
            raise invalid()
        normalized=urlunsplit((p.scheme,host+(f':{port}' if port and port!={'http':80,'https':443}.get(p.scheme) else ''),p.path or '/', '', ''))
        if p.scheme=='http' and normalized in allowlist:
            return normalized
        if p.scheme!='https' or host.endswith('.') or host in ('localhost','metadata.google.internal') or host.endswith(('.localhost','.local','.internal','.svc','.cluster.local')):
            raise invalid()
        try:
            address=ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?',host) or '.' not in host or re.fullmatch(r'[0-9a-fx.]+',host) or any(not part for part in host.split('.')):
                raise invalid()
        else:
            if not address.is_global:
                raise invalid()
            if address.version==6:
                normalized=urlunsplit((p.scheme,f'[{host}]'+(f':{port}' if port and port!=443 else ''),p.path or '/', '', ''))
        return normalized
    except (ValueError,UnicodeError):
        raise invalid() from None


def validate_credential(value):
    if not isinstance(value,dict) or value.get('type') not in ('none','bearer','header'):
        raise invalid()
    kind=value['type']
    expected={'type'} if kind=='none' else {'type','value'} if kind=='bearer' else {'type','value','header_name'}
    if set(value)!=expected:
        raise invalid()
    if kind!='none':
        raw=value['value']
        if not isinstance(raw,str) or not raw.strip() or len(raw)>4096 or any(c in raw for c in '\r\n'):
            raise invalid()
        try:
            raw.encode('utf-8')
        except UnicodeError:
            raise invalid() from None
    if kind=='header':
        name=value['header_name']
        if not isinstance(name,str) or len(name)>100 or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name) or name.lower() in RESERVED or name.lower().startswith('mcp-'):
            raise invalid()
    return value


class Registry:
    def __init__(self,db,secrets,allowlist):
        self.db,self.secrets=db,secrets
        self._active=set()
        self._active_guard=Lock()
        self.allowlist={urlunsplit((p.scheme,p.netloc,p.path or '/', '', '')) for p in map(urlsplit,allowlist)}

    @contextmanager
    def mutation(self,server_id):
        self.db.check_owner()
        with self._active_guard:
            if server_id in self._active:
                raise conflict()
            self._active.add(server_id)
        try:
            with self.db.server_lock(server_id) as c:
                yield c
        finally:
            with self._active_guard:
                self._active.discard(server_id)

    def summary(self,row,principal):
        result=safe_row(row,FIELDS)
        if principal.role=='admin':
            result.update({'url':row['url'],'auth_type':row['auth_type'],'header_name':row['header_name']})
        return result

    def get_server(self,server_id):
        with self.db.transaction() as c:
            row=c.execute('SELECT * FROM servers WHERE id=%s',(server_id,)).fetchone()
        if not row:
            raise missing()
        return row

    def list_servers(self,enabled_only=False):
        with self.db.transaction() as c:
            return c.execute('SELECT * FROM servers WHERE (%s=false OR enabled=true) ORDER BY created_at DESC,id DESC',(enabled_only,)).fetchall()

    def get(self,principal,server_id):
        return self.summary(self.get_server(server_id),principal)

    def list(self,principal,page,per_page):
        with self.db.transaction() as c:
            rows=c.execute('SELECT * FROM servers ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s',(per_page+1,(page-1)*per_page)).fetchall()
        return page_result([self.summary(r,principal) for r in rows],page,per_page)

    def _validate(self,data,create):
        allowed={'name','url','enabled','credential'}|({'slug'} if create else set())
        if not isinstance(data,dict) or set(data)-allowed or (create and not {'name','url','slug'}<=set(data)):
            raise invalid()
        result=dict(data)
        if 'name' in result and (not isinstance(result['name'],str) or not result['name'].strip() or len(result['name'])>100):
            raise invalid()
        if 'slug' in result and (not isinstance(result['slug'],str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,23}',result['slug'])):
            raise invalid()
        if 'url' in result:
            result['url']=validate_url(result['url'],self.allowlist)
        if 'enabled' in result and type(result['enabled']) is not bool:
            raise invalid()
        if 'credential' in result:
            result['credential']=validate_credential(result['credential'])
        return result

    def create_server(self,principal,data):
        require_admin(principal)
        data=self._validate(data,True)
        data.setdefault('enabled',True)
        data.setdefault('credential',{'type':'none'})
        server_id=uuid4()
        self._replace(server_id,data,True)
        return self.get(principal,server_id)

    def update_server(self,principal,server_id,data):
        require_admin(principal)
        data=self._validate(data,False)
        self._replace(server_id,data,False)
        return self.get(principal,server_id)

    def _replace(self,server_id,data,create):
        with self.mutation(server_id) as c:
            if c.execute('SELECT id FROM secret_operations WHERE server_id=%s',(server_id,)).fetchone():
                raise conflict()
            old=c.execute('SELECT * FROM servers WHERE id=%s',(server_id,)).fetchone()
            if not create and not old:
                raise missing()
            credential=data.get('credential')
            op_id=uuid4()
            staged=f'urumi-upstream-{op_id}' if credential and credential['type']!='none' else None
            old_name=old['secret_name'] if old else None
            with c.transaction():
                if create:
                    c.execute("INSERT INTO servers(id,name,slug,url,enabled,status,auth_type) VALUES(%s,%s,%s,%s,false,'Disabled','none')",(server_id,data['name'],data['slug'],data['url']))
                c.execute("INSERT INTO secret_operations(id,server_id,phase,staged_name,old_name,new_server) VALUES(%s,%s,'prepared',%s,%s,%s)",(op_id,server_id,staged,old_name,create))
            if staged:
                # The durable intent already names this object, including on ambiguous failure.
                self.db.check_owner()
                c.execute('SELECT 1')
                self.secrets.create(staged,server_id,credential['value'])
            enabled=data.get('enabled',old['enabled'] if old else True)
            auth_type=credential['type'] if credential else old['auth_type']
            header_name=credential.get('header_name') if credential else old['header_name']
            secret_name=staged if credential else old_name
            with c.transaction():
                c.execute("UPDATE servers SET name=%s,url=%s,enabled=%s,status=%s,status_reason=%s,last_checked_at=NULL,auth_type=%s,header_name=%s,secret_name=%s,version=version+1,updated_at=now() WHERE id=%s",(data.get('name',old['name'] if old else None),data.get('url',old['url'] if old else None),enabled,'Unreachable' if enabled else 'Disabled','NOT_CHECKED' if enabled else None,auth_type,header_name,secret_name,server_id))
                c.execute("UPDATE secret_operations SET phase='committed' WHERE id=%s",(op_id,))
            if old_name and old_name!=secret_name:
                self.db.check_owner()
                c.execute('SELECT 1')
                self.secrets.delete(old_name,server_id)
            c.execute('DELETE FROM secret_operations WHERE id=%s',(op_id,))

    def remove_server(self,principal,server_id):
        require_admin(principal)
        with self.mutation(server_id) as c:
            if c.execute('SELECT id FROM secret_operations WHERE server_id=%s',(server_id,)).fetchone():
                raise conflict()
            old=c.execute('SELECT * FROM servers WHERE id=%s',(server_id,)).fetchone()
            if not old:
                raise missing()
            with c.transaction():
                c.execute("UPDATE servers SET enabled=false,status='Disabled',status_reason=NULL,updated_at=now(),version=version+1 WHERE id=%s",(server_id,))
                c.execute("INSERT INTO secret_operations(id,server_id,phase,old_name,new_server) VALUES(%s,%s,'remove',%s,false)",(uuid4(),server_id,old['secret_name']))
            self.db.check_owner()
            c.execute('SELECT 1')
            self.secrets.delete(old['secret_name'],server_id)
            with c.transaction():
                c.execute('DELETE FROM servers WHERE id=%s',(server_id,))
                c.execute('DELETE FROM secret_operations WHERE server_id=%s',(server_id,))

    def recover(self):
        self.db.check_owner()
        with self.db.transaction() as c:
            pending=c.execute('SELECT server_id FROM secret_operations ORDER BY created_at,id LIMIT 100').fetchall()
        for operation in pending:
            try:
                with self.mutation(operation['server_id']) as c:
                    row=c.execute('SELECT * FROM secret_operations WHERE server_id=%s',(operation['server_id'],)).fetchone()
                    if not row:
                        continue
                    if row['phase']=='prepared':
                        if row['staged_name']:
                            # Keep the name even if GET is absent: an ambiguous POST may finish late.
                            c.execute('INSERT INTO canceled_secret_names(name,server_id) VALUES(%s,%s) ON CONFLICT(name) DO NOTHING',(row['staged_name'],row['server_id']))
                        self.secrets.delete(row['staged_name'],row['server_id'])
                    elif row['old_name']:
                        current=c.execute('SELECT secret_name FROM servers WHERE id=%s',(row['server_id'],)).fetchone()
                        if row['phase']=='remove' or not current or row['old_name']!=current['secret_name']:
                            self.secrets.delete(row['old_name'],row['server_id'])
                    with c.transaction():
                        if row['phase']=='remove' or (row['phase']=='prepared' and row['new_server']):
                            c.execute('DELETE FROM servers WHERE id=%s',(row['server_id'],))
                        c.execute('DELETE FROM secret_operations WHERE id=%s',(row['id'],))
            except Exception:
                # Keep the exact known intent for another explicit reconciliation pass.
                continue
        with self.db.transaction() as c:
            tombstones=c.execute('SELECT * FROM canceled_secret_names ORDER BY last_checked_at,name LIMIT 100').fetchall()
        for row in tombstones:
            try:
                with self.mutation(row['server_id']) as c:
                    # Rotate attempted names even when this particular object cannot be cleaned.
                    c.execute('UPDATE canceled_secret_names SET last_checked_at=now() WHERE name=%s',(row['name'],))
                    self.secrets.delete(row['name'],row['server_id'])
            except Exception:
                continue
        with self.db.transaction() as c:
            return c.execute('SELECT count(*) AS n FROM secret_operations').fetchone()['n']

    def set_server_status(self,server_id,status,reason=None,*,expected_version=None):
        if status not in ('Connected','Unreachable') or reason not in REASONS:
            raise invalid()
        with self.db.transaction() as c:
            row=c.execute("UPDATE servers SET status=CASE WHEN enabled THEN %s ELSE 'Disabled' END,status_reason=CASE WHEN enabled THEN %s ELSE NULL END,last_checked_at=now() WHERE id=%s AND (%s::integer IS NULL OR version=%s) RETURNING id",(status,reason,server_id,expected_version,expected_version)).fetchone()
            if not row:
                if expected_version is not None:
                    return False
                raise missing()
            return True
