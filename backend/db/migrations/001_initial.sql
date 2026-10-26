CREATE TABLE installation(id uuid PRIMARY KEY);
CREATE TABLE users (
 id uuid PRIMARY KEY, email text NOT NULL UNIQUE, role text NOT NULL CHECK(role IN ('admin','member')),
 password_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE invitations (
 id uuid PRIMARY KEY, email text NOT NULL, token_hash text NOT NULL UNIQUE,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL, consumed_at timestamptz
);
CREATE INDEX invitations_email ON invitations(email);
CREATE TABLE sessions (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id), token_hash text NOT NULL UNIQUE,
 csrf_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 revoked_at timestamptz
);
CREATE TABLE api_keys (
 id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id), label text NOT NULL,
 prefix text NOT NULL, token_hash text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), revoked_at timestamptz
);
CREATE INDEX api_keys_order ON api_keys(user_id,created_at DESC,id DESC);
CREATE TABLE servers (
 id uuid PRIMARY KEY, name text NOT NULL, slug text NOT NULL UNIQUE, url text NOT NULL,
 enabled boolean NOT NULL, status text NOT NULL CHECK(status IN ('Connected','Unreachable','Disabled')),
 status_reason text, last_checked_at timestamptz, auth_type text NOT NULL CHECK(auth_type IN ('none','bearer','header')),
 header_name text, secret_name text, version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX servers_order ON servers(created_at DESC,id DESC);
CREATE TABLE secret_operations (
 id uuid PRIMARY KEY, server_id uuid NOT NULL, phase text NOT NULL CHECK(phase IN ('prepared','committed','remove')),
 staged_name text, old_name text, new_server boolean NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX secret_operations_server ON secret_operations(server_id);
CREATE TABLE audit_records (
 audit_id uuid PRIMARY KEY, request_id uuid NOT NULL, user_id uuid, key_id uuid,
 auth_source text CHECK(auth_source IN ('session','api_key')), server_id uuid,
 public_tool_name text NOT NULL, upstream_tool_name text, started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz, duration_ms bigint CHECK(duration_ms>=0),
 outcome text NOT NULL CHECK(outcome IN ('running','success','error','timeout','denied','unknown')),
 error_code text, error_summary text, run_id uuid NOT NULL,
 CHECK ((outcome='running')=(finished_at IS NULL))
);
CREATE INDEX audit_order ON audit_records(started_at DESC,audit_id DESC);
CREATE INDEX audit_owner ON audit_records(user_id,started_at DESC,audit_id DESC);
