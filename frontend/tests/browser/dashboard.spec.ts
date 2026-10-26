import { mkdirSync, writeFileSync } from "node:fs";
import { test, expect } from "@playwright/test";

type SafeRequest = {
  test: string;
  origin: string;
  path: string;
  method: string;
  status: number | null;
  csrf_present: boolean;
  authorization_present: boolean;
  body_fields: string[];
  fragment_cleared: boolean;
};
const observed: SafeRequest[] = [];
const evidence = process.env.M8_EVIDENCE_DIR ?? "../docs/evidence/m8";
mkdirSync(evidence, { recursive: true });
test.beforeEach(async ({ page }, testInfo) => {
  const mapping = new WeakMap<object, SafeRequest>();
  page.on("request", (request) => {
    const url = new URL(request.url());
    let fields: string[] = [];
    try {
      const body = request.postDataJSON();
      if (body && typeof body === "object") fields = Object.keys(body);
    } catch {}
    const row: SafeRequest = {
      test: testInfo.title,
      origin: url.origin,
      path: url.pathname,
      method: request.method(),
      status: null,
      csrf_present: !!request.headers()["x-csrf-token"],
      authorization_present: !!request.headers()["authorization"],
      body_fields: fields,
      fragment_cleared:
        !url.pathname.startsWith("/api/v1") || !new URL(page.url()).hash,
    };
    mapping.set(request, row);
    observed.push(row);
  });
  page.on("response", (response) => {
    const row = mapping.get(response.request());
    if (row) row.status = response.status();
  });
});
test.afterEach(async ({}, testInfo) => {
  writeFileSync(
    `${evidence}/network-summary.json`,
    JSON.stringify({ requests: observed }, null, 2),
  );
  const rows = observed.filter((r) => r.test === testInfo.title);
  expect(
    rows.every(
      (r) =>
        r.origin === "http://127.0.0.1:18080" &&
        !r.authorization_present &&
        r.fragment_cleared,
    ),
  ).toBe(true);
});
async function login(page: any, email = "admin@example.test") {
  await page.goto("/login");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Fixture-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Servers", exact: true }),
  ).toBeVisible();
}
test.beforeEach(async ({ request }) => {
  await request.post("/test/control", { data: { reset: true } });
});
test("admin status, hostile preview and server credential keep/replace/clear", async ({
  page,
}) => {
  await login(page);
  await expect(page.getByText("Not checked yet")).toBeVisible();
  await page
    .getByRole("button", { name: "View tools", exact: true })
    .first()
    .click();
  await expect(page.getByText(/onerror/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "woo__service_info", exact: true })).toBeVisible();
  await expect(page.getByText("Unexpected response shape.", { exact: true })).toHaveCount(0);
  await expect(page.locator('img[src^="https://evil.example"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Edit WooCommerce" }).click();
  await expect(page.getByLabel("Slug", { exact: true })).toHaveAttribute(
    "readonly",
    "",
  );
  await page.getByLabel("Name", { exact: true }).fill("Woo shop");
  await page.getByRole("button", { name: "Save server" }).click();
  await expect(
    page.getByRole("button", { name: "Edit Woo shop" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Edit Woo shop" }).click();
  await page.getByLabel("clear", { exact: true }).check();
  await page.getByRole("button", { name: "Save server" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
});
test("member direct access denied, redacted API and expiry clears private screen", async ({
  page,
  request,
}) => {
  await login(page, "member@example.test");
  await expect(
    page.getByRole("link", { name: "Members", exact: true }),
  ).toHaveCount(0);
  await page.goto("/members");
  await expect(
    page.getByRole("heading", { name: "Access denied" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Servers", exact: true }).click();
  const body = await page.evaluate(
    async () => await (await fetch("/api/v1/servers")).json(),
  );
  expect(body.items[0]).not.toHaveProperty("url");
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    "urumi_session",
  );
  await request.post("/test/control", { data: { expire: true } });
  await page.getByRole("button", { name: "Refresh servers" }).click();
  await expect(
    page.getByRole("heading", { name: "Login", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("WooCommerce", { exact: true })).toHaveCount(0);
});
test("invitation fragment removed and account creation does not auto-login", async ({
  page,
}) => {
  await page.goto("/invite#token=fixture-invitation-token-for-tests");
  await expect(page).toHaveURL(/\/invite$/);
  await page.getByLabel("New password").fill("Fixture-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(
    page.getByText("Account created.", { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Go to login" })).toBeVisible();
  await page.reload();
  await expect(page.getByText(/missing or malformed/)).toBeVisible();
});
test("members invitation once-only and explicit target key lifecycle", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Members", exact: true }).click();
  await page.getByLabel("Invite email").fill("new@example.test");
  await page.getByRole("button", { name: "Create invitation" }).click();
  await expect(page.getByLabel("Private invitation link value")).toBeVisible();
  await page.getByRole("button", { name: "Dismiss", exact: true }).click();
  await page
    .getByRole("button", { name: "Manage keys for member@example.test" })
    .click();
  await expect(page.getByText("Key owner:", { exact: false })).toContainText(
    "member@example.test",
  );
  await page.getByLabel("Key label").fill("Browser demo");
  await page
    .getByRole("button", { name: "Issue key for member@example.test" })
    .click();
  await expect(page.getByLabel("One-time gateway key value")).toBeVisible();
  await page.getByRole("button", { name: "Dismiss", exact: true }).click();
  await page.getByRole("button", { name: "Revoke Browser demo" }).click();
  await expect(page.getByRole("dialog")).toContainText("member@example.test");
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page.getByText("Browser demo  -  demo-prefix  -  Revoked"),
  ).toBeVisible();
});
test("audit six outcomes, filters, null values and member-owned responses", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Audit", exact: true }).click();
  for (const value of [
    "running",
    "success",
    "error",
    "timeout",
    "denied",
    "unknown",
  ])
    await expect(
      page.getByRole("heading", {
        name: "woo__list_orders  -  " + value,
        exact: true,
      }),
    ).toBeVisible();
  await expect(page.getByText("Unknown", { exact: true }).first()).not.toBeVisible();
  await page.locator(".audit-details > summary").first().click();
  await expect(page.getByText("Unknown", { exact: true }).first()).toBeVisible();
  await page.getByLabel("Outcome", { exact: true }).selectOption("timeout");
  await expect(
    page.getByRole("heading", { name: "woo__list_orders  -  timeout" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "woo__list_orders  -  success" }),
  ).toHaveCount(0);
});
test("chat formatted answers, actual attempts, partial and unknown effects", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  for (const message of [
    "hello",
    "product",
    "today",
    "cross",
    "partial",
    "unknown",
    "hostile",
  ]) {
    await page.getByLabel("Message", { exact: true }).fill(message);
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(
      page.getByRole("button", { name: "Send message" }),
    ).toBeEnabled();
  }
  await expect(
    page.getByText("No tool calls", { exact: true }).first(),
  ).toBeVisible();
  for (const summary of await page.locator("details.tool-activity > summary").all()) await summary.click();
  await expect(page.locator(".tool-activity-body strong").filter({hasText:"inventory__lookup_sku"})).toBeVisible();
  await expect(page.getByText(/The request reached its execution limit/)).toBeVisible();
  await expect(
    page
      .getByText(
        "Remote effects may have happened. Inspect Activity before another attempt.",
      )
      .first(),
  ).toBeVisible();
  await expect(page.locator('script[src^="https"]')).toHaveCount(0);
  await expect(page.locator(".markdown-answer").last()).toHaveText("");
  await expect(page.locator(".markdown-answer script")).toHaveCount(0);
  expect(
    await page.evaluate(() => ({
      local: localStorage.length,
      session: sessionStorage.length,
    })),
  ).toEqual({ local: 0, session: 0 });
});
test("safe failures, no automatic replay and narrow keyboard/sanitized screenshots", async ({
  page,
  request,
}) => {
  await login(page);
  await request.post("/test/control", { data: { scenario: "unavailable" } });
  await page.getByRole("button", { name: "Refresh servers" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "A required dependency is unavailable.",
  );
  await request.post("/test/control", { data: { scenario: "normal" } });
  await page.getByRole("button", { name: "Refresh servers" }).click();
  await expect(
    page.getByRole("button", { name: "Edit WooCommerce" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({
    path: `${evidence}/desktop.png`,
    fullPage: true,
    mask: [page.locator("[data-sensitive]")],
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).focus();
  await page.keyboard.type("hello");
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(
    page.getByText("Hello. No tools were needed.", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: `${evidence}/mobile.png`,
    fullPage: true,
    mask: [page.locator("[data-sensitive]")],
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  const summary = await (await request.get("/test/summary")).json();
  writeFileSync(
    `${evidence}/fixture-network-summary.json`,
    JSON.stringify(summary, null, 2),
  );
  await test.info().attach("allowlisted-network", {
    body: JSON.stringify(summary),
    contentType: "application/json",
  });
});

test("server create replace disable remove sends exact permitted bodies", async ({
  page,
}) => {
  await login(page);
  const writes: { method: string; body: any }[] = [];
  page.on("request", (r) => {
    if (r.url().includes("/api/v1/servers") && r.method() !== "GET")
      writes.push({ method: r.method(), body: r.postDataJSON() });
  });
  await page.getByRole("button", { name: "Add server", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Demo server");
  await page.getByLabel("Slug", { exact: true }).fill("demo");
  await page
    .getByLabel("URL", { exact: true })
    .fill("https://demo.example.test/mcp");
  await page.getByRole("button", { name: "Save server" }).click();
  await expect(
    page.getByRole("button", { name: "Edit Demo server" }),
  ).toBeVisible();
  expect(writes[0].body).toEqual({
    name: "Demo server",
    slug: "demo",
    url: "https://demo.example.test/mcp",
    enabled: true,
    credential: { type: "none" },
  });
  await page.getByRole("button", { name: "Edit Demo server" }).click();
  await page.getByLabel("replace", { exact: true }).check();
  await page
    .getByLabel("Authentication", { exact: true })
    .selectOption("bearer");
  await page
    .getByLabel("Credential value", { exact: true })
    .fill("dummy-entered-value");
  await page.getByRole("button", { name: "Save server" }).click();
  await expect(
    page.getByRole("button", { name: "Edit Demo server" }),
  ).toBeVisible();
  expect(writes[1].body.credential).toEqual({
    type: "bearer",
    value: "dummy-entered-value",
  });
  expect(writes[1].body).not.toHaveProperty("slug");
  const row = page
    .locator(".server-card")
    .filter({ has: page.getByRole("button", { name: "Edit Demo server" }) });
  await row.getByRole("button", { name: "Disable", exact: true }).click();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    row.getByRole("button", { name: "Enable", exact: true }),
  ).toBeVisible();
  expect(writes[2].body).toEqual({ enabled: false });
  await row.getByRole("button", { name: "Remove", exact: true }).click();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Edit Demo server" }),
  ).toHaveCount(0);
  expect(writes[3].method).toBe("DELETE");
});

test("invitation malformed expired and consumed states are explicit", async ({
  page,
  request,
}) => {
  await page.goto("/invite#token=x&token=y");
  await expect(page).toHaveURL(/\/invite$/);
  await expect(page.getByText(/missing or malformed/)).toBeVisible();
  await request.post("/test/control", { data: { scenario: "expired" } });
  await page.goto("/invite#token=fixture-invitation-token-for-tests");
  await page.getByLabel("New password").fill("Fixture-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toContainText("invalid or expired");
  await expect(page.getByLabel("New password")).toHaveValue("");
  await request.post("/test/control", { data: { scenario: "normal" } });
  await page.getByLabel("New password").fill("Fixture-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(/Account created/)).toBeVisible();
  await page.goto("/invite#token=fixture-invitation-token-for-tests");
  await page.getByLabel("New password").fill("Fixture-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("alert")).toContainText("already consumed");
});

test("chat overload provider failure and lost response never replay", async ({
  page,
  request,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  for (const [scenario, text] of [
    ["overload", "Chat is busy"],
    ["provider", "Provider is unavailable"],
  ]) {
    await request.post("/test/control", { data: { scenario } });
    await page.getByLabel("Message", { exact: true }).fill("product");
    await page.getByRole("button", { name: "Send message" }).click();
    await expect(page.getByRole("alert")).toContainText(text);
  }
  await request.post("/test/control", { data: { scenario: "normal" } });
  let count = 0;
  await page.route("**/api/v1/chat", async (route) => {
    count++;
    await route.abort("connectionreset");
  });
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "change may have happened",
  );
  await page.waitForTimeout(150);
  expect(count).toBe(1);
});

test("lost key issuance stays uncertain and does not silently reissue", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Keys", exact: true }).click();
  let issued = 0;
  await page.route("**/api/v1/members/*/keys", async (route) => {
    if (route.request().method() === "POST") {
      issued++;
      await route.fetch();
      await route.abort("connectionreset");
    } else await route.continue();
  });
  await page.getByLabel("Key label").fill("Lost issue");
  await page.getByRole("button", { name: /Issue key for/ }).click();
  await expect(page.getByRole("alert")).toContainText(
    "change may have happened",
  );
  await page.getByRole("button", { name: "Refresh keys" }).click();
  await expect(page.getByText(/Lost issue/).first()).toBeVisible();
  expect(issued).toBe(1);
  await expect(page.getByLabel("One-time gateway key value")).toHaveCount(0);
});

test("logout is serialized before another login and clears account state", async ({
  page,
}) => {
  await login(page);
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await page.getByLabel("Message", { exact: true }).fill("private admin draft");
  await page.route("**/api/v1/auth/logout", async (route) => {
    await new Promise((r) => setTimeout(r, 500));
    await route.continue();
  });
  await page.getByRole("button", { name: "Logout", exact: true }).click();
  await expect(page.getByText(/Confirming server logout/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Log in", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Login", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Email", { exact: true }).fill("member@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("Fixture-password-123");
  await page.getByRole("button", { name: "Log in", exact: true }).click();
  await page.getByRole("link", { name: "Chat", exact: true }).click();
  await expect(page.getByLabel("Message", { exact: true })).toHaveValue("");
  await expect(
    page.getByText("private admin draft", { exact: true }),
  ).toHaveCount(0);
});

test("late previous tool preview cannot replace a newer selected server", async ({
  page,
}) => {
  await login(page);
  await page.route(
    "**/api/v1/servers/33333333-3333-4333-8333-333333333333/tools?*",
    async (route) => {
      await new Promise((r) => setTimeout(r, 500));
      await route.continue();
    },
  );
  await page
    .getByRole("button", { name: "View tools", exact: true })
    .nth(0)
    .click();
  await page
    .getByRole("button", { name: "View tools", exact: true })
    .nth(1)
    .click();
  await expect(
    page.getByRole("heading", { name: "Tools: Inventory", exact: true }),
  ).toBeVisible();
  await page.waitForTimeout(700);
  await expect(
    page.getByRole("heading", { name: "Tools: WooCommerce", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(/Stale preview/)).toBeVisible();
});

test("API caller protection rejects missing CSRF and never sends third-party requests", async ({
  page,
}) => {
  const requests: string[] = [];
  page.on("request", (r) => requests.push(r.url()));
  await login(page);
  const result = await page.evaluate(async () => {
    const r = await fetch("/api/v1/invitations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "test@example.test", role: "member" }),
    });
    return r.status;
  });
  expect(result).toBe(403);
  await page
    .getByRole("button", { name: "View tools", exact: true })
    .first()
    .click();
  await expect(page.getByText(/onerror/)).toBeVisible();
  expect(
    requests.every((url) => new URL(url).origin === "http://127.0.0.1:18080"),
  ).toBe(true);
});

test('member own key defaults to verified owner and audit is server-filtered',async({page})=>{
 await login(page,'member@example.test');await page.getByRole('link',{name:'Keys',exact:true}).click();await expect(page.getByText('Key owner:',{exact:false})).toContainText('member@example.test');await page.getByLabel('Key label').fill('Own member key');await page.getByRole('button',{name:'Issue key for member@example.test'}).click();await expect(page.getByLabel('One-time gateway key value')).toBeVisible();await page.getByRole('button',{name:'Dismiss',exact:true}).click();await page.getByRole('link',{name:'Audit',exact:true}).click();await expect(page.getByText('Your activity.',{exact:false})).toBeVisible();await expect(page.getByLabel('User UUID')).toHaveCount(0);const rows=await page.evaluate(async()=>await(await fetch('/api/v1/audit')).json());expect(rows.items.length).toBeGreaterThan(0);expect(rows.items.every((r:any)=>r.user_id==='22222222-2222-4222-8222-222222222222')).toBe(true);await expect(page.getByRole('heading',{name:'woo__list_orders - success'})).toBeVisible();await expect(page.getByRole('heading',{name:'woo__list_orders - running'})).toHaveCount(0);
});

test('disabled and never-checked tool previews are empty and never stale',async({page})=>{
 await login(page);
 const disabled=page.locator('.server-card').filter({has:page.getByRole('button',{name:'Edit Microsoft Learn',exact:true})});
 await disabled.getByRole('button',{name:'View tools',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tools: Microsoft Learn',exact:true})).toBeVisible();
 await expect(page.getByText('No discovered tools.',{exact:true})).toBeVisible();
 await expect(page.getByText(/Stale preview/)).toHaveCount(0);
 const fresh=page.locator('.server-card').filter({has:page.getByRole('button',{name:'Edit Never checked',exact:true})});
 await fresh.getByRole('button',{name:'View tools',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Tools: Never checked',exact:true})).toBeVisible();
 await expect(page.getByText('No discovered tools.',{exact:true})).toBeVisible();
 await expect(page.getByText(/Stale preview/)).toHaveCount(0);
});


test("formatted product answer is a semantic table with contained mobile scrolling", async ({page}) => {
  await login(page);
  await page.getByRole("link", {name:"Chat",exact:true}).click();
  await page.getByLabel("Message", {exact:true}).fill("formatted products");
  await page.getByRole("button", {name:"Send message",exact:true}).click();
  const table=page.locator(".markdown-answer table");
  await expect(table).toBeVisible();
  await expect(table.getByRole("columnheader")).toHaveCount(3);
  await expect(table.getByRole("row")).toHaveCount(4);
  await expect(table).toContainText(String.fromCodePoint(0x20b9) + "499.00");
  await expect(page.locator(".markdown-answer strong").first()).toHaveText("IDs");
  await expect(page.locator(".markdown-answer pre")).toHaveCount(0);
  await page.setViewportSize({width:1440,height:1000});
  await page.screenshot({path:`${evidence}/chat-formatted-desktop.png`,fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${evidence}/chat-formatted-mobile.png`,fullPage:true});
});
