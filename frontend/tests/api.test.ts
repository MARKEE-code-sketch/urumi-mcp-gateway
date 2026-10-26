import { describe, it, expect, vi, afterEach } from "vitest";
import {
  Api,
  ApiError,
  chatMessage,
  schemaText,
  CHAT_TIMEOUT,
  NORMAL_TIMEOUT,
} from "../src/api";
const session = {
  user: {
    id: "11111111-1111-4111-8111-111111111111",
    email: "admin@example.test",
    role: "admin",
    created_at: "2026-10-18T00:00:00Z",
  },
  csrf_token: "test",
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
describe("bounded browser API", () => {
  it("uses same origin, no redirect, cookie and CSRF without caller identity", async () => {
    const f = vi.fn().mockResolvedValue(
      response({
        request_id: "x",
        state: "completed",
        answer: "ok",
        tool_calls: [],
      }),
    );
    vi.stubGlobal("fetch", f);
    await new Api(
      () => "csrf",
      () => {},
    ).chat(" hi ");
    expect(f.mock.calls[0][0]).toBe("/api/v1/chat");
    expect(f.mock.calls[0][1]).toMatchObject({
      credentials: "same-origin",
      redirect: "error",
      cache: "no-store",
      body: '{"message":"hi"}',
      headers: { "X-CSRF-Token": "csrf" },
    });
  });
  it("does not attach authenticated CSRF to login", async () => {
    const f = vi.fn().mockResolvedValue(response(session));
    vi.stubGlobal("fetch", f);
    await new Api(
      () => "secret",
      () => {},
    ).login("a", "b");
    expect(f.mock.calls[0][1].headers).not.toHaveProperty("X-CSRF-Token");
  });
  it("rejects arbitrary destinations before fetch", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    await expect(
      new Api(
        () => "",
        () => {},
      ).request("https://evil.example"),
    ).rejects.toThrow("Unsupported");
    expect(f).not.toHaveBeenCalled();
  });
  it("rejects oversized UTF8 body before submission", async () => {
    const f = vi.fn();
    vi.stubGlobal("fetch", f);
    await expect(
      new Api(
        () => "",
        () => {},
      ).request("/servers", "POST", { name: "\u{1F600}".repeat(5000) }),
    ).rejects.toThrow("too large");
    expect(f).not.toHaveBeenCalled();
  });
  it("counts Unicode code points and UTF8 bytes independently", () => {
    expect(chatMessage("a".repeat(4000))).toHaveLength(4000);
    expect(() => chatMessage("a".repeat(4001))).toThrow();
    expect(() => chatMessage("\u{1F600}".repeat(3073))).toThrow();
    expect(chatMessage("\u{1F600}".repeat(3000))).toBeTruthy();
  });
  it("bounds recursive schema display", () => {
    let value: unknown = {};
    for (let i = 0; i < 34; i++) value = { child: value };
    expect(() => schemaText(value)).toThrow("limit");
    expect(() => schemaText(Array(2001).fill(1))).toThrow("limit");
  });
  it("rejects oversized responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("{}", {
          headers: {
            "Content-Type": "application/json",
            "Content-Length": "1048577",
          },
        }),
      ),
    );
    await expect(
      new Api(
        () => "",
        () => {},
      ).servers(),
    ).rejects.toThrow("display limit");
  });
  it("rejects malformed list items rather than crashing page", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          items: [{ id: "bad" }],
          page: 1,
          per_page: 20,
          has_more: false,
        }),
      ),
    );
    await expect(
      new Api(
        () => "",
        () => {},
      ).servers(),
    ).rejects.toThrow("shape");
  });
  it("accepts the gateway preview contract without an MCP name field", async () => {
    const tool = {
      gateway_name: "woocommerce__list_products",
      upstream_name: "list_products",
      description: "List products.",
      inputSchema: { type: "object", properties: {} },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      items: [tool], page: 1, per_page: 20, has_more: false, stale: false,
    })));
    const result = await new Api(() => "", () => {}).tools(
      "33333333-3333-4333-8333-333333333333",
    );
    expect(result.items).toEqual([tool]);
    expect(result.items[0]).not.toHaveProperty("name");
  });
  it.each([undefined, 123])("rejects malformed preview gateway_name %s", async (gatewayName) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      items: [{ name: "woocommerce__list_products", gateway_name: gatewayName,
        upstream_name: "list_products", description: "List products.", inputSchema: {} }],
      page: 1, per_page: 20, has_more: false,
    })));
    await expect(new Api(() => "", () => {}).tools(
      "33333333-3333-4333-8333-333333333333",
    )).rejects.toThrow("Unexpected response shape.");
  });
  it("ignores obsolete 401 from a previous session", async () => {
    let resolve!: (r: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise((r) => (resolve = r))),
    );
    const expired = vi.fn(),
      api = new Api(() => "", expired);
    const pending = api.me();
    api.abort();
    resolve(response({ error: { message: "Expired" } }, 401));
    await expect(pending).rejects.toThrow("no longer active");
    expect(expired).not.toHaveBeenCalled();
  });
  it("expires current protected session on 401", async () => {
    const expired = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(response({ error: { message: "Expired" } }, 401)),
    );
    await expect(new Api(() => "", expired).me()).rejects.toThrow();
    expect(expired).toHaveBeenCalledOnce();
  });
  it("preserves safe error requestID without retry", async () => {
    const f = vi
      .fn()
      .mockResolvedValue(
        response({ error: { message: "Denied", request_id: "abc" } }, 403),
      );
    vi.stubGlobal("fetch", f);
    try {
      await new Api(
        () => "",
        () => {},
      ).chat("x");
    } catch (e) {
      expect((e as ApiError).requestId).toBe("abc");
    }
    expect(f).toHaveBeenCalledOnce();
  });
  it.each(
    [502, 503, 504].flatMap((status) =>
      ["GET", "POST"].map((method) => ({ status, method })),
    ),
  )("explains non-JSON gateway $status for $method without retrying", async ({ status, method }) => {
    const proxyBody = "Private proxy diagnostic: no available server";
    const f = vi.fn().mockResolvedValue(new Response(proxyBody, {
      status,
      headers: { "Content-Type": status === 503 ? "text/plain" : "text/html" },
    }));
    vi.stubGlobal("fetch", f);
    const error = await new Api(() => "csrf", () => {}).request(
      "/servers", method, method === "POST" ? { name: "QA server" } : undefined,
    ).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      message: "The gateway is temporarily unavailable. Please try again shortly.",
      status,
      uncertain: method === "POST",
      requestId: "",
    });
    expect((error as ApiError).message).not.toContain(proxyBody);
    expect(f).toHaveBeenCalledOnce();
  });
  it.each([
    { status: 200, contentType: "text/plain", body: "Not JSON" },
    { status: 200, contentType: "application/json", body: "{broken" },
    { status: 500, contentType: "text/html", body: "<html>Unexpected failure</html>" },
  ])("keeps malformed $status $contentType responses as format errors", async ({ status, contentType, body }) => {
    const f = vi.fn().mockResolvedValue(new Response(body, {
      status,
      headers: { "Content-Type": contentType },
    }));
    vi.stubGlobal("fetch", f);
    await expect(new Api(() => "csrf", () => {}).request("/servers", "POST", {}))
      .rejects.toMatchObject({ message: "Unexpected response format.", status, uncertain: true });
    expect(f).toHaveBeenCalledOnce();
  });
  it("marks a lost write as possibly effective", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    await expect(
      new Api(
        () => "",
        () => {},
      ).chat("x"),
    ).rejects.toMatchObject({ uncertain: true });
  });
  it("uses separate approved total deadlines", () => {
    expect(NORMAL_TIMEOUT).toBe(15000);
    expect(CHAT_TIMEOUT).toBe(130000);
  });
  it("handles empty 204 without JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );
    await expect(
      new Api(
        () => "",
        () => {},
      ).logout(),
    ).resolves.toBeUndefined();
  });
  it("rejects malformed session fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(response({ user: { id: "x" }, csrf_token: "x" })),
    );
    await expect(
      new Api(
        () => "",
        () => {},
      ).me(),
    ).rejects.toThrow("shape");
  });
});

