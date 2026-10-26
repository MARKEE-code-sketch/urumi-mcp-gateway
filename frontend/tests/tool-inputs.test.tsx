import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { ToolInputs } from "../src/components/ToolInputs";

afterEach(cleanup);
describe("readable tool inputs", () => {
  it("shows nested parameters, actual constraints and required status", () => {
    const { container } = render(<ToolInputs schema={{ type: "object", required: ["product"], properties: { product: { type: "object", description: "The selected product", required: ["sku"], properties: { sku: { type: "string", minLength: 2 }, page: { type: "integer", minimum: 1, maximum: 10 } } } } }} />);
    expect(screen.getByText("product")).toBeTruthy();
    expect(screen.getByText("sku")).toBeTruthy();
    expect(screen.getAllByText("Required")).toHaveLength(2);
    expect(screen.getByText("Optional")).toBeTruthy();
    expect(screen.getByText("Minimum length")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy();
    expect(container.querySelector("pre")).toBeNull();
    expect(container.textContent).not.toContain('"properties"');
  });
  it("keeps arrays and alternative schemas readable inside disclosures", () => {
    const { container } = render(<ToolInputs schema={{ properties: { tags: { type: "array", minItems: 1, items: { anyOf: [{ type: "string", enum: ["red", "green"] }, { type: "integer", minimum: 3 }] } } } }} />);
    expect(screen.getByText("Array item details")).toBeTruthy();
    expect(screen.getByText("At least one matching option")).toBeTruthy();
    expect(screen.getByText("Allowed values: red; green")).toBeTruthy();
    expect(container.querySelectorAll("details")).toHaveLength(2);
    expect(container.querySelector("pre")).toBeNull();
  });
  it("escapes hostile names and descriptions without creating markup", () => {
    const hostile = '<img src="https://invalid.example/x" onerror="alert(1)">';
    const { container } = render(<ToolInputs schema={{ properties: { [hostile]: { type: "string", description: "<script>alert(1)</script> & plain" } } }} />);
    expect(screen.getByText(hostile)).toBeTruthy();
    expect(screen.getByText("<script>alert(1)</script> & plain")).toBeTruthy();
    expect(container.querySelector("img,script,iframe")).toBeNull();
  });
  it("names unsupported constraints without dumping their objects", () => {
    const { container } = render(<ToolInputs schema={{ type: "object", $ref: "private-reference", not: { secret: "hidden-object-value" }, default: { private: "hidden-default" } }} />);
    expect(screen.getByText("Unsupported constraint: $ref.")).toBeTruthy();
    expect(screen.getByText("Unsupported constraint: not.")).toBeTruthy();
    expect(container.textContent).not.toContain("hidden-object-value");
    expect(container.textContent).not.toContain("hidden-default");
    expect(container.querySelector("pre")).toBeNull();
  });
  it("preserves the original complete-schema size and depth limits", () => {
    const { rerender } = render(<ToolInputs schema={{ enum: Array(2001).fill("value") }} />);
    expect(screen.getByRole("status").textContent).toContain("Schema display limit exceeded");
    let schema: unknown = { type: "string" };
    for (let i = 0; i < 34; i++) schema = { items: schema };
    rerender(<ToolInputs schema={schema} />);
    expect(screen.getByRole("status").textContent).toContain("Schema display limit exceeded");
  });
  it("bounds visible nested details and parameter count", () => {
    let nested: unknown = { type: "string" };
    for (let i = 0; i < 9; i++) nested = { items: nested };
    const properties = Object.fromEntries(Array.from({ length: 60 }, (_, i) => [`parameter-${i}`, { type: "string" }]));
    const { container, rerender } = render(<ToolInputs schema={{ properties }} />);
    expect(screen.getByText("Additional parameters exceed the display limit.")).toBeTruthy();
    expect(container.querySelectorAll(".schema-field")).toHaveLength(50);
    rerender(<ToolInputs schema={nested} />);
    expect(screen.getByText("Further schema details exceed the display limit.")).toBeTruthy();
  });
});
