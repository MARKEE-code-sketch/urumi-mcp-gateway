CREATE TABLE canceled_secret_names (
 name text PRIMARY KEY, server_id uuid NOT NULL, last_checked_at timestamptz NOT NULL DEFAULT now()
);
