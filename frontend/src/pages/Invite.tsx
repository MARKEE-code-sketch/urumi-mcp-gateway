import { useState } from "react";
import type { Api } from "../api";
import { ApiError } from "../api";
import { Feedback } from "../components/Feedback";
export function Invite({
  api,
  token,
  navigate,
}: {
  api: Api;
  token: string;
  navigate: (s: string) => void;
}) {
  const [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState(false),
    [error, setError] = useState<unknown>();
  return (
    <>
      <h1 tabIndex={-1}>Accept invitation</h1>
      {done ? (
        <>
          <p>Account created. Log in with your email and new password.</p>
          <button onClick={() => navigate("/login")}>Go to login</button>
        </>
      ) : !token ? (
        <p role="alert">
          This invitation link is missing or malformed. Open the original
          private link.
        </p>
      ) : (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy) return;
            setBusy(true);
            setError(undefined);
            try {
              if (
                [...password].length < 12 ||
                [...password].length > 128 ||
                new TextEncoder().encode(password).length > 512
              )
                throw new ApiError(
                  "Password requires 12-128 characters and at most 512 UTF-8 bytes.",
                );
              await api.redeem(token, password);
              setDone(true);
            } catch (x) {
              setError(x);
            } finally {
              setPassword("");
              setBusy(false);
            }
          }}
        >
          <label>
            New password
            <input
              type="password"
              required
              minLength={12}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <p>Use 12-128 characters, at most 512 UTF-8 bytes.</p>
          <button disabled={busy}>Create account</button>
        </form>
      )}
      <Feedback error={error} />
    </>
  );
}
