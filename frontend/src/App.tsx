import { useEffect, useRef, useState } from "react";
import { Api, ApiError } from "./api";
import type { Session, User } from "./types";
import { Login } from "./pages/Login";
import { Invite } from "./pages/Invite";
import { Servers } from "./pages/Servers";
import { Members } from "./pages/Members";
import { Keys } from "./pages/Keys";
import { Audit } from "./pages/Audit";
import { Chat } from "./pages/Chat";
import { captureInvite } from "./invitation";
import { Feedback } from "./components/Feedback";
import { Icon, type IconName } from "./components/Icon";
import mark from "./assets/urumi-mark.svg?no-inline";
export function App({ invitation = "" }: { invitation?: string }) {
  const [path, setPath] = useState(
      location.pathname === "/" ? "/servers" : location.pathname,
    ),
    [session, setSession] = useState<Session>(),
    [checking, setChecking] = useState(true),
    [loggingOut, setLoggingOut] = useState(false),
    [epoch, setEpoch] = useState(0),
    [owner, setOwner] = useState<User>(),
    [pending, setPending] = useState(false),
    [logoutError, setLogoutError] = useState<unknown>(),
    [sessionError, setSessionError] = useState<unknown>(),
    [retry, setRetry] = useState(0);
  const [inviteToken, setInviteToken] = useState(invitation);
  const [inviteVersion, setInviteVersion] = useState(0);
  // A view token prevents a late write from changing the next screen.
  const viewRef = useRef(0);
  const sessionRef = useRef<Session | undefined>(undefined),
    epochRef = useRef(0),
    retryCsrf = useRef(""),
    apiRef = useRef<Api | undefined>(undefined);
  function clear() {
    epochRef.current++;
    viewRef.current++;
    apiRef.current?.abort();
    sessionRef.current = undefined;
    setSession(undefined);
    setOwner(undefined);
    setPending(false);
    setEpoch(epochRef.current);
  }
  if (!apiRef.current)
    apiRef.current = new Api(
      () => sessionRef.current?.csrf_token ?? retryCsrf.current,
      () => {
        clear();
        setPath("/login");
        history.replaceState(null, "", "/login");
      },
    );
  const api = apiRef.current;
  function navigate(next: string, member?: User) {
    if (
      pending &&
      !window.confirm(
        "Work may already have taken effect. Leave and discard the local response?",
      )
    )
      return;
    viewRef.current++;
    api.abort();
    setPending(false);
    setOwner(member);
    setInviteToken("");
    history.pushState(null, "", next);
    setPath(next);
  }
  useEffect(() => {
    if (path === "/invite" || path === "/login") {
      setChecking(false);
      return;
    }
    const captured = epochRef.current;
    api
      .me()
      .then((s) => {
        if (captured === epochRef.current) {
          sessionRef.current = s;
          setSession(s);
        }
      })
      .catch((e) => {
        if (
          captured === epochRef.current &&
          !(e instanceof ApiError && e.status === 401)
        )
          setSessionError(e);
      })
      .finally(() => setChecking(false));
  }, [retry]);
  useEffect(() => {
    const fragment = () => {
      if (location.pathname === "/invite") {
        viewRef.current++;
        api.abort();
        setInviteToken(captureInvite());
        setInviteVersion((v) => v + 1);
        setPath("/invite");
      }
    };
    addEventListener("hashchange", fragment);
    const pop = () => {
      if (
        pending &&
        !window.confirm(
          "Leave pending work? Remote effects may already have happened.",
        )
      ) {
        history.pushState(null, "", path);
        return;
      }
      viewRef.current++;
      api.abort();
      setOwner(undefined);
      setPending(false);
      setPath(location.pathname);
    };
    const unload = (e: BeforeUnloadEvent) => {
      if (pending) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    addEventListener("popstate", pop);
    addEventListener("beforeunload", unload);
    return () => {
      removeEventListener("hashchange", fragment);
      removeEventListener("popstate", pop);
      removeEventListener("beforeunload", unload);
    };
  }, [pending, path]);
  useEffect(() => {
    document.querySelector<HTMLElement>("h1")?.focus();
  }, [path, session, checking]);
  async function logout() {
    if (
      pending &&
      !confirm(
        "Work may already have taken effect. Clear local data and log out?",
      )
    )
      return;
    if (loggingOut) return;
    setLoggingOut(true);
    retryCsrf.current = sessionRef.current?.csrf_token ?? retryCsrf.current;
    clear();
    setPath("/login");
    history.replaceState(null, "", "/login");
    try {
      await api.logout();
      retryCsrf.current = "";
      setLogoutError(undefined);
    } catch (e) {
      setLogoutError(e);
    } finally {
      setLoggingOut(false);
    }
  }
  const view = viewRef.current;
  const guardedPending = (value: boolean) => {
    if (view === viewRef.current) setPending(value);
  };
  const publicPage = path === "/invite" || path === "/login";
  let content;
  if (checking && !publicPage)
    content = <p role="status">Checking your session...</p>;
  else if (path === "/invite")
    content = (
      <Invite
        key={inviteVersion}
        api={api}
        token={inviteToken}
        navigate={navigate}
      />
    );
  else if (sessionError && !session)
    content = (
      <>
        <h1 tabIndex={-1}>Session check unavailable</h1>
        <Feedback error={sessionError} />
        <button
          onClick={() => {
            setSessionError(undefined);
            setChecking(true);
            setRetry((v) => v + 1);
          }}
        >
          Retry session check
        </button>
      </>
    );
  else if (loggingOut)
    content = (
      <p role="status">
        Confirming server logout. Please wait before another login.
      </p>
    );
  else if (!session || path === "/login")
    content = (
      <Login
        api={api}
        onLogin={(s) => {
          if (view !== viewRef.current) return;
          clear();
          retryCsrf.current = "";
          setLogoutError(undefined);
          sessionRef.current = s;
          setSession(s);
          setPath("/servers");
          history.replaceState(null, "", "/servers");
        }}
      />
    );
  else if (path === "/servers")
    content = <Servers api={api} session={session} pending={guardedPending} />;
  else if (path === "/members")
    content =
      session.user.role === "admin" ? (
        <Members
          api={api}
          pending={guardedPending}
          onKeys={(u) => navigate("/keys", u)}
        />
      ) : (
        <>
          <h1 tabIndex={-1}>Access denied</h1>
          <p>Admin access is required.</p>
        </>
      );
  else if (path === "/keys")
    content = (
      <Keys
        key={owner?.id ?? session.user.id}
        api={api}
        owner={owner ?? session.user}
        pending={guardedPending}
      />
    );
  else if (path === "/audit") content = <Audit api={api} session={session} />;
  else if (path === "/chat")
    content = <Chat api={api} pending={guardedPending} onNavigate={navigate} />;
  else content = <h1 tabIndex={-1}>Not found</h1>;
  return (
    <div className={`shell ${session ? "signed-in" : "public-shell"}`}>
        {session && (
          <aside className="sidebar">
            <div className="brand"><img src={mark} alt="" /><span>urumi<span className="brand-period">.</span></span></div>
            <div className="workspace"><span className="workspace-avatar">U</span><div><strong>Urumi workspace</strong><span>Team gateway</span></div><span className="team-label">TEAM</span></div>
            <p className="nav-label">WORKSPACE</p>
            <nav aria-label="Main navigation">
            {[
              "chat",
              "servers",
              ...(session.user.role === "admin" ? ["members"] : []),
              "keys",
              "audit",
            ].map((v) => (
              <a
                key={v}
                href={"/" + v}
                aria-current={path === "/" + v ? "page" : undefined}
                onClick={(e) => {
                  e.preventDefault();
                  navigate("/" + v);
                }}
              >
                <Icon name={v as IconName} />
                {v[0].toUpperCase() + v.slice(1)}
                <span className="nav-active-dot" />
              </a>
            ))}
            </nav>
            <div className="sidebar-bottom">
              <div className="trust-note"><Icon name="shield" /><div><strong>Your team. Your access.</strong><p>Tools run with your permissions. Every call is recorded.</p></div></div>
              <div className="profile"><span className="avatar">{session.user.email.slice(0, 2).toUpperCase()}</span><div><strong>{session.user.email}</strong><span>Workspace {session.user.role}</span></div></div>
            </div>
          </aside>
        )}
      <div className="main-shell">
        {session ? <header className="topbar"><div className="breadcrumb"><span>Workspace</span><Icon name="chevron" /><strong>{({ "/chat": "Chat", "/servers": "Servers", "/members": "Members", "/keys": "API keys", "/audit": "Activity" } as Record<string, string>)[path] ?? "Workspace"}</strong></div><div className="topbar-right"><span className="secure"><Icon name="shield" />Team access</span><span className="avatar small" title={session.user.email}>{session.user.email.slice(0, 2).toUpperCase()}</span><button className="logout-button" onClick={() => void logout()}><Icon name="logout" />Logout</button></div></header> : <div className="public-brand brand"><img src={mark} alt="" /><span>urumi<span className="brand-period">.</span></span></div>}
        <main className={session ? (path === "/chat" ? "chat-main" : "management-page") : "public-page"} key={epoch + ":" + path}>
          {!!logoutError && (
            <>
              <p role="alert">
                Local data cleared; server logout could not be confirmed.
              </p>
              <Feedback error={logoutError} />
              {retryCsrf.current && (
                <button onClick={() => void logout()}>Retry logout</button>
              )}
            </>
          )}
          {content}
        </main>
      </div>
    </div>
  );
}


