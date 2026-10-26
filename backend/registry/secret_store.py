import base64
import json
import re
from pathlib import Path

import httpx

from backend.errors import unavailable


class SecretStore:
    """Only M5-owned credential objects in one configured namespace."""
    def __init__(self, namespace, owner, client=None):
        self.namespace,self.owner=namespace,str(owner)
        if client is None:
            root=Path('/var/run/secrets/kubernetes.io/serviceaccount')
            client=httpx.Client(base_url='https://kubernetes.default.svc',
                headers={'Authorization':'Bearer '+root.joinpath('token').read_text().strip()},
                verify=str(root/'ca.crt'),timeout=3,follow_redirects=False,trust_env=False)
        self.client=client

    def _request(self, method, path, body=None, missing_ok=False):
        try:
            with self.client.stream(method,path,json=body) as response:
                if response.status_code==404 and missing_ok:
                    return None
                if response.status_code not in (200,201,202):
                    raise unavailable()
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data)>262144:
                        raise unavailable()
                return json.loads(data) if data else {}
        except (httpx.HTTPError,ValueError,KeyError):
            raise unavailable() from None

    def _path(self,name=None):
        if name is not None and not re.fullmatch(r'urumi-upstream-[0-9a-f-]{36}',name):
            raise unavailable()
        return f'/api/v1/namespaces/{self.namespace}/secrets'+('/'+name if name else '')

    def _labels(self, server_id):
        return {'urumi-module':'m5','urumi-owner':self.owner,'urumi-server':str(server_id)}

    def _owned(self, document, server_id):
        meta=document.get('metadata',{})
        if meta.get('namespace')!=self.namespace or any(meta.get('labels',{}).get(k)!=v for k,v in self._labels(server_id).items()):
            raise unavailable()
        return document

    def get(self,name,server_id):
        document=self._request('GET',self._path(name),missing_ok=True)
        return self._owned(document,server_id) if document is not None else None

    def create(self,name,server_id,value):
        if self.get(name,server_id) is not None:
            # Never treat an ambiguous preexisting credential as the supplied new value.
            raise unavailable()
        body={'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':self.namespace,
              'labels':self._labels(server_id)},'type':'Opaque','immutable':True,
              'data':{'value':base64.b64encode(value.encode()).decode()}}
        self._request('POST',self._path(),body)

    def resolve(self,name,server_id):
        document=self.get(name,server_id)
        if not document:
            raise unavailable()
        try:
            return base64.b64decode(document['data']['value'],validate=True).decode()
        except (KeyError,ValueError,UnicodeError):
            raise unavailable() from None

    def update_owned(self,name,server_id):
        """Update only safe owned metadata; credential replacement stays staged."""
        document=self.get(name,server_id)
        if not document:
            raise unavailable()
        document['metadata'].setdefault('annotations',{})['urumi-reconciled']='true'
        self._request('PUT',self._path(name),document)

    def delete(self,name,server_id):
        if not name:
            return
        document=self.get(name,server_id)
        if document:
            self._request('DELETE',self._path(name),{'apiVersion':'v1','kind':'DeleteOptions',
                'preconditions':{'uid':document['metadata']['uid']}},missing_ok=True)

    def close(self):
        self.client.close()
