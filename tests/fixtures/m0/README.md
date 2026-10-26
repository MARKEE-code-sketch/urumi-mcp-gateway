# M0 sample data

These JSON replies are prepared examples, not live shop data or executed tests. examples.json covers the six local tools, expected errors, and planned authentication/collision/timeout fixtures. Its credentials are deliberately fake. contracts/mcp-tools.schema.json provides the proposed input/output schemas.

No executable MCP test server, real AI call, pinned dependency set, or Kubernetes test is created by these files. Those experiments follow design approval.

Failure examples distinguish mcp_upstream_dispatched (gateway to MCP helper) from shop_rest_dispatched (shop helper to WooCommerce REST API). Invalid price may reach M3, but M3 must reject it before contacting WooCommerce. These are proposed scenario facts, not observations.
