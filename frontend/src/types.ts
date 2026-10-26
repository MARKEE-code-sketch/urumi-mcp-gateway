export type User = {
  id: string;
  email: string;
  role: "admin" | "member";
  created_at: string;
};
export type Session = { user: User; csrf_token: string };
export type Page<T> = {
  items: T[];
  page: number;
  per_page: number;
  has_more: boolean;
  stale?: boolean;
};
export type Server = {
  id: string;
  name: string;
  slug: string;
  enabled: boolean;
  status: "Connected" | "Unreachable" | "Disabled";
  last_checked_at: string | null;
  status_reason: string | null;
  created_at: string;
  updated_at: string;
  url?: string;
  auth_type?: string;
  header_name?: string | null;
};
export type Tool = {
  gateway_name: string;
  upstream_name: string;
  description: string;
  inputSchema: unknown;
};
export type Key = {
  id: string;
  user_id: string;
  label: string;
  prefix: string;
  created_at: string;
  revoked_at: string | null;
  raw_key?: string;
};
export type Audit = {
  audit_id: string;
  request_id: string;
  user_id: string | null;
  key_id: string | null;
  auth_source: string | null;
  server_id: string | null;
  public_tool_name: string;
  upstream_tool_name: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  outcome: string;
  error_code: string | null;
  error_summary: string | null;
};
export type Attempt = {
  call_id: string;
  tool_name: string;
  server_id: string | null;
  outcome: string;
  duration_ms: number | null;
  audit_id: string | null;
  error_code?: string;
  result_summary?: string;
};
export type ChatReply = {
  request_id: string;
  state: "completed" | "failed" | "limit_reached";
  answer: string;
  tool_calls: Attempt[];
};