it("cancels response transfer on excessive declared length", async () => {
  const f = vi
    .fn()
    .mockResolvedValue(
      new Response("{}", {
        headers: {
          "Content-Type": "application/json",
          "Content-Length": "1048577",
        },
      }),
    );
  vi.stubGlobal("fetch", f);
  await expect(
    new Api(
      () => "",
      () => {},
    ).servers(),
  ).rejects.toThrow("display limit");
  expect(f.mock.calls[0][1].signal.aborted).toBe(true);
});
it("normal deadline aborts without any automatic retry", async () => {
  vi.useFakeTimers();
  const f = vi.fn(
    (_url, options) =>
      new Promise((_resolve, reject) =>
        options.signal.addEventListener("abort", () =>
          reject(new DOMException("aborted", "AbortError")),
        ),
      ),
  );
  vi.stubGlobal("fetch", f);
  const result = new Api(
    () => "",
    () => {},
  ).servers();
  const assertion = expect(result).rejects.toThrow("timed out");
  await vi.advanceTimersByTimeAsync(15000);
  await assertion;
  expect(f).toHaveBeenCalledOnce();
});

it("rejects a list response missing its required envelope", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ foo: 1 })));
  await expect(
    new Api(
      () => "",
      () => {},
    ).servers(),
  ).rejects.toThrow("list response");
});
it("rejects nontext nullable audit fields before rendering", async () => {
  const row = {
    audit_id: "aaaaaaaa-aaaa-4aaa-8aaa-000000000000",
    request_id: "11111111-1111-4111-8111-111111111111",
    public_tool_name: "demo",
    started_at: "2026-10-18T00:00:00Z",
    finished_at: null,
    outcome: "running",
    error_summary: { secret: "invalid" },
  };
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        response({ items: [row], page: 1, per_page: 20, has_more: false }),
      ),
  );
  await expect(
    new Api(
      () => "",
      () => {},
    ).audit(),
  ).rejects.toThrow("shape");
});
