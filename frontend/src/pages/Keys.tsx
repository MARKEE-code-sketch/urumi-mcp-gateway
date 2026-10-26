import { useState } from "react";
import { Api } from "../api";
import type { User, Key } from "../types";
import { Feedback, useRead, utc } from "../components/Feedback";
import { Pagination } from "../components/Pagination";
import { OneTimeValue } from "../components/OneTimeValue";
import { Confirm } from "../components/Confirm";
export function Keys({
  api,
  owner,
  pending,
}: {
  api: Api;
  owner: User;
  pending: (v: boolean) => void;
}) {
  const [page, setPage] = useState(1),
    [label, setLabel] = useState(""),
    [raw, setRaw] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [revoke, setRevoke] = useState<Key>();
  const r = useRead(() => api.keys(owner.id, page), [api, owner.id, page]);
  async function act(fn: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    pending(true);
    setError(undefined);
    try {
      await fn();
      r.reload();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
      pending(false);
    }
  }
  return (
    <>
      <h1 tabIndex={-1}>Gateway keys</h1>
      <p>
        Key owner: <strong>{owner.email}</strong>
        <small>{owner.id}</small>
      </p>
      <p>
        External MCP endpoint:{" "}
        <code>{new URL("/mcp", location.origin).href}</code>. Give your client
        this URL and your personal key.
      </p>
      <p>
        Revocation blocks the next external request. Browser login remains
        usable; already dispatched work may finish.
      </p>
      <button onClick={r.reload}>Refresh keys</button>
      <Feedback error={r.error || error} loading={r.loading} />
      {r.data && !r.data.items.length && <p>No keys for this owner.</p>}
      <ul>
        {r.data?.items.map((k) => (
          <li key={k.id}>
            {k.label} - {k.prefix} - {k.revoked_at ? "Revoked" : "Active"}
            <p>
              Created: {utc(k.created_at)}; revoked: {utc(k.revoked_at)}
            </p>
            <button
              disabled={busy || !!k.revoked_at}
              onClick={() => setRevoke(k)}
            >
              Revoke {k.label}
            </button>
          </li>
        ))}
      </ul>
      <Pagination page={page} more={!!r.data?.has_more} onPage={setPage} />
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setRaw("");
          void act(async () => {
            const k = await api.request<Key>(
              "/members/" + owner.id + "/keys",
              "POST",
              { label },
            );
            if (typeof k.raw_key !== "string")
              throw new Error(
                "One-time value was missing. Refresh metadata before trying again.",
              );
            setRaw(k.raw_key);
            setLabel("");
          });
        }}
      >
        <label>
          Key label
          <input
            required
            maxLength={100}
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
        </label>
        <button disabled={busy}>Issue key for {owner.email}</button>
      </form>
      {raw && (
        <OneTimeValue
          label="One-time gateway key"
          value={raw}
          onDismiss={() => setRaw("")}
        />
      )}{" "}
      {revoke && (
        <Confirm
          message={`Revoke ${revoke.label} for ${owner.email} (${owner.id})?`}
          onCancel={() => setRevoke(undefined)}
          onConfirm={() => {
            const k = revoke;
            setRevoke(undefined);
            void act(() =>
              api.request("/members/" + owner.id + "/keys/" + k.id, "DELETE"),
            );
          }}
        />
      )}
    </>
  );
}
