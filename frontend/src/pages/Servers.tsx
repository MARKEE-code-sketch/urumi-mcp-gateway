import { useState } from "react";
import { Api, ApiError } from "../api";
import type { Server, Session } from "../types";
import { Feedback, useRead, utc } from "../components/Feedback";
import { Pagination } from "../components/Pagination";
import { Confirm } from "../components/Confirm";
import { ToolInputs } from "../components/ToolInputs";
import { Icon } from "../components/Icon";
type Props = { api: Api; session: Session; pending: (v: boolean) => void };
function Preview({ api, server }: { api: Api; server: Server }) {
  const [page, setPage] = useState(1),
    [size, setSize] = useState(20);
  const r = useRead(
    () => api.tools(server.id, page, size),
    [api, server.id, page, size],
  );
  return (
    <section className="server-tools-panel" aria-label={`Tools for ${server.name}`}>
      <h2>Tools: {server.name}</h2>
      {r.data?.stale && (
        <p role="status">
          Stale preview: previously discovered; current availability is unknown.
        </p>
      )}
      <Feedback error={r.error} loading={r.loading} />
      <button onClick={r.reload}>Refresh tools</button>
      {r.data && !r.data.items.length && <p>No discovered tools.</p>}
      {r.data?.items.map((tool) => (
        <article className="tool-card" key={tool.gateway_name}>
          <div className="tool-heading"><span className="server-icon"><Icon name="package" /></span><h3>{tool.gateway_name}</h3></div>
          <p>{tool.description}</p>
          <ToolInputs schema={tool.inputSchema} />
          <details><summary>Technical details</summary><p>Gateway name: {tool.gateway_name}</p><p>Upstream name: {tool.upstream_name}</p></details>
        </article>
      ))}
      <Pagination
        page={page}
        more={!!r.data?.has_more}
        onPage={setPage}
        size={size}
        onSize={(n) => {
          setSize(n);
          setPage(1);
        }}
      />
    </section>
  );
}
export function Servers({ api, session, pending }: Props) {
  const [page, setPage] = useState(1),
    [size, setSize] = useState(20),
    [selected, setSelected] = useState<Server>(),
    [edit, setEdit] = useState<Server | null | undefined>(),
    [name, setName] = useState(""),
    [slug, setSlug] = useState(""),
    [url, setUrl] = useState(""),
    [enabled, setEnabled] = useState(true),
    [mode, setMode] = useState("keep"),
    [auth, setAuth] = useState("none"),
    [header, setHeader] = useState(""),
    [value, setValue] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [confirm, setConfirm] = useState<{ message: string; action: () => void }>();
  const r = useRead(() => api.servers(page, size), [api, page, size]);
  const admin = session.user.role === "admin";
  function open(server: Server | null) {
    setEdit(server);
    setName(server?.name ?? "");
    setSlug(server?.slug ?? "");
    setUrl(server?.url ?? "");
    setEnabled(server?.enabled ?? true);
    setMode(server ? "keep" : "replace");
    setAuth("none");
    setValue("");
    setHeader("");
    setError(undefined);
  }
  async function change(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true);
    pending(true);
    setError(undefined);
    try {
      await action();
      setEdit(undefined);
      setSelected(undefined);
      r.reload();
    } catch (e) {
      setError(e);
    } finally {
      setValue("");
      setBusy(false);
      pending(false);
    }
  }
  async function save() {
    const data: Record<string, unknown> = { name, url, enabled };
    if (!edit) {
      if (!/^[a-z][a-z0-9-]{0,23}$/.test(slug))
        throw new ApiError("Use a lowercase slug of at most 24 characters.");
      data.slug = slug;
    }
    if (!/^[\x21-\x7e]{1,2048}$/.test(url))
      throw new ApiError("Enter an ASCII URL up to 2,048 characters.");
    if (mode === "clear") data.credential = { type: "none" };
    else if (mode === "replace") {
      if (value.length > 4096 || /[\r\n]/.test(value))
        throw new ApiError("Credential value is invalid.");
      data.credential =
        auth === "none"
          ? { type: "none" }
          : auth === "bearer"
            ? { type: "bearer", value }
            : { type: "header", header_name: header, value };
    }
    return api.request(
      edit ? "/servers/" + edit.id : "/servers",
      edit ? "PATCH" : "POST",
      data,
    );
  }
  return (
    <>
      <div className="page-heading"><div><h1 tabIndex={-1}>Servers</h1>
      <p>
        Inspect stored status and discovered tools. Refresh reads the gateway;
        it does not ping servers.
      </p>
      </div><div className="page-actions"><button
        onClick={() => {
          setSelected(undefined);
          r.reload();
        }}
      >
        Refresh servers
      </button>
      {admin && (
        <button disabled={busy} onClick={() => open(null)}>
          <Icon name="plus" /> Add server
        </button>
      )}
      </div></div>
      <Feedback error={r.error || error} loading={r.loading} />
      {r.data && !r.data.items.length && <p>No registered servers.</p>}
      <section className="server-grid" aria-label="Registered MCP servers">
        {r.data?.items.map((s) => (
          <article className="server-card" key={s.id} aria-label={s.name}>
            <div className="server-card-head">
              <span className="server-icon"><Icon name="servers" /></span>
              <span className={`status-badge status-${s.status.toLowerCase()}`}>{s.status}</span>
            </div>
            <h2>{s.name}</h2>
            <p className="server-slug">{s.slug}</p>
            <dl className="server-meta">
              <div><dt>Last checked</dt><dd>{utc(s.last_checked_at)}</dd></div>
              <div><dt>Stored status</dt><dd>{s.status_reason === "NOT_CHECKED" ? "Not checked yet" : s.status_reason ?? "No additional detail"}{!s.enabled && " - Disabled"}</dd></div>
            </dl>
            <div className="server-card-actions">
                  <button onClick={() => setSelected(s)}>View tools</button>
                  {admin && (
                    <>
                      <button disabled={busy} onClick={() => open(s)}>
                        Edit {s.name}
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          setConfirm({
                            message: `${s.enabled ? "Disable" : "Enable"} ${s.name}? Disabling stops gateway access.`,
                            action: () =>
                              void change(() =>
                                api.request("/servers/" + s.id, "PATCH", {
                                  enabled: !s.enabled,
                                }),
                              ),
                          })
                        }
                      >
                        {s.enabled ? "Disable" : "Enable"}
                      </button>
                      <button
                        disabled={busy}
                        onClick={() =>
                          setConfirm({
                            message: `Remove ${s.name}? This removes registration, not the remote application.`,
                            action: () =>
                              void change(() =>
                                api.request("/servers/" + s.id, "DELETE"),
                              ),
                          })
                        }
                      >
                        Remove
                      </button>
                    </>
                  )}

            </div>
          </article>
        ))}
      </section>
      <Pagination
        page={page}
        more={!!r.data?.has_more}
        onPage={(n) => {
          setPage(n);
          setSelected(undefined);
        }}
        size={size}
        onSize={(n) => {
          setSize(n);
          setPage(1);
          setSelected(undefined);
        }}
      />
      {selected && <Preview key={selected.id} api={api} server={selected} />}
      {admin && edit !== undefined && (
        <section>
          <h2>{edit ? "Edit server" : "Create server"}</h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (
                mode === "clear" ||
                (!!edit && mode === "replace" && auth === "none")
              )
                setConfirm({
                  message: "Clear the saved credential for " + name + "?",
                  action: () => void change(save),
                });
              else void change(save);
            }}
          >
            <label>
              Name
              <input
                required
                maxLength={100}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Slug
              <input
                required
                readOnly={!!edit}
                maxLength={24}
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
              />
            </label>
            <label>
              URL
              <input
                required
                maxLength={2048}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </label>
            <label>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              Enabled
            </label>
            {edit && (
              <p>
                Saved authentication: {edit.auth_type}; header:{" "}
                {edit.header_name ?? "None"}. Existing values are never
                retrieved.
              </p>
            )}
            <fieldset>
              <legend>Credential action</legend>
              {(edit ? ["keep", "replace", "clear"] : ["replace"]).map((m) => (
                <label key={m}>
                  <input
                    type="radio"
                    name="credential"
                    checked={mode === m}
                    onChange={() => {
                      setMode(m);
                      setValue("");
                    }}
                  />
                  {m}
                </label>
              ))}
            </fieldset>
            {mode === "replace" && (
              <>
                <label>
                  Authentication
                  <select
                    aria-label="Authentication"
                    value={auth}
                    onChange={(e) => {
                      setAuth(e.target.value);
                      setValue("");
                    }}
                  >
                    <option value="none">None</option>
                    <option value="bearer">Bearer</option>
                    <option value="header">Custom header</option>
                  </select>
                </label>
                {auth === "header" && (
                  <label>
                    Header name
                    <input
                      required
                      maxLength={100}
                      value={header}
                      onChange={(e) => setHeader(e.target.value)}
                    />
                  </label>
                )}
                {auth !== "none" && (
                  <label>
                    Credential value
                    <input
                      type="password"
                      autoComplete="off"
                      required
                      maxLength={4096}
                      value={value}
                      onChange={(e) => setValue(e.target.value)}
                    />
                  </label>
                )}
              </>
            )}
            <button disabled={busy}>Save server</button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setEdit(undefined);
                setValue("");
              }}
            >
              Cancel
            </button>
          </form>
        </section>
      )}
      {confirm && (
        <Confirm
          message={confirm.message}
          onConfirm={() => {
            setConfirm(undefined);
            confirm.action();
          }}
          onCancel={() => setConfirm(undefined)}
        />
      )}
    </>
  );
}
