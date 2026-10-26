from uuid import UUID,uuid4

from backend.db.models import page_result,safe_row
from backend.errors import PlatformError,conflict,invalid

FIELDS=('audit_id','request_id','user_id','key_id','auth_source','server_id','public_tool_name',
        'upstream_tool_name','started_at','finished_at','duration_ms','outcome','error_code','error_summary')
SUMMARIES={None:None,'KEY_REVOKED':'The personal key was revoked.',
 'UNAUTHENTICATED':'Authentication was rejected.','FORBIDDEN':'Permission was denied.',
 'TOOL_NOT_FOUND':'The requested tool was not found.','SERVER_DISABLED':'The server is disabled.',
 'UPSTREAM_ERROR':'The upstream reported an error.','TIMEOUT':'The upstream deadline expired; remote effects may be uncertain.',
 'INTERRUPTED':'The previous process stopped; the remote outcome is unknown.',
 'CONNECTION_FAILED':'The upstream connection failed.','AUTH_FAILED':'Upstream authentication failed.'}
SUMMARIES.update({'TOOL_DISABLED':'The server is disabled.',
 'UPSTREAM_TIMEOUT':'The upstream deadline expired; remote effects may be uncertain.',
 'UPSTREAM_AUTH_FAILED':'Upstream authentication failed.',
 'UPSTREAM_UNAVAILABLE':'The upstream connection failed.',
 'UPSTREAM_PROTOCOL_ERROR':'The upstream response was invalid.'})


class Audit:
    def __init__(self,db,identity):
        self.db,self.identity=db,identity

    def _values(self,request_id,principal,server_id,public_tool_name,upstream_tool_name):
        if not isinstance(request_id,UUID) or (server_id is not None and not isinstance(server_id,UUID)):
            raise invalid()
        if not isinstance(public_tool_name,str) or not 1<=len(public_tool_name)<=200:
            raise invalid()
        if upstream_tool_name is not None and (not isinstance(upstream_tool_name,str) or not 1<=len(upstream_tool_name)<=200):
            raise invalid()
        if principal is not None and principal._proof is not self.identity._proof:
            raise invalid()
        return (uuid4(),request_id,principal.user_id if principal else None,
                principal.key_id if principal else None,principal.auth_source if principal else None,
                server_id,public_tool_name,upstream_tool_name,self.db.run_id)

    def begin_attempt(self,request_id,principal,server_id,public_tool_name,upstream_tool_name=None):
        values=self._values(request_id,principal,server_id,public_tool_name,upstream_tool_name)
        try:
            self.db.check_owner()
            with self.db.transaction() as c:
                c.execute("INSERT INTO audit_records(audit_id,request_id,user_id,key_id,auth_source,server_id,public_tool_name,upstream_tool_name,run_id,outcome) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'running')",values)
        except PlatformError as error:
            if error.status==503:
                raise PlatformError(503,'AUDIT_UNAVAILABLE','Activity storage is unavailable; execution was not started.') from None
            raise
        return values[0]

    def finalize_attempt(self,audit_id,outcome,duration_ms=None,error_code=None):
        if outcome not in ('success','error','timeout','denied','unknown') or error_code not in SUMMARIES or (duration_ms is not None and (type(duration_ms) is not int or duration_ms<0)):
            raise invalid()
        try:
            self.db.check_owner()
            with self.db.transaction() as c:
                row=c.execute("UPDATE audit_records SET outcome=%s,finished_at=now(),duration_ms=%s,error_code=%s,error_summary=%s WHERE audit_id=%s AND run_id=%s AND outcome='running' RETURNING audit_id",(outcome,duration_ms,error_code,SUMMARIES[error_code],audit_id,self.db.run_id)).fetchone()
                if not row:
                    raise conflict()
        except PlatformError as error:
            if error.status==503:
                raise PlatformError(503,'AUDIT_FINALIZATION_FAILED','The activity outcome could not be saved; remote effects are uncertain.') from None
            raise

    def record_denial(self,request_id,principal,server_id,public_tool_name,error_code):
        if error_code not in SUMMARIES or error_code is None:
            raise invalid()
        values=self._values(request_id,principal,server_id,public_tool_name,None)
        try:
            self.db.check_owner()
            with self.db.transaction() as c:
                c.execute("INSERT INTO audit_records(audit_id,request_id,user_id,key_id,auth_source,server_id,public_tool_name,upstream_tool_name,run_id,outcome) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'running')",values)
                c.execute("UPDATE audit_records SET outcome='denied',finished_at=now(),duration_ms=0,error_code=%s,error_summary=%s WHERE audit_id=%s",(error_code,SUMMARIES[error_code],values[0]))
        except PlatformError as error:
            if error.status==503:
                raise PlatformError(503,'AUDIT_UNAVAILABLE','Activity storage is unavailable; execution was not started.') from None
            raise
        return values[0]

    def recover(self):
        self.db.check_owner()
        with self.db.transaction() as c:
            return c.execute("UPDATE audit_records SET outcome='unknown',finished_at=now(),duration_ms=NULL,error_code='INTERRUPTED',error_summary=%s WHERE outcome='running' AND run_id<>%s RETURNING audit_id",(SUMMARIES['INTERRUPTED'],self.db.run_id)).fetchall()

    def list(self,principal,page,per_page,server_id=None,outcome=None,user_id=None):
        if user_id is not None and principal.role!='admin':
            raise PlatformError(403,'FORBIDDEN','Admin access is required.')
        if outcome is not None and outcome not in ('running','success','error','timeout','denied','unknown'):
            raise invalid()
        clauses=[]; values=[]
        for name,value in [('user_id',principal.user_id if principal.role!='admin' else user_id),('server_id',server_id),('outcome',outcome)]:
            if value is not None:
                clauses.append(name+'=%s'); values.append(value)
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self.db.transaction() as c:
            rows=c.execute('SELECT * FROM audit_records'+where+' ORDER BY started_at DESC,audit_id DESC LIMIT %s OFFSET %s',(*values,per_page+1,(page-1)*per_page)).fetchall()
        return page_result([safe_row(r,FIELDS) for r in rows],page,per_page)
