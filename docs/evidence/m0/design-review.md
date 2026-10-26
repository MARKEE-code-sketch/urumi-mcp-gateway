# M0 design review and document checks

**Date:** 14 October 2026. **Verdict:** READY FOR USER REVIEW; not design approval or module acceptance.

## Independent review

An independent reviewer compared the assignment, approved choices, blueprint, three contracts, local-tool schemas, and sample replies. It found required tool coverage, generic hosted-server discovery/static credentials, pagination, tool naming, user attribution, revocation, timeout uncertainty, and credential boundaries represented.

Applied its two clarifications: ordinary upstream names for direct prefixing match ^[A-Za-z0-9_.-]+$; failure samples distinguish a gateway-to-MCP request from a WooCommerce REST request. An invalid price may reach the MCP helper, but no REST write should occur. Sample schema matching was inspected, not executed through a formal JSON Schema validator.

## Checks actually run

Via the Node workspace tool, fs.readFile + JSON.parse loaded contracts/mcp-tools.schema.json and tests/fixtures/m0/examples.json. A Set checked six unique local tool names. For eight success examples, JSON.parse(result.content[0].text) matched structuredContent with isError=false. Three failure examples parsed to error objects, had isError=true, and omitted structuredContent. Four JSON examples in the Markdown drafts parsed successfully. Nine relative document links resolved to existing files. Written documents were read back and compared with the written strings.

These are document/sample consistency checks. The validation libraries jsonschema (Python) and Ajv (Node) were not available. No validation dependency was installed. Formal JSON Schema validation, executable MCP fixture behavior, real SDK/client negotiation/authentication, version pinning, real provider tool calling, and Kubernetes behavior remain unverified. No provider keys were read or used.

## Gate

User review is next. Proposed defaults: invitation24h, session8h, member own audit only, discovery3s/tool10s/status5s, chat8 rounds. Review the full cookie/Secret/URL/name/session design as well. Application implementation and M0 experiments are not marked approved by this verdict. M1 is not authorized.
