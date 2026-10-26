import { useState } from "react";
import { Api } from "../api";
import type { Session } from "../types";
import { Feedback, useRead, utc } from "../components/Feedback";
import { Pagination } from "../components/Pagination";
export function Audit({ api, session }: { api: Api; session: Session }) {
  const [page, setPage] = useState(1),
    [outcome, setOutcome] = useState(""),
    [server, setServer] = useState(""),
    [user, setUser] = useState("");
  const filters: Record<string, string> = {};
  if (outcome) filters.outcome = outcome;
  if (server) filters.server_id = server;
  if (user && session.user.role === "admin") filters.user_id = user;
  const r = useRead(
    () => api.audit(page, filters),
    [api, page, outcome, server, user],
  );
  return (
    <>
      <h1 tabIndex={-1}>Audit</h1>
      <p>
        {session.user.role === "admin" ? "Team activity" : "Your activity"}.
        Running means unfinished; timeout and unknown may include remote
        effects.
      </p>
      <div className="audit-filters">
      <label>
        Outcome
        <select
          aria-label="Outcome"
          value={outcome}
          onChange={(e) => {
            setOutcome(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All outcomes</option>
          {["running", "success", "error", "timeout", "denied", "unknown"].map(
            (v) => (
              <option key={v}>{v}</option>
            ),
          )}
        </select>
      </label>
      <label>
        Server UUID
        <input
          value={server}
          onChange={(e) => {
            setServer(e.target.value);
            setPage(1);
          }}
        />
      </label>
      {session.user.role === "admin" && (
        <label>
          User UUID
          <input
            value={user}
            onChange={(e) => {
              setUser(e.target.value);
              setPage(1);
            }}
          />
        </label>
      )}
      <button onClick={r.reload}>Refresh audit</button>
      </div>
      <Feedback error={r.error} loading={r.loading} />
      {r.data && !r.data.items.length && <p>No matching activity.</p>}
      {r.data?.items.map((a) => (
        <article key={a.audit_id}>
          <h2>
            {a.public_tool_name} - {a.outcome}
          </h2>
          {["timeout", "unknown"].includes(a.outcome) && (
            <p className="chat-warning">Remote effects may have happened. Check the record before repeating the action.</p>
          )}
          {a.error_summary && <p>{a.error_summary}</p>}
          <p>Started: {utc(a.started_at)} · Duration: {a.duration_ms === null ? "Unknown" : a.duration_ms + " ms"}</p>
          <details className="audit-details">
          <summary>Record details</summary>
          <dl>
            {Object.entries({
              Audit: a.audit_id,
              Request: a.request_id,
              User: a.user_id,
              Key: a.key_id,
              "Auth source": a.auth_source,
              Server: a.server_id,
              "Upstream tool": a.upstream_tool_name,
              "Duration ms": a.duration_ms,
              "Error code": a.error_code,
              "Safe explanation": a.error_summary,
            }).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v ?? "Unknown"}</dd>
              </div>
            ))}
          </dl>
          <p>Started: {utc(a.started_at)}</p>
          <p>Finished: {utc(a.finished_at)}</p>
          </details>
        </article>
      ))}
      <Pagination page={page} more={!!r.data?.has_more} onPage={setPage} />
    </>
  );
}
