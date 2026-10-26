import { useState } from "react";
import { Api } from "../api";
import type { User } from "../types";
import { Feedback, useRead, utc } from "../components/Feedback";
import { Pagination } from "../components/Pagination";
import { OneTimeValue } from "../components/OneTimeValue";
export function Members({
  api,
  onKeys,
  pending,
}: {
  api: Api;
  onKeys: (user: User) => void;
  pending: (v: boolean) => void;
}) {
  const [page, setPage] = useState(1),
    [email, setEmail] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [invite, setInvite] = useState<{
      invite_url: string;
      expires_at: string;
    }>();
  const r = useRead(() => api.members(page), [api, page]);
  return (
    <>
      <h1 tabIndex={-1}>Members</h1>
      <p>Invite a member for 24 hours. Share the one-time link privately.</p>
      <button onClick={r.reload}>Refresh members</button>
      <Feedback error={r.error || error} loading={r.loading} />
      {r.data && !r.data.items.length && <p>No members.</p>}
      <ul>
        {r.data?.items.map((u) => (
          <li key={u.id}>
            {u.email} - {u.role} <small>{u.id}</small>
            <button onClick={() => onKeys(u)}>Manage keys for {u.email}</button>
          </li>
        ))}
      </ul>
      <Pagination page={page} more={!!r.data?.has_more} onPage={setPage} />
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          pending(true);
          setError(undefined);
          setInvite(undefined);
          try {
            setInvite(
              await api.request("/invitations", "POST", {
                email,
                role: "member",
              }),
            );
            setEmail("");
          } catch (x) {
            setError(x);
          } finally {
            setBusy(false);
            pending(false);
          }
        }}
      >
        <label>
          Invite email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <p>Role: member</p>
        <button disabled={busy}>Create invitation</button>
      </form>
      {invite && (
        <>
          <p>Expires: {utc(invite.expires_at)}</p>
          <OneTimeValue
            label="Private invitation link"
            value={invite.invite_url}
            onDismiss={() => setInvite(undefined)}
          />
        </>
      )}
    </>
  );
}
