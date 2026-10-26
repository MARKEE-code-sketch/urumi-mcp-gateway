import type { ReactNode } from "react";
import { schemaText } from "../api";

const object = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === "object" && !Array.isArray(v);
const text = (v: unknown) => String(v).slice(0, 500);
const scalar = (v: unknown) =>
  v === null ? "null" : ["string", "number", "boolean"].includes(typeof v) ? text(v) : "Complex value (not displayed)";
const constraints: Record<string, string> = {
  minimum: "Minimum", maximum: "Maximum", exclusiveMinimum: "Exclusive minimum",
  exclusiveMaximum: "Exclusive maximum", multipleOf: "Multiple of", minLength: "Minimum length",
  maxLength: "Maximum length", pattern: "Pattern", format: "Format", minItems: "Minimum items",
  maxItems: "Maximum items", uniqueItems: "Unique items", minProperties: "Minimum properties",
  maxProperties: "Maximum properties", default: "Default", const: "Constant", readOnly: "Read only",
  writeOnly: "Write only", deprecated: "Deprecated",
};
const supported = new Set(["type", "title", "description", "properties", "required", "items", "enum", "additionalProperties", "anyOf", "oneOf", "allOf", ...Object.keys(constraints)]);

/** A read-only schema guide. It never executes tools or interprets upstream HTML. */
export function ToolInputs({ schema }: { schema: unknown }) {
  // Keep the original whole-schema budget before constructing a bounded UI tree.
  try { schemaText(schema); } catch {
    return <p role="status">Schema display limit exceeded. Try a smaller page.</p>;
  }
  let count = 0;
  function node(value: unknown, depth: number): ReactNode {
    if (++count > 150 || depth > 6)
      return <p>Further schema details exceed the display limit.</p>;
    if (typeof value === "boolean") return <p>{value ? "Any value is allowed." : "No value is allowed."}</p>;
    if (!object(value)) return <p>Unsupported schema format.</p>;
    const required = Array.isArray(value.required) ? value.required.filter((v) => typeof v === "string") : [];
    const fields = object(value.properties) ? Object.entries(value.properties) : [];
    const type = typeof value.type === "string" ? value.type : Array.isArray(value.type) ? value.type.map(scalar).slice(0, 20).join(" or ") : fields.length ? "object" : undefined;
    return <>
      {type && <span className="schema-type">{text(type)}</span>}
      {typeof value.title === "string" && <p>{text(value.title)}</p>}
      {typeof value.description === "string" && <p>{text(value.description)}</p>}
      {fields.length > 0 && <ul className="schema-fields">{fields.slice(0, 50).map(([name, child]) => <li className="schema-field" key={name}>
        <div className="schema-field-head"><strong>{text(name)}</strong><span className={required.includes(name) ? "schema-required" : "schema-optional"}>{required.includes(name) ? "Required" : "Optional"}</span></div>
        <div className="schema-nested">{node(child, depth + 1)}</div>
      </li>)}</ul>}
      {fields.length > 50 && <p>Additional parameters exceed the display limit.</p>}
      {depth === 0 && fields.length === 0 && <p>No named parameters are declared.</p>}
      {required.filter((name) => !fields.some(([key]) => key === name)).length > 0 && <p>Other required names: {required.filter((name) => !fields.some(([key]) => key === name)).slice(0, 50).map(text).join(", ")}</p>}
      {Array.isArray(value.enum) && <p>Allowed values: {value.enum.slice(0, 20).map(scalar).join("; ")}{value.enum.length > 20 ? "; more values exceed the display limit" : ""}</p>}
      <dl className="schema-constraints">{Object.entries(constraints).filter(([key]) => key in value).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{scalar(value[key])}</dd></div>)}</dl>
      {"items" in value && <details><summary>Array item details</summary>{Array.isArray(value.items) ? <p>Unsupported constraint: tuple items.</p> : node(value.items, depth + 1)}</details>}
      {"additionalProperties" in value && <details><summary>Additional properties</summary>{node(value.additionalProperties, depth + 1)}</details>}
      {(["anyOf", "oneOf", "allOf"] as const).filter((key) => key in value).map((key) => <details key={key}><summary>{key === "anyOf" ? "At least one matching option" : key === "oneOf" ? "Exactly one matching option" : "All conditions must match"}</summary>{Array.isArray(value[key]) ? value[key].slice(0, 20).map((child, index) => <section key={index}><h5>Option {index + 1}</h5>{node(child, depth + 1)}</section>) : <p>Unsupported constraint format: {key}.</p>}{Array.isArray(value[key]) && value[key].length > 20 && <p>Additional options exceed the display limit.</p>}</details>)}
      {Object.keys(value).filter((key) => !supported.has(key)).slice(0, 50).map((key) => <p key={key}>Unsupported constraint: {text(key)}.</p>)}
    </>;
  }
  return <section className="tool-inputs" aria-label="Tool input parameters"><h4>Input parameters</h4>{node(schema, 0)}</section>;
}
