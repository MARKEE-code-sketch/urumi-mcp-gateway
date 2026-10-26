# M0: tool message agreements

**Status:** Design approved by the user on 14 October 2026. Application behavior is not implemented; local M0 fixtures exercise only the documented sample messages.

## WHAT, WHY, and HOW

**WHAT:** Agree on the information each tool needs and the reply it gives.

**WHY:** The shop helper, gateway, dashboard, and AI can be built separately only if they understand the same messages.

**HOW:** Start with six local tool definitions and prepared replies. Discover hosted tools from their server. A schema is a written checklist for a message: required fields, value types, and allowed values. The accompanying mcp-tools.schema.json contains the exact proposed checklists for our local tools.

Example: “Create a Blue Mug for ₹299” becomes create_product with name and regular_price. The gateway checks the person, calls the shop helper, and records the result. Money is text such as “299.00” so decimal prices are not rounded by floating-point calculations.

## The six tools we own

The five shop actions are required. The Inventory lookup is our selected sample helper. IDs for products/orders are positive integers from WooCommerce, distinct from platform UUIDs.

| Tool | Inputs | Successful reply |
|---|---|---|
| list_products | Optional search, exact sku, page, per_page | items of Product, page, per_page, has_more |
| create_product | Required name and regular_price; optional sku | product: Product |
| list_orders | Optional created_from, created_to, status, page, per_page | items of Order, page, per_page, has_more |
| get_order | Required order_id | order: Order |
| update_order_status | Required order_id and status | order: Order after update |
| lookup_sku | Required sku | sku, found, warehouses |

All inputs are JSON objects. Our local tools reject unknown fields. Page starts at 1; per_page defaults to 20 and is between 1 and 50. Names/SKUs are trimmed and cannot be blank. Prices are nonnegative decimal strings with at most two fractional digits; normalize replies to two digits. Empty lists are a successful result. None of these arguments can override caller identity, credentials, or destination URLs.

Create a simple published product in the configured INR shop. A supplied SKU must be unique; duplicate-SKU errors are reported clearly. No automatic retry follows a timed-out write. Creating products and changing order status can affect the real shop; describe that in the tool metadata. Only update the requested status; changing a status to refunded does not itself promise a payment refund.

Product fields: id, name, sku (empty if unset), price, regular_price, currency, status, permalink. Price fields may be null if the source has no price. Order fields: id, number, status, currency, total, date_created (normalized UTC), line_items with product_id, name, sku, quantity, total. A line item's product_id may be 0 for a deleted/manual item. Omit billing addresses, emails, phone numbers, payment tokens, and raw shop metadata.

Read order status as a string to preserve existing store values. For writes, the initial accepted statuses are pending, processing, on-hold, completed, cancelled, refunded, and failed. Custom plugin statuses and trash are outside this initial tool contract; changing these bounds requires review. WooCommerce remains responsible for its own status-transition effects.

Inventory returns sample warehouse data. A known SKU might return Bengaluru and quantity 12; an unknown SKU returns found=false and an empty warehouses list. It must not pretend to reflect current WooCommerce stock.

## Today's orders, without timezone surprises

created_from and created_to are optional offset-aware ISO8601 timestamps. Reject a timezone-free date or a reversed range. They mean an inclusive creation-time interval. An omitted bound leaves that side open. Status is optional and does not silently exclude COD orders.

For “today,” the agent captures one now value, calculates midnight in Asia/Kolkata, and passes both bounds. Fixture example: noon on 14 October is 2026-10-14T06:30:00Z; that day's midnight is 2026-10-13T18:30:00Z. All pages use those same fixed bounds. Follow has_more until false; if a configured work/time limit prevents completion, say the answer is partial rather than presenting it as all orders.

M3 maps these bounds to the WooCommerce v3 orders API with dates_are_gmt=true. Normalize date_created_gmt to a UTC timestamp. Verify the installed shop's boundary behavior using orders before, exactly at, and after midnight. If the source filter excludes a boundary, widen the source query and enforce the agreed interval before returning pages. No direct database queries are needed.

## MCP envelopes and failures

SDK negotiation handles initialize, protocol version, headers, and transport lifecycle. The November 2025 specification below is a reference baseline, not a claim that any SDK/protocol pair has passed. Record the negotiated versions during M0 experiments. /mcp is the gateway endpoint; upstream URLs are independent registry settings.

A successful own-tool CallToolResult contains isError=false, structuredContent holding the reply object, and a text content block containing the same object serialized as JSON. When an outputSchema is advertised, the successful object must match it.

A tool execution failure uses isError=true and a text content block containing a safe error object; omit structuredContent when it would violate the advertised success schema. Example:

~~~json
{"content":[{"type":"text","text":"{\"error\":{\"code\":\"ORDER_NOT_FOUND\",\"message\":\"Order 999 was not found.\"}}"}],"isError":true}
~~~

