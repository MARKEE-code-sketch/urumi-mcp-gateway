import type {
  Session,
  Page,
  Server,
  Tool,
  User,
  Key,
  Audit,
  ChatReply,
} from "./types";
export const NORMAL_TIMEOUT = 15000,
  CHAT_TIMEOUT = 130000,
  BODY_CAP = 16384,
  RESPONSE_CAP = 1048576;
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function id(value: string) {
  if (!uuid.test(value)) throw new ApiError("Invalid identifier.");
  return value;
}
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
    public requestId = "",
    public uncertain = false,
  ) {
    super(message);
  }
}
export function chatMessage(value: string) {
  const result = value.trim();
  if (
    !result ||
    [...result].length > 4000 ||
    new TextEncoder().encode(result).length > 12288
  )
    throw new ApiError("Enter 1-4,000 characters, at most 12,288 UTF-8 bytes.");
  return result;
}
export function schemaText(value: unknown) {
  let count = 0;
  function walk(v: unknown, depth: number) {
    if (++count > 2000 || depth > 32)
      throw new ApiError("Schema display limit exceeded. Try a smaller page.");
    if (v && typeof v === "object")
      for (const item of Object.values(v)) walk(item, depth + 1);
  }
  walk(value, 0);
  return JSON.stringify(value, null, 2);
}
function object(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}
export class Api {
  private controllers = new Set<AbortController>();
  // Aborting alone is insufficient: an old response may already be complete.
  private generation = 0;
  constructor(
    private csrf: () => string,
    private expired: () => void,
  ) {}
  abort() {
    this.generation++;
    for (const c of this.controllers) c.abort();
    this.controllers.clear();
  }
  async request<T>(
    route: string,
    method = "GET",
    body?: unknown,
    publicCall = false,
  ): Promise<T> {
    if (
      !/^\/(auth\/(me|login|logout)|invitations(\/redeem)?|members(\/[a-f0-9-]{36}\/keys(\/[a-f0-9-]{36})?)?|servers(\/[a-f0-9-]{36}(\/tools)?)?|audit|chat)(\?[a-z0-9_=&%-]*)?$/i.test(
        route,
      )
    )
      throw new ApiError("Unsupported API route.");
    const encoded = body === undefined ? undefined : JSON.stringify(body);
    if (encoded && new TextEncoder().encode(encoded).length > BODY_CAP)
      throw new ApiError("Request is too large.");
    const generation = this.generation;
    const change = method !== "GET",
      c = new AbortController();
    this.controllers.add(c);
    let timedOut = false;
    const timer = setTimeout(
      () => {
        timedOut = true;
        c.abort();
      },
      route === "/chat" ? CHAT_TIMEOUT : NORMAL_TIMEOUT,
    );
    try {
      const headers: Record<string, string> = { Accept: "application/json" };
      if (encoded) headers["Content-Type"] = "application/json";
      if (change && !publicCall) headers["X-CSRF-Token"] = this.csrf();
      const response = await fetch("/api/v1" + route, {
        method,
        body: encoded,
        headers,
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        signal: c.signal,
      });
      if (generation !== this.generation)
        throw new ApiError("This view is no longer active.");
      if (response.status === 401 && !publicCall) this.expired();
      if (response.status === 204) return undefined as T;
      if (Number(response.headers.get("Content-Length")) > RESPONSE_CAP)
        throw new ApiError(
          "Response exceeds the display limit. Try a smaller page.",
          response.status,
          "",
          change,
        );
      if (!response.headers.get("Content-Type")?.includes("application/json"))
        throw new ApiError(
          [502, 503, 504].includes(response.status)
            ? "The gateway is temporarily unavailable. Please try again shortly."
            : "Unexpected response format.",
          response.status,
          "",
          change,
        );
      const reader = response.body?.getReader();
      if (!reader)
        throw new ApiError("Response was empty.", response.status, "", change);
      let length = 0;
      const chunks: Uint8Array[] = [];
      try {
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          length += value.length;
          if (length > RESPONSE_CAP) {
            await reader.cancel();
            throw new ApiError(
              "Response exceeds the display limit. Try a smaller page.",
              response.status,
              "",
              change,
            );
          }
          chunks.push(value);
        }
      } finally {
        reader.releaseLock();
      }
      const bytes = new Uint8Array(length);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.length;
      }
      let data: unknown;
      try {
        data = JSON.parse(
          new TextDecoder("utf-8", { fatal: true }).decode(bytes),
        );
      } catch {
        throw new ApiError(
          "Unexpected response format.",
          response.status,
          "",
          change,
        );
      }
      if (!response.ok) {
        const error = object(data) && object(data.error) ? data.error : {};
        throw new ApiError(
          typeof error.message === "string"
            ? error.message.slice(0, 500)
            : "The request could not be completed.",
          response.status,
          typeof error.request_id === "string"
            ? error.request_id.slice(0, 100)
            : "",
        );
      }
      if (!object(data))
        throw new ApiError(
          "Unexpected response shape.",
          response.status,
          "",
          change,
        );
      if (
        method === "GET" &&
        (route.startsWith("/servers?") ||
          route.includes("/tools?") ||
          route.startsWith("/members?") ||
          route.includes("/keys?") ||
          route.startsWith("/audit?")) &&
        (!Array.isArray(data.items) ||
          data.items.length > 50 ||
          typeof data.has_more !== "boolean" ||
          typeof data.page !== "number" ||
          typeof data.per_page !== "number")
      )
        throw new ApiError("Unexpected list response.");
      if (
        route.startsWith("/auth/") &&
        (!object(data.user) || typeof data.csrf_token !== "string")
      )
        throw new ApiError("Unexpected session response.");
      if (
        route === "/chat" &&
        (!Array.isArray(data.tool_calls) ||
          data.tool_calls.length > 12 ||
          typeof data.answer !== "string" ||
          !["completed", "failed", "limit_reached"].includes(
            String(data.state),
          ))
      )
        throw new ApiError("Unexpected chat response.", 200, "", true);
      if (generation !== this.generation)
        throw new ApiError("This view is no longer active.");
      const fail = () => {
        throw new ApiError(
          "Unexpected response shape.",
          response.status,
          "",
          change,
        );
      };
      const text = (v: unknown) => typeof v === "string";
      const validId = (v: unknown) => typeof v === "string" && uuid.test(v);
      const date = (v: unknown) =>
        typeof v === "string" && Number.isFinite(Date.parse(v));
      const user = (v: unknown) =>
        object(v) &&
        validId(v.id) &&
        text(v.email) &&
        ["admin", "member"].includes(String(v.role)) &&
        date(v.created_at);
      if (
        route.startsWith("/auth/") &&
        (!user(data.user) || !text(data.csrf_token))
      )
        fail();
      if (Array.isArray(data.items))
        for (const item of data.items) {
          if (!object(item)) fail();
          const v = item as Record<string, unknown>;
          if (
            route.startsWith("/members") &&
            !route.includes("/keys") &&
            !user(v)
          )
            fail();
          if (
            route.includes("/keys") &&
            (!validId(v.id) ||
              !validId(v.user_id) ||
              !text(v.label) ||
              !text(v.prefix) ||
              !date(v.created_at) ||
              (v.revoked_at !== null && !date(v.revoked_at)))
          )
            fail();
          if (
            route.startsWith("/servers") &&
            !route.includes("/tools") &&
            (!validId(v.id) ||
              !text(v.name) ||
              !text(v.slug) ||
              typeof v.enabled !== "boolean" ||
              !["Connected", "Unreachable", "Disabled"].includes(
                String(v.status),
              ) ||
              (v.last_checked_at !== null && !date(v.last_checked_at)))
          )
            fail();
          if (
            route.includes("/tools") &&
            (!text(v.gateway_name) ||
              !text(v.upstream_name) ||
              !text(v.description) ||
              !("inputSchema" in v))
          )
            fail();
          if (
            route.startsWith("/audit") &&
            (!validId(v.audit_id) ||
              !validId(v.request_id) ||
              !text(v.public_tool_name) ||
              !date(v.started_at) ||
              (v.finished_at !== null && !date(v.finished_at)) ||
              ![
                "running",
                "success",
                "error",
                "timeout",
                "denied",
                "unknown",
              ].includes(String(v.outcome)))
          )
            fail();
        }
      const optionalText = (v: unknown) =>
        v === null || v === undefined || typeof v === "string";
      const optionalNumber = (v: unknown) =>
        v === null ||
        v === undefined ||
        (typeof v === "number" && Number.isFinite(v));
      if (
        route.startsWith("/servers") &&
        Array.isArray(data.items) &&
        !route.includes("/tools")
      ) {
        for (const v of data.items)
          for (const field of [
            "status_reason",
            "auth_type",
            "header_name",
            "url",
          ])
            if (!optionalText(v[field])) fail();
      }
      if (
        route === "/invitations" &&
        (!text(data.invite_url) || !date(data.expires_at))
      )
        fail();
      if (route === "/invitations/redeem" && !user(data.user)) fail();
      if (
        method === "POST" &&
        route.includes("/keys") &&
        (!text(data.raw_key) ||
          !validId(data.id) ||
          !validId(data.user_id) ||
          !text(data.label) ||
          !text(data.prefix) ||
          !date(data.created_at))
      )
        fail();
      if (route === "/chat" && !text(data.request_id)) fail();
      if (route.startsWith("/audit") && Array.isArray(data.items))
        for (const v of data.items) {
          for (const k of [
            "user_id",
            "key_id",
            "auth_source",
            "server_id",
            "upstream_tool_name",
            "error_code",
            "error_summary",
          ])
            if (!optionalText(v[k])) fail();
          if (!optionalNumber(v.duration_ms)) fail();
        }
      if (route === "/chat")
        for (const v of data.tool_calls as unknown[]) {
          if (
            !object(v) ||
            !text(v.call_id) ||
            !text(v.tool_name) ||
            !["success", "error", "timeout", "denied", "unknown"].includes(
              String(v.outcome),
            ) ||
            !optionalText(v.server_id) ||
            !optionalText(v.audit_id) ||
            !optionalText(v.error_code) ||
            !optionalText(v.result_summary) ||
            !optionalNumber(v.duration_ms)
          )
            fail();
        }
      return data as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(
        timedOut ? "The response timed out." : "The response was lost.",
        0,
        "",
        change,
      );
    } finally {
      c.abort();
      clearTimeout(timer);
      this.controllers.delete(c);
    }
  }
  me = () => this.request<Session>("/auth/me");
  login = (email: string, password: string) =>
    this.request<Session>("/auth/login", "POST", { email, password }, true);
  logout = () => this.request<void>("/auth/logout", "POST");
  redeem = (token: string, password: string) =>
    this.request<{ user: User }>(
      "/invitations/redeem",
      "POST",
      { token, password },
      true,
    );
  list = <T>(
    route: string,
    page = 1,
    perPage = 20,
    filters: Record<string, string> = {},
  ) =>
    this.request<Page<T>>(
      route +
        "?" +
        new URLSearchParams({
          page: String(page),
          per_page: String(perPage),
          ...filters,
        }),
    );
  servers = (page = 1, perPage = 20) =>
    this.list<Server>("/servers", page, perPage);
  server = (sid: string) => this.request<Server>("/servers/" + id(sid));
  tools = (sid: string, page = 1, perPage = 20) =>
    this.list<Tool>("/servers/" + id(sid) + "/tools", page, perPage);
  members = (page = 1) => this.list<User>("/members", page);
  keys = (owner: string, page = 1) =>
    this.list<Key>("/members/" + id(owner) + "/keys", page);
  audit = (page = 1, filters: Record<string, string> = {}) => {
    for (const k of ["user_id", "server_id"]) if (filters[k]) id(filters[k]);
    if (
      filters.outcome &&
      !["running", "success", "error", "timeout", "denied", "unknown"].includes(
        filters.outcome,
      )
    )
      throw new ApiError("Invalid outcome.");
    return this.list<Audit>("/audit", page, 20, filters);
  };
  chat = (message: string) =>
    this.request<ChatReply>("/chat", "POST", { message: chatMessage(message) });
}
