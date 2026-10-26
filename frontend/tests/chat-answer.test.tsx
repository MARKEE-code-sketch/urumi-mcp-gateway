import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { ChatAnswer } from "../src/components/ChatAnswer";

afterEach(cleanup);

describe("safe formatted chat answers", () => {
  it("renders the product answer as a semantic three-column table with INR and SKU values", () => {
    const { container } = render(<ChatAnswer answer={`Here are the **3 products** currently in your shop.

| Product | SKU | Price (INR) |
| :--- | :---: | ---: |
| Everyday essential (12) | DEMO-001 | ₹499.00 |
| Classic notebook (18) | M10-BROWSER-NOTEBOOK | ₹129.00 |
| Test product (20) | M10-TLS-PROBE | ₹1.00 |`} />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader")).toHaveLength(3);
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(screen.getByText("3 products").tagName).toBe("STRONG");
    expect(within(table).getByText("₹499.00").className).toBe("text-align-right");
    expect(within(table).getByText("M10-BROWSER-NOTEBOOK").className).toBe("text-align-center");
    expect(screen.getByRole("region", { name: "Answer table" }).tabIndex).toBe(0);
    expect(container.querySelector("[style]")).toBeNull();
  });

  it("suppresses raw HTML, scripts and image fetches, and allows only deliberate safe links", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    const { container } = render(<ChatAnswer answer={`<script>alert('bad')</script>

<img src="https://hostile.example/tracker" onerror="alert(1)">

![tracker](https://hostile.example/track.png)

[bad](javascript:alert%281%29) [data](data:text/html,bad) [relative](/admin) [protocol](//hostile.example)

[Docs](https://example.com/docs) [Local](http://localhost:8080) [Email](mailto:team@example.com)`} />);
    expect(container.querySelector("script,img,iframe,object,embed,style")).toBeNull();
    expect(container.querySelector("[onclick],[onerror],[style]")).toBeNull();
    expect(screen.getAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(["https://example.com/docs", "http://localhost:8080", "mailto:team@example.com"]);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("preserves prose, lists, code and long Unicode text without interpreting code as HTML", () => {
    const longText = "नमस्ते ₹ 🛒 ".repeat(300);
    const { container } = render(<ChatAnswer answer={`Plain response.

## Next steps

- Check stock
- Review orders

1. First
2. Second

Use \`woocommerce__list_products\`.

\`\`\`html
<img src=x onerror=alert(1)>
\`\`\`

${longText}`} />);
    expect(screen.getByText("Plain response.").tagName).toBe("P");
    expect(screen.getByRole("heading", { name: "Next steps" }).tagName).toBe("H2");
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.getByText("woocommerce__list_products").tagName).toBe("CODE");
    expect(container.querySelector("pre code")?.textContent).toContain("<img src=x onerror=alert(1)>");
    expect(container.textContent).toContain(longText.trim());
    expect(container.querySelector("img")).toBeNull();
  });
});
