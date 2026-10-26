"""Live acceptance of the owned, disposable M5 harness; never prints credentials."""
import sys
# Direct-file execution must not let nearby operator.py shadow Python's operator module.
if sys.path and sys.path[0].replace("\\", "/").rstrip("/").endswith("/scripts/m5"):
    sys.path.pop(0)
import argparse
import base64
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from uuid import UUID, uuid4

import httpx
import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.db.database import Database
from backend.identity.auth import Identity
from backend.identity.api_keys import ApiKeys
from backend.audit.records import Audit
from backend.errors import PlatformError

NS = "urumi-m5-check"
SNS = "urumi-m5-upstream-secrets-check"
DB_DEPLOY = NS + "-platform-db"
APP_DEPLOY = NS + "-m5-harness"
PVC = NS + "-platform-data"
ORIGIN = "https://gateway.example.test"
EVIDENCE = ROOT / "docs/evidence/m5"
PRIVATE = ROOT / ".tools/m5"
KCFG = str(ROOT / ".tools/m1/kubeconfig.yaml")


class CheckFailed(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise CheckFailed(message)


def kube(*args, payload=None, timeout=180, binary=False):
    command = ["kubectl", "--kubeconfig", KCFG, "--context", "k3d-urumi", *args]
    result = subprocess.run(command, input=payload, capture_output=True, text=not binary, timeout=timeout)
    require(result.returncode == 0, "A scoped Kubernetes operation failed; sensitive output suppressed.")
    return result.stdout


def document(*args):
    return json.loads(kube(*args, "-o", "json"))


def apply(value):
    kube("apply", "-f", "-", payload=json.dumps(value))


def wait_until(check, message, seconds=150):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (httpx.HTTPError, OSError, CheckFailed, psycopg.Error):
            pass
        time.sleep(2)
    raise CheckFailed(message)


class Forward:
    def __init__(self, service, local, remote):
        self.service, self.local, self.remote, self.process = service, local, remote, None

    def start(self):
        self.close()
        self.process = subprocess.Popen(["kubectl", "--kubeconfig", KCFG, "--context", "k3d-urumi", "-n", NS,
            "port-forward", "--address", "127.0.0.1", "service/" + self.service, f"{self.local}:{self.remote}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def connected():
            require(self.process.poll() is None, "Loopback forwarding stopped.")
            with socket.create_connection(("127.0.0.1", self.local), timeout=1):
                return True
        wait_until(connected, "Loopback forwarding did not become ready.", 30)

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(5)


def owned_namespace(name):
    labels = document("get", "namespace", name)["metadata"].get("labels", {})
    require(labels.get("urumi-module") == "m5" and labels.get("urumi-owner") == NS,
            "Namespace ownership mismatch; refuse mutation or cleanup.")


def pod(component):
    items = document("-n", NS, "get", "pods", "-l", "app.kubernetes.io/component=" + component)["items"]
    live = [p for p in items if not p["metadata"].get("deletionTimestamp")]
    require(len(live) == 1, "Expected exactly one current owned workload Pod.")
    return live[0]


def identities(value):
    return sorted((p["kind"], p["metadata"]["name"], p["metadata"]["uid"]) for p in value["items"])


class Runner:
    def __init__(self, cleanup):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        self.results = {"module": "M5", "status": "RUNNING", "checks": [], "synthetic_audits_only": True}
        self.cleanup = cleanup
        self.db_forward = Forward(DB_DEPLOY, 15436, 5432)
        self.app_forward = Forward(APP_DEPLOY, 18006, 8000)
        self.http = httpx.Client(base_url="http://127.0.0.1:18006", trust_env=False, timeout=45)
        password = json.loads((PRIVATE / "db.json").read_text())["password"]
        self.db = Database(psycopg.conninfo.make_conninfo(host="127.0.0.1", port=15436, user="urumi", dbname="urumi", password=password))
        self.protected = [password]
        self.sessions = {}

    def save(self):
        (EVIDENCE / "cluster-results.json").write_text(json.dumps(self.results, indent=2) + "\n", encoding="utf-8")

    def passed(self, name, **details):
        self.results["checks"].append({"name": name, "status": "PASS", **details})
        self.save()
        print("PASS:", name, flush=True)

    def request(self, method, path, expected=200, who=None, value=None, headers=None):
        self.results["last_action"] = {"method": method, "path": path}
        self.save()
        request_headers = {"Origin": ORIGIN}
        if who:
            cookie, csrf = self.sessions[who]
            request_headers.update(Cookie="urumi_session=" + cookie, **{"X-CSRF-Token": csrf})
        request_headers.update(headers or {})
        reply = self.http.request(method, "/api/v1" + path, json=value, headers=request_headers)
        require(reply.status_code == expected, "Unexpected API status for " + method + " " + path)
        require(reply.headers.get("cache-control") == "no-store", "Sensitive API response lacks no-store.")
        return reply

    def login(self, who, email, password):
        reply = self.request("POST", "/auth/login", value={"email": email, "password": password})
        cookie = reply.cookies.get("urumi_session")
        csrf = reply.json()["csrf_token"]
        require(cookie and "Secure" in reply.headers["set-cookie"] and "HttpOnly" in reply.headers["set-cookie"], "Secure session cookie flags missing.")
        self.sessions[who] = (cookie, csrf)
        self.protected.extend([cookie, csrf, password])
        return UUID(reply.json()["user"]["id"])

    def health(self, path, expected):
        if self.app_forward.process and self.app_forward.process.poll() is not None:
            self.app_forward.start()
        return self.http.get("/health/" + path).status_code == expected

    def run(self):
        self.save()
        owned_namespace(NS); owned_namespace(SNS)
        baseline = json.loads((ROOT / ".tools/m45/retained-before.json").read_text(encoding="utf-8-sig"))
        self.retained = identities(baseline)
        self.pvc_uid = document("-n", NS, "get", "pvc", PVC)["metadata"]["uid"]
        self.db_forward.start(); self.app_forward.start()
        wait_until(lambda: self.health("ready", 200), "Harness never became ready.")
        with self.db.transaction() as c:
            require(c.execute("SELECT count(*) AS n FROM users").fetchone()["n"] == 0, "Fresh bootstrap requires root-coordinated cleared disposable test accounts.")
        self.identity_fixture()
        self.registry_fixture()
        self.secret_rbac()
        self.durability()
        self.backup()
        self.resources_and_redaction()
        require(identities(document("-n", "urumi", "get", "deployments,statefulsets,services,pvc")) == self.retained,
                "Retained store resource/PVC identities changed.")
        self.passed("original-store-resources-and-pvc-identities-preserved")
        if self.cleanup:
            self.app_forward.close(); self.db_forward.close(); self.db.close()
            for namespace in (SNS, NS):
                owned_namespace(namespace)
                kube("delete", "namespace", namespace, "--wait=true", "--timeout=120s")
                require(not kube("get", "namespace", namespace, "--ignore-not-found", "-o", "name").strip(), "Owned namespace cleanup incomplete.")
            self.passed("owned-disposable-namespaces-cleaned")
        self.results["status"] = "PASS_RUNTIME_REVIEW_PENDING"
        self.save()

    def identity_fixture(self):
        admin_email = "accept-admin-" + uuid4().hex[:8] + "@example.test"
        admin_password = secrets.token_urlsafe(24)
        self.protected.append(admin_password)
        bootstrap_name = "m5-accept-bootstrap"
        apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": bootstrap_name, "namespace": NS},
               "stringData": {"email": admin_email, "password": admin_password}})
        operator = importlib.import_module("scripts.m5.operator")
        operator.bootstrap(self.db, bootstrap_name, NS, KCFG, "k3d-urumi")
        require(not kube("-n", NS, "get", "secret", bootstrap_name, "--ignore-not-found", "-o", "name").strip(), "Original bootstrap Secret was not deleted.")
        self.admin_id = self.login("admin", admin_email, admin_password)
        member_email = "accept-member-" + uuid4().hex[:8] + "@example.test"
        invite = self.request("POST", "/invitations", 201, "admin", {"email": member_email, "role": "member"}).json()
        token = invite["invite_url"].split("#token=", 1)[1]
        self.protected.append(token)
        password = secrets.token_urlsafe(24)
        self.request("POST", "/invitations/redeem", 201, value={"token": token, "password": password})
        self.request("POST", "/invitations/redeem", 409, value={"token": token, "password": password})
        self.member_id = self.login("member", member_email, password)
        self.login("revoked-session", member_email, password)
        self.revoked_cookie = self.sessions["revoked-session"][0]
        self.request("POST", "/auth/logout", 204, "revoked-session")
        self.request("GET", "/auth/me", 401, "revoked-session")
        self.request("GET", "/members", 403, "member")
        self.request("GET", f"/members/{self.admin_id}/keys", 404, "member")
        self.request("POST", "/invitations", 403, "member", {"email": "denied@example.test", "role": "member"})
        self.request("POST", f"/members/{self.member_id}/keys", 403, "member", {"label": "denied-csrf"}, {"X-CSRF-Token": "wrong"})
        self.active_key = self.request("POST", f"/members/{self.member_id}/keys", 201, "member", {"label": "active acceptance fixture"}).json()
        self.revoked_key = self.request("POST", f"/members/{self.member_id}/keys", 201, "admin", {"label": "revoked acceptance fixture"}).json()
        self.protected.extend([self.active_key["raw_key"], self.revoked_key["raw_key"]])
        self.request("DELETE", f"/members/{self.member_id}/keys/{self.revoked_key['id']}", 204, "admin")
        self.request("DELETE", f"/members/{self.member_id}/keys/{self.revoked_key['id']}", 204, "admin")
        self.passed("real-operator-bootstrap-secret-invitation-sessions-role-csrf-and-keys")

    def registry_fixture(self):
        self.credential = secrets.token_urlsafe(32)
        self.protected.append(self.credential)
        self.server = self.request("POST", "/servers", 201, "admin", {"name": "Acceptance synthetic upstream", "slug": "acceptance-fixture", "url": "https://learn.microsoft.com/api/mcp", "credential": {"type": "bearer", "value": self.credential}}).json()
        require(self.server["status"] == "Unreachable", "Untested server incorrectly Connected.")
        member = self.request("GET", "/servers/" + self.server["id"], who="member").json()
        require(not ({"url", "auth_type", "header_name", "secret_name"} & set(member)), "Member registry response exposes sensitive metadata.")
        self.request("POST", "/servers", 403, "member", {"name": "Denied", "slug": "denied", "url": "https://learn.microsoft.com/api/mcp"})
        self.request("POST", "/servers", 422, "admin", {"name": "Invalid", "slug": "invalid", "url": "http://169.254.169.254/"})
        changed = self.request("PATCH", "/servers/" + self.server["id"], who="admin", value={"enabled": False}).json()
        require(changed["status"] == "Disabled", "Disable did not win.")
        self.request("PATCH", "/servers/" + self.server["id"], who="admin", value={"enabled": True})
        with self.db.transaction() as c:
            row = c.execute("SELECT secret_name FROM servers WHERE id=%s", (UUID(self.server["id"]),)).fetchone()
            self.secret_reference = row["secret_name"]
            self.audit_ids = [uuid4(), uuid4()]
            for audit_id, user_id, outcome in ((self.audit_ids[0], self.admin_id, "success"), (self.audit_ids[1], self.member_id, "running")):
                c.execute("INSERT INTO audit_records(audit_id,request_id,user_id,auth_source,server_id,public_tool_name,run_id,outcome,finished_at) VALUES(%s,%s,%s,'session',%s,'acceptance__synthetic',%s,%s,CASE WHEN %s='running' THEN NULL ELSE now() END)", (audit_id, uuid4(), user_id, UUID(self.server["id"]), uuid4(), outcome, outcome))
        self.passed("real-registry-secret-backed-registration-disable-role-and-url-checks", synthetic_audit_rows=2)

    def secret_rbac(self):
        foreign_name = "urumi-upstream-" + str(uuid4())
        apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": foreign_name, "namespace": SNS,
            "labels": {"urumi-module": "m5", "urumi-owner": "synthetic-other-owner", "urumi-server": str(uuid4())}},
            "stringData": {"value": secrets.token_urlsafe(24)}})
        apply({"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "m5-rbac-foreign-fixture", "namespace": NS},
               "stringData": {"value": secrets.token_urlsafe(24)}})
        foreign_uid = document("-n", SNS, "get", "secret", foreign_name)["metadata"]["uid"]
        program = '''
import json,os,secrets
from uuid import uuid4
import psycopg
from backend.db.database import Database
from backend.registry.secret_store import SecretStore
from backend.errors import PlatformError
try:
 db=Database(psycopg.conninfo.make_conninfo(host=os.environ['PGHOST'],user=os.environ['PGUSER'],dbname=os.environ['PGDATABASE'],password=os.environ['PGPASSWORD']))
 with db.transaction() as c: owner=c.execute('SELECT id FROM installation').fetchone()['id']
 store=SecretStore(os.environ['M5_SECRET_NAMESPACE'],owner)
 sid=uuid4(); name='urumi-upstream-'+str(uuid4()); value=secrets.token_urlsafe(24)
 store.create(name,sid,value); assert store.resolve(name,sid)==value
 store.update_owned(name,sid); document=store.get(name,sid)
 assert document['immutable'] is True and document['metadata']['annotations']['urumi-reconciled']=='true'
 wrong=store.client.request('DELETE',store._path(name),json={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':str(uuid4())}})
 assert wrong.status_code==409 and store.resolve(name,sid)==value
 store.delete(name,sid); assert store.get(name,sid) is None
 foreign=FOREIGN_NAME
 for action in (lambda:store.get(foreign,sid),lambda:store.delete(foreign,sid),lambda:store.update_owned(foreign,sid),lambda:store.create(foreign,sid,value)):
  try: action()
  except PlatformError: pass
  else: raise AssertionError('Foreign object mutation accepted.')
 checks={}
 for label,path in [('list',store._path()),('watch',store._path()+'?watch=true&timeoutSeconds=1'),('foreign-namespace','/api/v1/namespaces/urumi-m5-check/secrets/m5-rbac-foreign-fixture'),('workloads','/apis/apps/v1/namespaces/urumi-m5-check/deployments')]:
  response=store.client.get(path); assert response.status_code==403; checks[label]=403
 store.close(); db.close()
 print(json.dumps({'status':'PASS','owned_secret_crud':True,'immutable_metadata_put':True,'wrong_uid_conflict':409,'foreign_ownership_rejected':True,'actual_serviceaccount_denials':checks}))
except Exception as error:
 print(json.dumps({'status':'FAIL','error_category':type(error).__name__}))
 raise SystemExit(1)
'''.replace("FOREIGN_NAME", repr(foreign_name))
        result = json.loads(kube("-n", NS, "exec", "-i", pod("backend")["metadata"]["name"], "--", "python", "-", payload=program))
        require(result["status"] == "PASS", "Actual ServiceAccount Secret checks failed.")
        require(document("-n", SNS, "get", "secret", foreign_name)["metadata"]["uid"] == foreign_uid, "Foreign synthetic Secret was changed.")
        self.passed("actual-serviceaccount-secret-crud-uid-ownership-and-rbac", evidence=result)

    def state(self):
        with self.db.transaction() as c:
            return {table: c.execute("SELECT count(*) AS n FROM " + table).fetchone()["n"] for table in
                    ("users", "invitations", "sessions", "api_keys", "servers", "audit_records")}

    def private_rows(self):
        # Includes password/token hashes and complete registry fields in memory only.
        with self.db.transaction() as c:
            return {table: c.execute("SELECT * FROM " + table + " ORDER BY id").fetchall() for table in
                    ("users", "invitations", "sessions", "api_keys", "servers")}

    def verify_saved(self):
        require(document("-n", NS, "get", "pvc", PVC)["metadata"]["uid"] == self.pvc_uid, "Platform PVC was replaced.")
        require(self.state() == self.saved_counts, "Durable fixture row counts changed.")
        require(self.private_rows() == self.saved_rows, "Private full identity or registry rows changed across restart.")
        require(self.request("GET", "/auth/me", who="admin").json()["user"]["id"] == str(self.admin_id), "Admin session lost.")
        self.request("GET", "/auth/me", who="member")
        self.request("GET", "/auth/me", 401, "revoked-session")
        keys = self.request("GET", f"/members/{self.member_id}/keys", who="member").json()["items"]
        require(len(keys) == 2 and all("raw_key" not in k for k in keys), "Durable key summaries invalid.")
        require(next(k for k in keys if k["id"] == self.revoked_key["id"])["revoked_at"] is not None, "Key revocation lost.")
        with self.db.transaction() as c:
            require(c.execute("SELECT secret_name FROM servers WHERE id=%s", (UUID(self.server["id"]),)).fetchone()["secret_name"] == self.secret_reference, "Registry credential reference lost.")
        resolve_program = '''
import json,os,psycopg
from uuid import UUID
from backend.registry.secret_store import SecretStore
try:
 with psycopg.connect(host=os.environ['PGHOST'],user=os.environ['PGUSER'],dbname=os.environ['PGDATABASE'],password=os.environ['PGPASSWORD']) as c:
  owner=c.execute('SELECT id FROM installation').fetchone()[0]
 store=SecretStore(os.environ['M5_SECRET_NAMESPACE'],owner)
 assert store.resolve(REFERENCE,UUID(SERVER_ID))==EXPECTED
 store.close(); print(json.dumps({'status':'PASS','durable_credential_resolved_and_matched':True}))
except Exception as error:
 print(json.dumps({'status':'FAIL','error_category':type(error).__name__})); raise SystemExit(1)
'''.replace("REFERENCE", repr(self.secret_reference)).replace("SERVER_ID", repr(self.server["id"])).replace("EXPECTED", repr(self.credential))
        resolved = json.loads(kube("-n", NS, "exec", "-i", pod("backend")["metadata"]["name"], "--", "python", "-", payload=resolve_program))
        require(resolved["status"] == "PASS", "Persisted credential could not be resolved by actual ServiceAccount.")
        own = self.request("GET", "/audit", who="member").json()["items"]
        require(own and all(item["user_id"] == str(self.member_id) for item in own), "Member audit ownership failed.")
        require(any(item["audit_id"] == str(self.audit_ids[1]) and item["outcome"] == "unknown" for item in own), "Abandoned synthetic attempt was not recovered unknown.")
        admin_audits = self.request("GET", "/audit", who="admin").json()["items"]
        require(set(map(str, self.audit_ids)) <= {item["audit_id"] for item in admin_audits}, "Admin cannot see both synthetic users' audits.")
        self.request("GET", "/audit?user_id=" + str(self.admin_id), 403, "member")

    def durability(self):
        self.saved_counts = self.state()
        self.saved_rows = self.private_rows()
        self.scan_logs("before-database-outage")
        original = pod("backend")
        original_db_uid = pod("platform-db")["metadata"]["uid"]
        original_uid = original["metadata"]["uid"]
        restarts = original["status"]["containerStatuses"][0]["restartCount"]
        kube("-n", NS, "scale", "deployment/" + DB_DEPLOY, "--replicas=0")
        wait_until(lambda: not document("-n", NS, "get", "pods", "-l", "app.kubernetes.io/component=platform-db")["items"], "Database did not stop.")
        wait_until(lambda: self.health("ready", 503), "Readiness did not reflect database loss.", 30)
        for _ in range(3):
            require(self.health("live", 200), "Database loss failed process liveness.")
            current = pod("backend")
            require(current["metadata"]["uid"] == original_uid and current["status"]["containerStatuses"][0]["restartCount"] == restarts,
                    "Database-down restart storm observed.")
            time.sleep(5)
        self.passed("actual-database-outage-live-ready-fencing-without-restart-storm", observed_seconds=15)
        self.db_forward.close()
        kube("-n", NS, "scale", "deployment/" + DB_DEPLOY, "--replicas=1")
        kube("-n", NS, "rollout", "status", "deployment/" + DB_DEPLOY, "--timeout=150s")
        wait_until(lambda: pod("backend")["status"]["containerStatuses"][0]["restartCount"] > restarts,
                   "Ownership supervisor did not restart after database recovery.")
        wait_until(lambda: any(c.get("type") == "Ready" and c.get("status") == "True" for c in pod("backend")["status"].get("conditions", [])),
                   "Restarted harness Pod never became Ready.")
        self.app_forward.start()
        wait_until(lambda: self.health("ready", 200), "Harness did not recover ownership.")
        self.scan_logs("supervisor-previous", previous=True)
        self.scan_logs("supervisor-recovered")
        self.db_forward.start()
        recovered = pod("backend")
        recovered_db_uid = pod("platform-db")["metadata"]["uid"]
        require(recovered_db_uid != original_db_uid, "Database Pod identity did not change.")
        require(recovered["metadata"]["uid"] == original_uid, "Supervisor evidence must belong to the same harness Pod.")
        self.verify_saved()
        self.passed("database-pod-replacement-supervisor-recovery-and-pvc-durability", durable_counts=dict(self.saved_counts),
                    private_full_identity_registry_rows_unchanged=True, actual_credential_resolved_and_matched=True,
                    pvc_uid=self.pvc_uid, database_pod_before_uid=original_db_uid, database_pod_after_uid=recovered_db_uid,
                    harness_pod_uid=original_uid, supervisor_restart_before=restarts,
                    supervisor_restart_after=recovered["status"]["containerStatuses"][0]["restartCount"])
        self.scan_logs("before-exclusive-validator-scale-down")
        # Test the real validator under an exclusive lifecycle owner, never a fake owner bypass.
        kube("-n", NS, "scale", "deployment/" + APP_DEPLOY, "--replicas=0")
        wait_until(lambda: not document("-n", NS, "get", "pods", "-l", "app.kubernetes.io/component=backend")["items"], "Harness did not stop.")
        self.db.acquire_owner()
        identity = Identity(self.db); keys = ApiKeys(self.db, identity)
        require(keys.validate(self.active_key["raw_key"]).user_id == self.member_id, "Active key failed real validator.")
        try:
            keys.validate(self.revoked_key["raw_key"])
        except PlatformError as error:
            require(error.code == "KEY_REVOKED", "Revoked key produced wrong failure.")
        else:
            raise CheckFailed("Revoked key passed validator.")
        require(identity.revalidate(identity.session(self.sessions["member"][0])).user_id == self.member_id, "Active session failed fresh validator.")
        try:
            identity.session(self.revoked_cookie)
        except PlatformError as error:
            require(error.status == 401, "Revoked session failed incorrectly.")
        else:
            raise CheckFailed("Revoked session remained usable.")
        # Create one artificial attempt through the actual audit module; no upstream call is made.
        audit = Audit(self.db, identity)
        audit_id = audit.begin_attempt(uuid4(), identity.session(self.sessions["member"][0]), UUID(self.server["id"]), "acceptance__synthetic")
        audit.finalize_attempt(audit_id, "success", 1)
        self.saved_counts["audit_records"] += 1
        self.db.close()
        kube("-n", NS, "scale", "deployment/" + APP_DEPLOY, "--replicas=1")
        kube("-n", NS, "rollout", "status", "deployment/" + APP_DEPLOY, "--timeout=150s")
        self.app_forward.start()
        wait_until(lambda: self.health("ready", 200), "Harness replacement did not recover.")
        self.scan_logs("before-harness-pod-delete")
        before_delete = pod("backend")["metadata"]["uid"]
        kube("-n", NS, "delete", "pod", pod("backend")["metadata"]["name"], "--wait=true", "--timeout=90s")
        kube("-n", NS, "rollout", "status", "deployment/" + APP_DEPLOY, "--timeout=150s")
        require(pod("backend")["metadata"]["uid"] != before_delete, "Harness Pod did not change UID.")
        self.app_forward.start()
        wait_until(lambda: self.health("ready", 200), "Deleted harness Pod did not recover.")
        self.verify_saved()
        self.passed("actual-harness-pod-replacement-active-revoked-identities-registry-and-audits",
                    private_full_identity_registry_rows_unchanged=True, actual_credential_resolved_and_matched=True,
                    pvc_uid=self.pvc_uid, harness_before_delete_uid=before_delete,
                    harness_after_delete_uid=pod("backend")["metadata"]["uid"],
                    harness_restart_after_delete=pod("backend")["status"]["containerStatuses"][0]["restartCount"])

    def backup(self):
        db_pod = pod("platform-db")["metadata"]["name"]
        dump_path = PRIVATE / "acceptance-backup.sql"
        command = ["kubectl", "--kubeconfig", KCFG, "--context", "k3d-urumi", "-n", NS, "exec", db_pod, "--", "pg_dump", "-U", "urumi", "-d", "urumi", "--no-owner", "--no-acl"]
        with dump_path.open("wb") as dump:
            result = subprocess.run(command, stdout=dump, stderr=subprocess.PIPE, timeout=90)
        require(result.returncode == 0 and dump_path.stat().st_size > 0, "Private database backup failed.")
        restore_name = "m5_accept_restore_" + uuid4().hex[:10]
        kube("-n", NS, "exec", db_pod, "--", "createdb", "-U", "urumi", restore_name)
        try:
            kube("-n", NS, "exec", "-i", db_pod, "--", "psql", "-U", "urumi", "-d", restore_name, "-v", "ON_ERROR_STOP=1", payload=dump_path.read_bytes(), binary=True)
            table_sql = "SELECT json_build_object(" + ",".join("'" + table + "',(SELECT count(*) FROM " + table + ")" for table in self.saved_counts) + ")"
            actual = json.loads(kube("-n", NS, "exec", db_pod, "--", "psql", "-U", "urumi", "-d", restore_name, "-tAc", table_sql))
            require(actual == self.saved_counts, "Separate restored database table counts differ.")
            flag_sql = "SELECT json_build_object('revoked_sessions',(SELECT count(*) FROM sessions WHERE revoked_at IS NOT NULL),'revoked_keys',(SELECT count(*) FROM api_keys WHERE revoked_at IS NOT NULL))"
            restored_flags = json.loads(kube("-n", NS, "exec", db_pod, "--", "psql", "-U", "urumi", "-d", restore_name, "-tAc", flag_sql))
            with self.db.transaction() as c:
                primary_flags = c.execute(flag_sql).fetchone()["json_build_object"]
            require(restored_flags == primary_flags, "Restored revocation counts differ.")
            self.passed("actual-private-pg-dump-separate-database-restore", restored_counts=actual, restored_revocations=restored_flags, raw_dump_saved_only_in_ignored_tools=True)
        finally:
            kube("-n", NS, "exec", db_pod, "--", "dropdb", "-U", "urumi", restore_name)

    def scan_logs(self, label, previous=False):
        command = ["-n", NS, "logs", "deployment/" + APP_DEPLOY, "--all-containers=true"]
        if previous:
            command.append("--previous")
        logs = kube(*command)
        require(not any(value in logs for value in self.protected), "Sensitive value appeared in harness logs; raw logs not saved.")
        (EVIDENCE / ("cluster-harness-logs-" + label + ".txt")).write_text(logs, encoding="utf-8")

    def resources_and_redaction(self):
        resources = document("-n", NS, "get", "deployments,services,ingresses,pvc")
        for item in resources["items"]:
            if item["kind"] == "Ingress":
                raise CheckFailed("M5 harness has public Ingress.")
            if item["kind"] == "Service":
                require(item["spec"]["type"] == "ClusterIP", "M5 service has public exposure.")
            if item["kind"] == "Deployment":
                for container in item["spec"]["template"]["spec"]["containers"]:
                    require(all(container.get(key) for key in ("readinessProbe", "livenessProbe", "resources")), "Probe/resource settings missing.")
                    require(all(container["resources"].get(key) for key in ("requests", "limits")), "Resource requests or limits missing.")
        self.scan_logs("final")
        files = [path for path in EVIDENCE.iterdir() if path.is_file()]
        require(not any(value in path.read_text(encoding="utf-8-sig", errors="replace") for path in files for value in self.protected),
                "Sensitive fixture value appeared in saved evidence.")
        self.passed("saved-evidence-actual-credential-session-key-redaction", scanned_files=len(files), matches=0)
        (EVIDENCE / "cluster-resource-settings.json").write_text(json.dumps({"service_types": [r["spec"]["type"] for r in resources["items"] if r["kind"] == "Service"], "ingress_count": 0, "probes_and_resources_present": True, "pvc_uid_retained": True}, indent=2) + "\n")
        self.passed("actual-probes-resources-internal-exposure-and-secret-free-logs")

    def close(self):
        self.http.close(); self.app_forward.close(); self.db_forward.close(); self.db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cleanup", action="store_true", help="Delete only both verified M5-owned disposable namespaces after all checks pass.")
    args = parser.parse_args()
    runner = Runner(args.cleanup)
    try:
        runner.run()
    except Exception as error:
        runner.results.update(status="FAIL", error_category=type(error).__name__, safe_message=str(error) if isinstance(error, CheckFailed) else "Live check failed; sensitive dependency output suppressed.")
        runner.save()
        print("FAIL:", type(error).__name__, flush=True)
        raise SystemExit(1) from None
    finally:
        runner.close()