| Situation | Contract |
|---|---|
| Malformed MCP envelope or unknown tool | Standard MCP/JSON-RPC error, such as invalid params for an unknown tool; SDK owns protocol encoding. |
| Valid call with invalid own-tool arguments | M3 returns a safe INVALID_ARGUMENT execution error before any WooCommerce REST request. A gateway-to-MCP call may already have occurred. |
| Missing/wrong/revoked gateway key | HTTP 401; no upstream call. Track an attempted tool denial as defined in identity-and-audit.md. |
| Disabled server or stale disabled tool name | TOOL_DISABLED, denied outcome; no upstream call. |
| Order absent | ORDER_NOT_FOUND, error outcome. |
| Upstream rejects its configured credential | UPSTREAM_AUTH_FAILED, error outcome; do not expose its response or credential. |
| Connection/protocol failure | UPSTREAM_UNAVAILABLE or UPSTREAM_PROTOCOL_ERROR; other servers continue. |
| Deadline expires | UPSTREAM_TIMEOUT, timeout outcome; a write may have completed remotely. Do not claim it was rolled back. |
| Audit storage/finalization fails | AUDIT_UNAVAILABLE before dispatch or AUDIT_FINALIZATION_FAILED after dispatch, following the identity contract. |

M6's internal invoke_tool returns request_id, audit_id, outcome, and result (the MCP CallToolResult). A successful external MCP reply remains a standard MCP result; it does not get wrapped in the dashboard API format. On a protocol/HTTP rejection, the adapter uses the matching protocol response instead of manufacturing a successful CallToolResult.

## A gateway that can use external servers

Register a URL and an optional credential. M6 reads every page of tools/list and preserves each tool's inputSchema, description, optional outputSchema, and relevant annotations. Do not assume a fixed set of field names or build a Microsoft-only adapter. Reject malformed schemas with a safe per-server error. The gateway preserves normal MCP result content, including structured and text results, subject to configured size limits and credential sanitization. Do not silently drop unsupported content or report truncation as a complete result.

The chat adapter may support fewer schema/content features than the MCP gateway. If the chosen model cannot use a particular schema or content type, show a clear chat limitation; do not silently change the upstream contract. Test that limitation independently.

Microsoft Learn's documented endpoint is https://learn.microsoft.com/api/mcp. It currently needs no credential. Its real tool names/schemas will be discovered and saved as evidence; no invented hosted tool definition is checked into our own-tool schema file.

Support no authentication, Authorization: Bearer with a saved upstream token, or an API key in a named header. Upstream connections use only registry configuration. Never forward the member's gateway Authorization header or dashboard cookie. Reject credential values containing CR/LF and credential-header names reserved for routing, cookies, transport framing, or MCP protocol/session headers. Only bearer mode may set Authorization. Dynamic OAuth is outside core scope.

Remove known configured secret values from diagnostics and sanitize an upstream result that echoes them; never put a key into a model prompt. Untrusted servers can still supply misleading or transformed malicious content, so do not promise protection against every compromised-server exfiltration trick. Review destination restrictions and these trust limits in the threat model.

## Tool names and routing

Use an immutable unique server slug, proposed format: lower-case letter followed by up to 23 lower-case letters, digits, or hyphens. Usually the public name is slug__original_name, for example woocommerce__list_products. Names remain case-sensitive. An ordinary upstream tool name must match the exact ASCII pattern ^[A-Za-z0-9_.-]+$ before direct prefixing; other names use the hash alias below.

For model compatibility, our gateway public-name limit is proposed as 64 characters; MCP's own recommendation permits longer names. If the upstream name has unsafe characters, makes the public name too long, or begins with the reserved h_ prefix, use slug__h_ followed by the first 32 hexadecimal characters of SHA-256 of the original UTF-8 name. This gives a stable alias. Store an explicit mapping to server UUID and original tool name; never guess the route by splitting a supplied name. Detect alias collisions at discovery and report that server's discovery error without affecting other servers.

Upstream edits, disable, or removal invalidate relevant caches/connections. Recheck server state just before dispatch. A failed discovery can retain the last known list with an Unreachable status, but a disabled server never appears in a fresh list. A previously undiscovered dead server contributes no invented tools. Protocol tool-list changes are signalled when supported; clients may still need refresh/reconnect.

## Ownership and independent checks

M0 owns this agreement and sample data. M3 owns WooCommerce input validation and REST mapping. M4 owns Inventory and the external compatibility probe. M6 owns discovery/mapping/timeouts/authenticated dispatch; M7 consumes the same gateway result; M10 connects the real pieces.

Check all six local schemas, multiple list pages, empty results, missing orders, duplicate SKU, bad prices/statuses, UTC/day boundaries, duplicate/long/unsafe tool names, wrong credentials, disabled tools, slow/dead upstreams, and output redaction. M0 supplies examples; M3/M4/M6 implement their own checks. Fixtures are not evidence of live shop changes.

**Proposed design values for review:** discovery 3 seconds per server, tool execution 10 seconds, status polling 5 seconds; validate them against actual hosts. Client/SDK session mode and exact payload/tool-list bounds remain experiment/design decisions. No hard-coded package versions are selected by this document.

Technical references support protocol/API choices, not extra product requirements: [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [MCP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [WooCommerce products](https://developer.woocommerce.com/docs/apis/rest-api/v3/products/), [WooCommerce orders](https://developer.woocommerce.com/docs/apis/rest-api/v3/orders/), [Microsoft Learn](https://learn.microsoft.com/en-us/training/support/mcp).
