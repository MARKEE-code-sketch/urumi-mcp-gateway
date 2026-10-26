import { useState } from "react";
import type { Api } from "../api";
import type { Session } from "../types";
import { Feedback } from "../components/Feedback";
export function Login({
  api,
  onLogin,
}: {
  api: Api;
  onLogin: (s: Session) => void;
}) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  return (
    <>
      <h1 tabIndex={-1}>Login</h1>
      <p>
        Use your team account. Gateway API keys are for external MCP clients.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          setBusy(true);
          setError(undefined);
          try {
            onLogin(await api.login(email, password));
          } catch (x) {
            setError(x);
          } finally {
            setPassword("");
            setBusy(false);
          }
        }}
      >
        <label>
          Email
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <button disabled={busy}>Log in</button>
      </form>
      <Feedback error={error} />
    </>
  );
}
